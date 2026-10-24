"""The signed-in user's profile: name, how they sign in, linked Google/GitHub accounts, and usage."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..dbmodels import QuizAttempt, Repo, UsageCounter, User
from ..guards import ip_limit
from ..mailer import mail_configured
from ..models import GoogleAuth, ProfileUpdate
from ..security import get_current_user
from .auth import _verify_google

router = APIRouter(prefix="/api/profile", tags=["profile"])
NOREPLY = "@users.noreply.github.com"


def _email_code(user: User) -> bool:
    """Can this account sign in with an emailed code? Not for GitHub's no-reply addresses."""
    return not user.email.endswith(NOREPLY) and (mail_configured() or not settings.is_production)


def _ways(user: User) -> dict:
    return {"password": bool(user.password_hash), "email_code": _email_code(user),
            "google": bool(user.google_sub), "github": user.github_login if user.github_id else None}


def _profile(user: User, db: Session) -> dict:
    repos = db.query(func.count(Repo.id), func.coalesce(func.sum(Repo.files_count), 0)) \
        .filter(Repo.owner_id == user.id).one()
    attempts = db.query(QuizAttempt.correct, QuizAttempt.total).filter(QuizAttempt.user_id == user.id).all()
    scores = [round(100 * c / t) for c, t in attempts if t]
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    used = dict(db.query(UsageCounter.kind, UsageCounter.count)
                .filter(UsageCounter.user_id == user.id, UsageCounter.day == day).all())
    return {
        "id": user.id, "name": user.name or "", "email": user.email,
        "email_verified": bool(user.email_verified), "noreply_email": user.email.endswith(NOREPLY),
        "created_at": user.created_at.isoformat() if user.created_at else "",
        "sign_in": _ways(user),
        "stats": {"repos": repos[0], "files": int(repos[1]), "quizzes": len(scores),
                  "best_score": max(scores, default=None),
                  "average_score": round(sum(scores) / len(scores)) if scores else None},
        "today": {"llm": used.get("llm", 0), "llm_limit": settings.daily_llm_requests,
                  "ingest": used.get("ingest", 0), "ingest_limit": settings.daily_ingests},
    }


@router.get("")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    return _profile(user, db)


@router.post("")
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    name = " ".join(body.name.split())
    if not name:
        raise HTTPException(422, "enter a name")
    user.name = name[:120]
    db.commit()
    return _profile(user, db)


@router.post("/google", dependencies=[Depends(ip_limit("profile-google", 10))])
def link_google(body: GoogleAuth, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    """Connect a Google account to this one, whatever its email."""
    claims = _verify_google(body.credential)
    owner = db.query(User).filter(User.google_sub == claims["sub"]).first()
    if owner is not None and owner.id != user.id:
        raise HTTPException(409, "this Google account is already connected to another Sherpa account")
    user.google_sub = claims["sub"]
    db.commit()
    return _profile(user, db)


@router.delete("/{provider}")
def unlink(provider: str, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    """Disconnect Google or GitHub, unless it is the only way left to sign in."""
    if provider not in ("google", "github"):
        raise HTTPException(404, "unknown provider")
    ways = _ways(user)
    ways[provider] = None
    if not any(ways.values()):
        raise HTTPException(409, f"{provider.title() if provider == 'google' else 'GitHub'} is your only way to sign in; "
                                 "set a password or connect another account first")
    if provider == "google":
        user.google_sub = None
    else:
        user.github_id = None
        user.github_login = None
    db.commit()
    return _profile(user, db)
