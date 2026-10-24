"""The signed-in user's GitHub repositories (public ones), ready to index in one click."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import github as gh
from ..db import get_session
from ..dbmodels import Repo, User
from ..guards import enforce
from ..security import get_current_user

router = APIRouter(prefix="/api/github", tags=["github"])


def _norm(url: str) -> str:
    return url.strip().rstrip("/").removesuffix(".git").lower()


@router.get("/repos")
def my_repos(request: Request, refresh: bool = False, user: User = Depends(get_current_user),
             db: Session = Depends(get_session)):
    """Public repos of the GitHub account linked to this user, marked when already indexed."""
    if not user.github_login:
        raise HTTPException(409, "connect your GitHub account to list your repositories")
    enforce(request, "github-repos", 20, 60, who=user.id)
    indexed = {_norm(r.source): r.id for r in db.query(Repo).filter(Repo.owner_id == user.id)}
    repos = gh.public_repos(user.github_login, refresh=refresh)
    return {"login": user.github_login,
            "repos": [{**r, "repo_id": indexed.get(_norm(r["url"]))} for r in repos]}
