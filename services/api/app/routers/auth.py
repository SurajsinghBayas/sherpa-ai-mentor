"""Auth routes — register / login / me (JWT Bearer)."""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_session
from ..dbmodels import User
from ..models import LoginRequest, Token, UserCreate, UserOut
from ..security import (create_access_token, get_current_user, hash_password,
                        verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name or "",
                   created_at=str(user.created_at or ""))


@router.post("/register", response_model=Token, status_code=201)
def register(body: UserCreate, db: Session = Depends(get_session)):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "enter a valid email address")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "an account with this email already exists")
    user = User(email=email, name=body.name.strip()[:120],
                password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return Token(access_token=create_access_token(user.id))


@router.post("/login", response_model=Token)
def login(body: LoginRequest, db: Session = Depends(get_session)):
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account deactivated")
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _out(user)
