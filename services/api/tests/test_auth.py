"""SaaS tests — auth, per-user keys/endpoints, credential-scoped Q&A."""


def _register(client, email="ada@sherpa.dev"):
    r = client.post("/api/auth/register", json={
        "name": "Ada", "email": email, "password": "correct-horse-9"})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def test_register_login_me(client):
    token = _register(client)
    assert client.post("/api/auth/login", json={
        "email": "ada@sherpa.dev", "password": "correct-horse-9"}).status_code == 200
    assert client.post("/api/auth/login", json={
        "email": "ada@sherpa.dev", "password": "wrong-pass-1"}).status_code == 401
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "ada@sherpa.dev"
    assert client.get("/api/auth/me").status_code == 401
    # duplicate + bad email rejected
    assert client.post("/api/auth/register", json={
        "name": "x", "email": "ada@sherpa.dev",
        "password": "correct-horse-9"}).status_code == 409
    assert client.post("/api/auth/register", json={
        "name": "x", "email": "not-an-email",
        "password": "correct-horse-9"}).status_code == 422


def test_provider_keys_crud(client):
    token = _register(client, "grace@sherpa.dev")
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/keys").status_code == 401  # auth required
    # bad prefix rejected before anything is stored
    bad = client.post("/api/keys", headers=h, json={
        "label": "main", "provider": "openai", "model": "gpt-4o-mini",
        "api_key": "nope"})
    assert bad.status_code == 422
    good = client.post("/api/keys", headers=h, json={
        "label": "main", "provider": "openai", "model": "gpt-4o-mini",
        "api_key": "sk-test1234567890"})
    assert good.status_code == 201, good.text
    body = good.json()
    assert body["last4"] == "…7890" and "sk-test" not in str(body)  # never leaks
    assert len(client.get("/api/keys", headers=h).json()) == 1
    assert client.delete(f"/api/keys/{body['id']}", headers=h).status_code == 204
    assert client.get("/api/keys", headers=h).json() == []


def test_openrouter_key_accepted(client):
    token = _register(client, "openrouter@sherpa.dev")
    h = {"Authorization": f"Bearer {token}"}
    # wrong prefix rejected
    assert client.post("/api/keys", headers=h, json={
        "provider": "openrouter", "api_key": "sk-notopenrouter"}).status_code == 422
    good = client.post("/api/keys", headers=h, json={
        "label": "or", "provider": "openrouter",
        "model": "anthropic/claude-3.5-haiku",
        "api_key": "sk-or-test1234567890"})
    assert good.status_code == 201, good.text
    assert good.json()["last4"] == "…7890"


def test_endpoints_crud_and_probe(client):
    token = _register(client, "Edsger@sherpa.dev".lower())
    h = {"Authorization": f"Bearer {token}"}
    bad = client.post("/api/endpoints", headers=h, json={
        "name": "x", "base_url": "not-a-url", "kind": "openai-compatible"})
    assert bad.status_code == 422
    created = client.post("/api/endpoints", headers=h, json={
        "name": "local ollama", "base_url": "http://localhost:11434",
        "kind": "ollama", "model": "codellama"}).json()
    assert created["has_key"] is False
    probe = client.post("/api/endpoints/test", headers=h, json={
        "name": "p", "base_url": "http://127.0.0.1:9",
        "kind": "openai-compatible"}).json()
    assert probe["ok"] is False  # nothing listens there; must fail gracefully
    assert client.delete(f"/api/endpoints/{created['id']}",
                         headers=h).status_code == 204


def test_ask_with_foreign_key_rejected(client):
    """Users can't borrow each other's credentials (or use them logged out)."""
    t1 = _register(client, "a@sherpa.dev")
    t2 = _register(client, "b@sherpa.dev")
    k = client.post("/api/keys", headers={"Authorization": f"Bearer {t1}"},
                    json={"provider": "openai", "api_key": "sk-test1234567890"})
    key_id = k.json()["id"]
    # ingest something to ask about (auth tables live under the same app)
    repo = client.post("/api/ingest-self").json()["repo_id"]
    anon = client.post("/api/ask", json={"repo_id": repo, "question": "hi",
                                         "key_id": key_id})
    assert anon.status_code == 401
    other = client.post("/api/ask", headers={"Authorization": f"Bearer {t2}"},
                        json={"repo_id": repo, "question": "hi", "key_id": key_id})
    assert other.status_code == 404
    # anonymous ask without credentials still works (offline fallback)
    plain = client.post("/api/ask", json={"repo_id": repo, "question": "how are citations verified?"})
    assert plain.status_code == 200 and plain.json()["citations"]
