"""Pipeline machine: graphs declared in code, the model's map, citation checks."""
from app.agents import pipeline as pl
from app.chunk import chunk_file
from app.store import RepoStore

GRAPH = '''from langgraph.graph import StateGraph, END


def plan(state):
    return state


def call_tools(state):
    return state


def should_continue(state):
    return "tools" if state.get("todo") else END


g = StateGraph(dict)
g.add_node("agent", plan)
g.add_node("tools", call_tools)
g.set_entry_point("agent")
g.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
g.add_edge("tools", "agent")
app = g.compile()
'''

WORKFLOW = '''name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: pytest
  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - run: docker build .
  deploy:
    needs: [test, build]
    runs-on: ubuntu-latest
    steps:
      - run: ./deploy.sh
'''

SKLEARN = '''from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

clf = Pipeline([
    ("scale", StandardScaler()),
    ("classify", LogisticRegression()),
])
'''


def store(src: dict, rid="machine") -> RepoStore:
    s = RepoStore(rid)
    s.save([c for f, t in src.items() for c in chunk_file(t, f)], {"source": "test", "name": "demo"}, dict(src))
    return s


def test_langgraph_nodes_edges_and_loop_offline():
    s = store({"agent/graph.py": GRAPH})
    g = pl.declared_graph(s)
    assert g["source"] == "LangGraph"
    assert {x["id"] for x in g["stages"]} == {"__start__", "agent", "tools", "__end__"}
    assert ("agent", "tools", "should_continue") in g["links"] and ("tools", "agent", "") in g["links"]

    out = pl.build_pipeline(s)  # no LLM in tests: drawn from the declaration
    assert out["found"] and out["mode"] == "offline" and out["kind"] == "agent"
    assert [x["id"] for x in out["stages"]] == ["__start__", "agent", "tools", "__end__"]
    assert out["stages"][0]["type"] == "input" and out["stages"][-1]["type"] == "output"
    assert all(x["cite"]["file"] == "agent/graph.py" for x in out["stages"])
    back = [x for x in out["links"] if x["from"] == "tools" and x["to"] == "agent"]
    assert back and back[0]["loop"]  # the tool result goes back to the agent


REACT = '''from typing import Literal
from langgraph.graph import StateGraph


async def call_model(state):
    return state


def route_model_output(state) -> Literal["__end__", "tools"]:
    return "tools"


builder = StateGraph(dict)
builder.add_node(call_model)
builder.add_node("tools", ToolNode(TOOLS))
builder.add_edge("__start__", "call_model")
builder.add_conditional_edges(
    "call_model",
    # comments between the arguments are common
    route_model_output,
)
builder.add_edge("tools", "call_model")
'''


def test_langgraph_bare_nodes_and_literal_router():
    out = pl.build_pipeline(store({"src/graph.py": REACT}))
    assert [x["id"] for x in out["stages"]] == ["__start__", "call_model", "tools", "__end__"]
    links = {(x["from"], x["to"]): x for x in out["links"]}
    assert set(links) == {("__start__", "call_model"), ("call_model", "__end__"), ("call_model", "tools"),
                          ("tools", "call_model")}
    assert links[("tools", "call_model")]["loop"] and links[("call_model", "tools")]["label"] == "route_model_output"


def test_github_actions_jobs_and_needs():
    s = store({".github/workflows/ci.yml": WORKFLOW})
    out = pl.build_pipeline(s)
    assert out["source"] == "GitHub Actions (ci.yml)"
    assert [x["id"] for x in out["stages"]] == ["test", "build", "deploy"]
    assert {(x["from"], x["to"]) for x in out["links"]} == {("test", "build"), ("test", "deploy"), ("build", "deploy")}
    assert all(x["type"] == "job" for x in out["stages"])


def test_sklearn_pipeline_steps():
    out = pl.build_pipeline(store({"train.py": SKLEARN}))
    assert [x["id"] for x in out["stages"]] == ["scale", "classify"]
    assert out["stages"][-1]["type"] == "model" and out["kind"] == "ml"


def test_model_map_keeps_only_cited_stages(monkeypatch):
    src = {"rag/answer.py": "def retrieve(q):\n    return index.similarity_search(q)\n\n\n"
                            "def answer(q):\n    docs = retrieve(q)\n    return openai.chat.completions.create(q, docs)\n"}
    s = store(src)
    monkeypatch.setattr(pl.llm, "can_use", lambda override=None: True)
    monkeypatch.setattr(pl.llm, "complete_json", lambda *a, **k: {
        "kind": "rag", "title": "Answer with retrieval", "summary": "Search, then answer [rag/answer.py:5-7].",
        "stages": [
            {"id": "retrieve", "name": "Search", "type": "retriever", "description": "Finds docs [rag/answer.py:1-2].",
             "narration": "First it searches `the index` [rag/answer.py:1-2]."},
            {"id": "answer", "name": "Answer", "type": "llm", "description": "Writes the reply [answer.py:5-7]."},
            {"id": "ghost", "name": "Ghost", "type": "tool", "description": "Does not exist [nope.py:1-3]."},
            {"id": "weird", "name": "Weird", "type": "spaceship", "description": "Odd type [rag/answer.py:6-6]."},
        ],
        "links": [{"from": "retrieve", "to": "answer", "label": "documents"},
                  {"from": "answer", "to": "ghost"}, {"from": "answer", "to": "retrieve", "label": "retry"}]})
    out = pl.build_pipeline(s)
    assert out["mode"] == "llm" and out["kind"] == "rag"
    assert out["stages"][0]["narration"] == "First it searches the index."  # said aloud: no code marks
    assert [x["id"] for x in out["stages"]] == ["retrieve", "answer", "weird"]  # no citation, no stage
    assert out["stages"][1]["cite"]["file"] == "rag/answer.py"  # short path resolved
    assert out["stages"][2]["type"] == "transform"  # unknown types fall back
    links = {(x["from"], x["to"]): x for x in out["links"]}
    assert ("answer", "ghost") not in links and links[("answer", "retrieve")]["loop"]
    assert links[("retrieve", "answer")]["label"] == "documents"


def test_nothing_found_without_model_or_declaration():
    out = pl.build_pipeline(store({"util.py": "def add(a, b):\n    return a + b\n"}))
    assert not out["found"] and out["stages"] == []


def test_pipeline_endpoint_needs_sign_in(client):
    assert client.post("/api/pipeline", json={"repo_id": "missing"}).status_code == 401
