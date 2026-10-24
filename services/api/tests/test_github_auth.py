"""GitHub sign-in (state, sign-up, account linking) and listing a user's public repos. GitHub is faked."""
import pytest

from app import github as gh
from app.config import settings

CB = "http://localhost:3000/auth/github/callback"
OCTO = {"id": "583231", "login": "octocat", "name": "The Octocat", "emails": ["octo@example.com"]}


@pytest.fixture(autouse=True)
def github_app(monkeypatch):
    monkeypatch.setattr(settings, "github_client_id", "Iv23test")
    monkeypatch.setattr(settings, "github_client_secret", "secret")
    monkeypatch.setattr(settings, "allowed_origins", "http://localhost:3000")
    gh._repos.clear()


def fake_github(monkeypatch, who=OCTO):
    monkeypatch.setattr(gh, "profile", lambda code, redirect_uri: dict(who))


def sign_in(client, link_token=None):
    h = {"Authorization": f"Bearer {link_token}"} if link_token else {}
    r = client.get("/api/auth/github/start", params={"redirect_uri": CB, "link": bool(link_token)}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith("https://github.com/login/oauth/authorize?client_id=Iv23test")
    return client.post("/api/auth/github", json={"code": "abc", "state": r.json()["state"], "redirect_uri": CB})


def test_config_and_start_checks(client, monkeypatch):
    assert client.get("/api/auth/config").json()["github"] is True
    assert client.get("/api/auth/github/start", params={"redirect_uri": "https://evil.example/auth/github/callback"}).status_code == 422
    assert client.get("/api/auth/github/start", params={"redirect_uri": CB, "link": True}).status_code == 401
    monkeypatch.setattr(settings, "github_client_secret", "")
    assert client.get("/api/auth/github/start", params={"redirect_uri": CB}).status_code == 503


def test_sign_up_then_sign_in_is_the_same_account(client, monkeypatch):
    fake_github(monkeypatch)
    t1 = sign_in(client).json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {t1}"}).json()
    assert me["email"] == "octo@example.com" and me["github_login"] == "octocat" and me["name"] == "The Octocat"
    t2 = sign_in(client).json()["access_token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {t2}"}).json()["id"] == me["id"]


def test_bad_state_and_wrong_callback_are_refused(client, monkeypatch):
    fake_github(monkeypatch)
    bad = client.post("/api/auth/github", json={"code": "abc", "state": "forged", "redirect_uri": CB})
    assert bad.status_code == 400
    state = client.get("/api/auth/github/start", params={"redirect_uri": CB}).json()["state"]
    other = client.post("/api/auth/github", json={"code": "abc", "state": state,
                                                  "redirect_uri": "http://127.0.0.1:3000/auth/github/callback"})
    assert other.status_code == 400
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {state}"}).status_code == 401  # not a session


def test_existing_email_account_is_linked_and_no_email_gets_noreply(client, monkeypatch):
    r = client.post("/api/auth/register", json={"name": "O", "email": "octo@example.com", "password": "pw-123456789"})
    uid = client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()["id"]
    fake_github(monkeypatch)
    t = sign_in(client).json()["access_token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {t}"}).json()["id"] == uid
    fake_github(monkeypatch, {"id": "9", "login": "Quiet-One", "name": "Quiet-One", "emails": []})
    t = sign_in(client).json()["access_token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {t}"}).json()["email"] == "9+quiet-one@users.noreply.github.com"


def test_connect_github_to_a_signed_in_account(client, monkeypatch):
    a = client.post("/api/auth/register", json={"name": "A", "email": "a@example.com", "password": "pw-123456789"}).json()["access_token"]
    fake_github(monkeypatch)
    r = sign_in(client, link_token=a)
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert me["email"] == "a@example.com" and me["github_login"] == "octocat"
    b = client.post("/api/auth/register", json={"name": "B", "email": "b@example.com", "password": "pw-123456789"}).json()["access_token"]
    assert sign_in(client, link_token=b).status_code == 409  # already connected to account A


def test_public_repos_listing(client, monkeypatch):
    h = {"Authorization": "Bearer " + client.post("/api/auth/register", json={
        "name": "N", "email": "n@example.com", "password": "pw-123456789"}).json()["access_token"]}
    assert client.get("/api/github/repos", headers=h).status_code == 409  # no GitHub connected yet
    fake_github(monkeypatch)
    h = {"Authorization": f"Bearer {sign_in(client).json()['access_token']}"}
    calls = []

    def fetch(login):
        calls.append(login)
        return [gh._repo({"full_name": "octocat/hello", "name": "hello", "html_url": "https://github.com/octocat/hello",
                          "language": "Python", "stargazers_count": 3, "pushed_at": "2026-10-01T00:00:00Z", "size": 12})]

    monkeypatch.setattr(gh, "_fetch_repos", fetch)
    body = client.get("/api/github/repos", headers=h).json()
    assert body["login"] == "octocat" and body["repos"][0]["full_name"] == "octocat/hello"
    assert body["repos"][0]["repo_id"] is None
    client.get("/api/github/repos", headers=h)
    assert calls == ["octocat"]  # cached
    client.get("/api/github/repos?refresh=true", headers=h)
    assert calls == ["octocat", "octocat"]
