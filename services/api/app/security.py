"""Auth + secrets: bcrypt passwords, JWT sessions, Fernet key encryption."""
import base64
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .db import get_session

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


# ---------- passwords ----------

def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_ctx.verify(password, password_hash)


# ---------- JWT ----------

def create_access_token(sub: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": sub, "exp": exp},
                      settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key,
                             algorithms=[settings.jwt_algorithm])
        return str(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired, sign in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid session token")


def _user_from_token(db: Session, token: str):
    from .dbmodels import User
    user = db.get(User, decode_token(token))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account inactive")
    return user


def get_current_user(db: Session = Depends(get_session),
                     creds: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    """Required auth — 401 when no/invalid Bearer token."""
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in required")
    return _user_from_token(db, creds.credentials)


def get_optional_user(db: Session = Depends(get_session),
                      creds: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    """Optional auth — returns None for anonymous callers (demo stays open)."""
    if creds is None or not creds.credentials:
        return None
    try:
        return _user_from_token(db, creds.credentials)
    except HTTPException:
        return None


# ---------- per-user secret encryption ----------

def _fernet() -> Fernet:
    raw = (settings.encryption_key or "").strip()
    if raw:
        key = raw.encode()
    else:
        # deterministic dev fallback derived from the JWT secret (set ENCRYPTION_KEY in prod)
        digest = hashlib.sha256(f"sherpa-enc:{settings.jwt_secret_key}".encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "cannot decrypt stored key (ENCRYPTION_KEY rotated?)")
