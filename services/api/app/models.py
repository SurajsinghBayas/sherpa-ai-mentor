"""Pydantic schemas — the API contract shared with the web app."""
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class IngestRequest(BaseModel):
    repo_url: Optional[str] = None
    local_path: Optional[str] = None
    branch: str = ""  # blank = the repo's default branch


class IngestResponse(BaseModel):
    repo_id: str
    name: str = ""
    files: int
    chunks: int
    changes: dict = Field(default_factory=dict)


class SyncRequest(BaseModel):
    repo_id: str
    refresh_docs: bool = True


class DocsRequest(BaseModel):
    repo_id: str
    key_id: Optional[str] = None
    endpoint_id: Optional[str] = None


class Citation(BaseModel):
    file: str
    start_line: int
    end_line: int
    snippet: str = ""


class AskRequest(BaseModel):
    repo_id: str
    question: str
    history: List[dict] = Field(default_factory=list)
    # SaaS overrides: use one of the caller's stored credentials for this answer.
    key_id: Optional[str] = None       # ProviderKey id (their own OpenAI/Anthropic/Gemini key)
    endpoint_id: Optional[str] = None  # CustomEndpoint id (any OpenAI-compatible / Ollama URL)


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
    refresh: bool = False
    key_id: Optional[str] = None
    endpoint_id: Optional[str] = None


class Component(BaseModel):
    name: str
    path: str
    role: str


class Edge(BaseModel):
    source: str = Field(alias="from")
    target: str = Field(alias="to")
    via: str = ""

    model_config = ConfigDict(populate_by_name=True)


class OverviewResponse(BaseModel):
    components: List[Component]
    edges: List[Edge]
    mermaid: str
    summary: str


class TourRequest(BaseModel):
    repo_id: str
    flow: str = "user signup"
    key_id: Optional[str] = None
    endpoint_id: Optional[str] = None


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
    refresh: bool = False
    key_id: Optional[str] = None
    endpoint_id: Optional[str] = None


class StarterTask(BaseModel):
    title: str
    why: str
    files: List[dict]
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


# ---------- SaaS: auth ----------

class UserCreate(BaseModel):
    name: str = ""
    email: str
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    created_at: str = ""


class OtpRequest(BaseModel):
    email: str = Field(max_length=320)
    purpose: str = "login"  # login | signup
    name: str = Field("", max_length=120)


class OtpVerify(BaseModel):
    email: str = Field(max_length=320)
    code: str = Field(max_length=12)
    purpose: str = "login"


class GoogleAuth(BaseModel):
    credential: str = Field(max_length=4096)  # Google Identity Services ID token


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- SaaS: user-owned LLM credentials ----------

class ProviderKeyCreate(BaseModel):
    label: str = ""
    provider: str  # openai | anthropic | gemini | openrouter
    model: str = ""
    api_key: str = Field(min_length=4, max_length=500)


class ProviderKeyOut(BaseModel):
    id: str
    label: str
    provider: str
    model: str
    last4: str = ""
    created_at: str = ""


class CustomEndpointCreate(BaseModel):
    name: str = ""
    base_url: str  # e.g. https://my-gateway.internal/v1 or http://localhost:11434
    kind: str = "openai-compatible"  # openai-compatible | ollama
    model: str = ""
    api_key: str = ""  # optional (Ollama needs none)


class CustomEndpointOut(BaseModel):
    id: str
    name: str
    base_url: str
    kind: str
    model: str
    has_key: bool = False
    created_at: str = ""


# ---------- user study ----------

class StudyResultCreate(BaseModel):
    participant: str = Field(min_length=1, max_length=60)  # pseudonym, e.g. P3
    group: str            # control | sherpa
    task: str             # architecture | flow | starter
    repo: str = ""
    seconds: float
    score: float = 0
    useful: int = Field(default=0, ge=0, le=5)
    trustworthy: int = Field(default=0, ge=0, le=5)
    reuse: int = Field(default=0, ge=0, le=5)
    notes: str = ""
