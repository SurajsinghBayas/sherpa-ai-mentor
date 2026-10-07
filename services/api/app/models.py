"""Pydantic schemas — the API contract shared with the web app."""
from typing import List, Optional
from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    repo_url: Optional[str] = None
    local_path: Optional[str] = None
    branch: str = "main"


class IngestResponse(BaseModel):
    repo_id: str
    files: int
    chunks: int


class Citation(BaseModel):
    file: str
    start_line: int
    end_line: int
    snippet: str = ""


class AskRequest(BaseModel):
    repo_id: str
    question: str
    history: List[dict] = Field(default_factory=list)


class VerifyReport(BaseModel):
    grounded: bool
    unchecked_claims: List[str] = Field(default_factory=list)


class AskResponse(BaseModel):
    answer_markdown: str
    citations: List[Citation]
    confidence: float
    verify: VerifyReport


class OverviewRequest(BaseModel):
    repo_id: str


class Component(BaseModel):
    name: str
    path: str
    role: str


class Edge(BaseModel):
    source: str = Field(alias="from")
    target: str = Field(alias="to")
    via: str = ""

    class Config:
        populate_by_name = True


class OverviewResponse(BaseModel):
    components: List[Component]
    edges: List[Edge]
    mermaid: str
    summary: str


class TourRequest(BaseModel):
    repo_id: str
    flow: str = "user signup"


class TourStep(BaseModel):
    caption: str
    file: str
    start_line: int
    end_line: int
    code: str = ""


class TourResponse(BaseModel):
    title: str
    estimated_minutes: int = 8
    steps: List[TourStep]


class TaskRequest(BaseModel):
    repo_id: str
    level: str = "beginner"


class StarterTask(BaseModel):
    title: str
    why: str
    files: List[str]
    steps: List[str]
    difficulty: str = "easy"


class TaskResponse(BaseModel):
    tasks: List[StarterTask]


class FreshnessRequest(BaseModel):
    repo_id: str
    docs_markdown: str


class StaleSection(BaseModel):
    heading: str
    reason: str
    suggested_update: str


class FreshnessResponse(BaseModel):
    stale_sections: List[StaleSection]
    fresh: bool
