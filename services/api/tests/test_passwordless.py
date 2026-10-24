"""Email one-time codes and Google sign-in."""
import re

import pytest


@pytest.fixture()
def outbox(monkeypatch):
    """Capture mail instead of sending it; the code is read from the message."""
    import app.routers.auth as auth
    sent = []
    monkeypatch.setattr(auth, "mail_configured", lambda: True)
    monkeypatch.setattr(auth, "send_mail", lambda to, subject, text, html: sent.append((to, subject, text)))
    return sent


def _code(outbox):
    return re.search(r"\b(\d{6})\b", outbox[-1][2]).group(1)


def _clear_throttle(client):
    from app.db import SessionLocal  # noqa: F401 — the fixture patched it
    import app.db as dbmod
    from app.dbmodels import EmailOtp
    with dbmod.SessionLocal() as db:
        for o in db.query(EmailOtp).all():
            o.created_at -= 120
        db.commit()


def test_signup_then_login_with_email_code(client, outbox):
    r = client.post("/api/auth/otp/request", json={"email": "Ada@Example.com", "purpose": "signup", "name": "Ada"})
    assert r.status_code == 200 and outbox[-1][0] == "ada@example.com"
    assert "Sherpa AI" in outbox[-1][1] and _code(outbox) in outbox[-1][1]
    # wrong code burns a try, right code creates the account
    wrong = "000000" if _code(outbox) != "000000" else "111111"
    bad = client.post("/api/auth/otp/verify", json={"email": "ada@example.com", "code": wrong, "purpose": "signup"})
    assert bad.status_code == 400 and "4 tries left" in bad.json()["detail"]
    ok = client.post("/api/auth/otp/verify", json={"email": "ada@example.com", "code": _code(outbox), "purpose": "signup"})
    assert ok.status_code == 200
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {ok.json()['access_token']}"}).json()
    assert me["email"] == "ada@example.com" and me["name"] == "Ada"
    # the code is single-use
    again = client.post("/api/auth/otp/verify", json={"email": "ada@example.com", "code": _code(outbox), "purpose": "signup"})
    assert again.status_code == 400
    # signing up twice is refused; logging in works; password login explains itself
    assert client.post("/api/auth/otp/request", json={"email": "ada@example.com", "purpose": "signup"}).status_code == 409
    _clear_throttle(client)
    assert client.post("/api/auth/otp/request", json={"email": "ada@example.com", "purpose": "login"}).status_code == 200
    login = client.post("/api/auth/otp/verify", json={"email": "ada@example.com", "code": _code(outbox), "purpose": "login"})
    assert login.status_code == 200
    pw = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "whatever123"})
    assert pw.status_code == 401 and "email code, Google or GitHub" in pw.json()["detail"]


def test_email_code_limits(client, outbox):
    assert client.post("/api/auth/otp/request", json={"email": "nobody@example.com", "purpose": "login"}).status_code == 404
    assert client.post("/api/auth/otp/request", json={"email": "bob@example.com", "purpose": "signup"}).status_code == 200
    # resend throttled
    assert client.post("/api/auth/otp/request", json={"email": "bob@example.com", "purpose": "signup"}).status_code == 429
    good = _code(outbox)
    wrong = "111111" if good != "111111" else "222222"
    codes = [client.post("/api/auth/otp/verify", json={"email": "bob@example.com", "code": wrong,
                                                       "purpose": "signup"}).status_code for _ in range(5)]
    assert codes == [400] * 5
    # after 5 wrong tries even the right code is refused
    assert client.post("/api/auth/otp/verify", json={"email": "bob@example.com", "code": good,
                                                     "purpose": "signup"}).status_code == 429


def test_expired_code_rejected(client, outbox):
    import app.db as dbmod
    from app.dbmodels import EmailOtp
    client.post("/api/auth/otp/request", json={"email": "cy@example.com", "purpose": "signup"})
    with dbmod.SessionLocal() as db:
        db.query(EmailOtp).update({EmailOtp.expires_at: 0})
        db.commit()
    r = client.post("/api/auth/otp/verify", json={"email": "cy@example.com", "code": _code(outbox), "purpose": "signup"})
    assert r.status_code == 400 and "expired" in r.json()["detail"]


def test_google_sign_in_creates_then_links(client, monkeypatch):
    import app.routers.auth as auth
    claims = {"sub": "g-123", "email": "Dee@Gmail.com", "email_verified": True, "name": "Dee"}
    monkeypatch.setattr(auth, "_verify_google", lambda cred: claims)
    first = client.post("/api/auth/google", json={"credential": "x"})
    assert first.status_code == 200
    h = {"Authorization": f"Bearer {first.json()['access_token']}"}
    me = client.get("/api/auth/me", headers=h).json()
    assert me["email"] == "dee@gmail.com" and me["name"] == "Dee"
    # same Google account → same user
    again = client.post("/api/auth/google", json={"credential": "x"}).json()["access_token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {again}"}).json()["id"] == me["id"]
    # an existing password account with the same email gets linked, not duplicated
    client.post("/api/auth/register", json={"email": "eve@example.com", "password": "password123"})
    claims.update(sub="g-456", email="eve@example.com")
    eve = client.post("/api/auth/google", json={"credential": "x"}).json()["access_token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {eve}"}).json()["email"] == "eve@example.com"


def test_google_rejects_unverifiable_tokens(client):
    r = client.post("/api/auth/google", json={"credential": "not-a-jwt"})
    assert r.status_code == 401
    cfg = client.get("/api/auth/config").json()
    assert cfg["google_client_id"] == "test-client.apps.googleusercontent.com" and cfg["email_otp"]


def test_code_email_is_branded_and_complete():
    from app.mailer import build_message, otp_email
    subject, text, html = otp_email("482913", "signup", 10, "ada@example.com")
    assert subject == "482913 is your Sherpa AI code"
    assert "482913" in text and "482913" in html and "ada@example.com" in html
    msg = build_message("ada@example.com", subject, text, html)
    parts = {p.get_content_type() for p in msg.walk()}
    assert {"text/plain", "text/html", "image/png"} <= parts
    cid = next(p for p in msg.walk() if p.get_content_type() == "image/png")["Content-ID"].strip("<>")
    assert f"cid:{cid}" in next(p for p in msg.walk() if p.get_content_type() == "text/html").get_content()
