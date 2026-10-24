"""Tech stack tree: manifests → workspaces → categories, each entry citing the line that declares it."""
from app.agents.stack import build_stack, classify
from app.chunk import chunk_file
from app.store import RepoStore

SRC = {
    "web/package.json": '{\n  "name": "web",\n  "engines": { "node": ">=20" },\n  "dependencies": {\n'
                        '    "next": "^14.2.5",\n    "react": "18.3.1",\n    "react-dom": "18.3.1",\n'
                        '    "@radix-ui/react-dialog": "1.0.0",\n    "left-pad": "1.3.0"\n  },\n'
                        '  "devDependencies": {\n    "typescript": "5.4.5",\n    "@types/react": "18.0.0"\n  }\n}\n',
    "api/requirements.txt": "# server\nfastapi==0.115.*\nuvicorn[standard]>=0.30\n-r dev.txt\nsqlalchemy==2.*\n",
    "api/pyproject.toml": '[project]\nname = "api"\nrequires-python = ">=3.11"\ndependencies = [\n'
                          '  "pydantic>=2",\n  "openai>=1.0",\n]\n\n[project.optional-dependencies]\n'
                          'test = ["pytest>=8"]\n',
    "svc/go.mod": "module example.com/svc\n\ngo 1.22\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.10.0\n"
                  "\tgorm.io/gorm v1.25.0 // indirect\n)\n",
    "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n  cache:\n    image: redis:7-alpine\n",
    "api/Dockerfile": "# api image\nFROM python:3.11-slim\nRUN pip install -r requirements.txt\n",
    ".github/workflows/ci.yml": "name: CI\non: push\n",
    "api/app.py": "def main():\n    return 1\n",
    "web/page.tsx": "export default function Page() {\n  return null\n}\n",
    "svc/main.go": "package main\n\nfunc main() {}\n",
}


def store(src=SRC, rid="stack1") -> RepoStore:
    s = RepoStore(rid)
    s.save([c for f, t in src.items() for c in chunk_file(t, f)], {"name": "x/y", "kind": "git"}, dict(src))
    return s


def _items(result, group):
    g = next(g for g in result["groups"] if g["name"] == group)
    return {i["name"]: {**i, "category": c["id"]} for c in g["categories"] for i in c["items"]}


def test_classify_exact_and_prefix():
    assert classify("next") == ("Next.js", "framework")
    assert classify("@radix-ui/react-dialog") == ("Radix UI", "ui")
    assert classify("pytest-asyncio") == ("pytest plugins", "testing")
    assert classify("left-pad") is None


def test_stack_tree_groups_categories_and_cites_lines():
    s = store()
    r = build_stack(s)
    assert [g["name"] for g in r["groups"]] == ["api", "svc", "web", "Infrastructure & delivery"]

    web = _items(r, "web")
    assert web["Next.js"]["category"] == "framework" and web["Next.js"]["version"] == "14.2.5"
    assert web["Next.js"]["cite"] == {"file": "web/package.json", "start_line": 5, "end_line": 5}
    assert web["TypeScript"]["dev"] and not web["React"]["dev"]
    assert web["Node.js"]["category"] == "runtime" and web["Node.js"]["version"] == ">=20"
    assert web["left-pad"]["category"] == "other"
    assert "@types/react" not in web and not any(i["package"] == "react-dom" for i in web.values())

    api = _items(r, "api")  # requirements.txt and pyproject.toml in one workspace
    assert api["FastAPI"]["version"] == "0.115.*" and api["FastAPI"]["cite"]["start_line"] == 2
    assert api["Uvicorn"]["version"] == ">=0.30"
    assert api["Python"]["version"] == ">=3.11" and api["OpenAI SDK"]["category"] == "ai"
    assert api["pytest"]["dev"] and api["pytest"]["cite"]["file"] == "api/pyproject.toml"

    svc = _items(r, "svc")
    assert svc["Gin"]["version"] == "v1.10.0" and svc["GORM"]["cite"]["start_line"] == 7
    assert svc["Go"]["version"] == "1.22"

    infra = _items(r, "Infrastructure & delivery")
    assert infra["PostgreSQL"]["version"] == "16" and infra["PostgreSQL"]["cite"]["start_line"] == 3
    assert infra["Docker"]["cite"] == {"file": "api/Dockerfile", "start_line": 2, "end_line": 2}
    assert infra["GitHub Actions"]["detail"] == "CI"

    # every citation points at a real line of the snapshot
    for g in r["groups"]:
        for c in g["categories"]:
            for i in c["items"]:
                assert 1 <= i["cite"]["start_line"] <= len(s.lines(i["cite"]["file"]))
    assert {"Python", "TypeScript", "Go"} <= {lang["name"] for lang in r["languages"]}


def test_stack_is_cached_per_snapshot():
    s = store(rid="stack2")
    first = build_stack(s)
    assert s.cache_get("stack") is first or s.cache_get("stack") == first
    s2 = store({**SRC, "Makefile": "test:\n\tpytest\n"}, rid="stack2")
    assert s2.cache_get("stack") is None or s2.snapshot_hash != first["snapshot"]
    again = build_stack(s2)
    assert any(i["name"] == "Make" for g in again["groups"] for c in g["categories"] for i in c["items"])


def test_stack_endpoint_needs_login(client):
    assert client.post("/api/stack", json={"repo_id": "missing1"}).status_code == 401
    r = client.post("/api/auth/register", json={"email": "stack@example.com", "password": "password123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.post("/api/stack", json={"repo_id": "missing1"}, headers=h).status_code == 404
