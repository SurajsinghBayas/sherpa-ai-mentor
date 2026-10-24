"""Profile: details and stats, renaming, connecting Google, and never disconnecting the last way in."""
from app import github as gh
from app.config import settings
from app.routers import profile as prof

CB = "http://localhost:3000/auth/github/callback"


def auth(client, email="p@example.com"):
    r = client.post("/api/auth/register", json={"name": "Pat", "email": email, "password": "pw-123456789"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_profile_and_rename(client):
    h = auth(client)
    p = client.get("/api/profile", headers=h).json()
    assert p["email"] == "p@example.com" and p["name"] == "Pat"
    assert p["sign_in"] == {"password": True, "email_code": True, "google": False, "github": None}
    assert p["stats"]["repos"] == 0 and p["stats"]["best_score"] is None and p["today"]["llm_limit"] > 0
    assert client.post("/api/profile", json={"name": "  Pat   Lee "}, headers=h).json()["name"] == "Pat Lee"
    assert client.post("/api/profile", json={"name": "   "}, headers=h).status_code == 422
    assert client.get("/api/profile").status_code == 401


def test_connect_and_disconnect_google(client, monkeypatch):
    monkeypatch.setattr(prof, "_verify_google", lambda c: {"sub": "g-1", "email": "other@gmail.com", "email_verified": True})
    h = auth(client)
    assert client.post("/api/profile/google", json={"credential": "x"}, headers=h).json()["sign_in"]["google"] is True
    h2 = auth(client, "q@example.com")
    assert client.post("/api/profile/google", json={"credential": "x"}, headers=h2).status_code == 409
    assert client.delete("/api/profile/google", headers=h).json()["sign_in"]["google"] is False
    assert client.delete("/api/profile/nope", headers=h).status_code == 404


def test_cannot_remove_the_only_sign_in(client, monkeypatch):
    monkeypatch.setattr(settings, "github_client_id", "Iv23test")
    monkeypatch.setattr(settings, "github_client_secret", "secret")
    monkeypatch.setattr(settings, "allowed_origins", "http://localhost:3000")
    monkeypatch.setattr(gh, "profile", lambda code, uri: {"id": "77", "login": "solo", "name": "Solo", "emails": []})
    state = client.get("/api/auth/github/start", params={"redirect_uri": CB}).json()["state"]
    tok = client.post("/api/auth/github", json={"code": "c", "state": state, "redirect_uri": CB}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    p = client.get("/api/profile", headers=h).json()
    assert p["noreply_email"] and p["sign_in"] == {"password": False, "email_code": False, "google": False, "github": "solo"}
    r = client.delete("/api/profile/github", headers=h)
    assert r.status_code == 409 and "only way to sign in" in r.json()["detail"]
