"""Auth routes — password, email one-time code, Google sign-in; all return a JWT.

- Email OTP: /otp/request mails a 6-digit code (only an HMAC of it is stored);
  /otp/verify exchanges it for a session. Codes expire, allow 5 tries, and requests
  are throttled per address.
- Google: the browser gets an ID token from Google Identity Services; /google verifies
  its signature against Google's keys and audience (GOOGLE_CLIENT_ID).
"""
import hashlib
import hmac
import logging
import re
import secrets
import time

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..dbmodels import EmailOtp, User
from ..guards import enforce, ip_limit
from ..mailer import MailError, mail_configured, otp_email, send_mail
from ..models import GoogleAuth, LoginRequest, OtpRequest, OtpVerify, Token, UserCreate, UserOut
from ..security import (create_access_token, get_current_user, hash_password,
                        verify_password)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60
OTP_MAX_PER_HOUR = 5
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
_google_keys = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", cache_keys=True)


def _out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name or "",
                   created_at=str(user.created_at or ""))


# Per-IP limits on the unauthenticated routes: stop password guessing, account
# spraying, and using our Gmail sender to mail-bomb people (Gmail caps us at ~500/day).
@router.post("/register", response_model=Token, status_code=201,
             dependencies=[Depends(ip_limit("auth-register", 5)), Depends(ip_limit("auth-register-h", 30, 3600))])
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


@router.post("/login", response_model=Token, dependencies=[Depends(ip_limit("auth-login", 10))])
def login(body: LoginRequest, request: Request, db: Session = Depends(get_session)):
    email = body.email.strip().lower()
    enforce(request, "auth-login-email", 20, 900, who=email)  # guessing one account from many IPs
    user = db.query(User).filter(User.email == email).first()
    if user and not user.password_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "this account signs in with an email code or Google")
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account deactivated")
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _out(user)


@router.get("/config")
def auth_config():
    """Which sign-in methods this server offers (the web app hides the rest)."""
    return {"google_client_id": settings.google_client_id or None,
            "email_otp": mail_configured() or not settings.is_production,
            "password": True}


def _email(raw: str) -> str:
    email = raw.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "enter a valid email address")
    return email


def _purpose(p: str) -> str:
    if p not in ("login", "signup"):
        raise HTTPException(422, "purpose must be login or signup")
    return p


def _code_hash(email: str, code: str) -> str:
    return hmac.new(settings.jwt_secret_key.encode(), f"{email}:{code}".encode(),
                    hashlib.sha256).hexdigest()


def _session_for(user: User) -> Token:
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account deactivated")
    return Token(access_token=create_access_token(user.id))


@router.post("/otp/request", dependencies=[Depends(ip_limit("otp-request", 5)),
                                           Depends(ip_limit("otp-request-h", 20, 3600))])
def otp_request(body: OtpRequest, db: Session = Depends(get_session)):
    email, purpose = _email(body.email), _purpose(body.purpose)
    exists = db.query(User).filter(User.email == email).first() is not None
    if purpose == "login" and not exists:
        raise HTTPException(404, "no account with this email — sign up first")
    if purpose == "signup" and exists:
        raise HTTPException(409, "an account with this email already exists — sign in instead")
    now = time.time()
    recent = db.query(EmailOtp).filter(EmailOtp.email == email,
                                       EmailOtp.created_at > now - 3600).all()
    last = max((o.created_at for o in recent), default=0)
    if now - last < OTP_RESEND_SECONDS:
        raise HTTPException(429, f"wait {int(OTP_RESEND_SECONDS - (now - last)) + 1}s before asking for another code")
    if len(recent) >= OTP_MAX_PER_HOUR:
        raise HTTPException(429, "too many codes requested for this email; try again in an hour")
    for o in recent:  # only the newest code is valid
        o.consumed = 1
    code = f"{secrets.randbelow(10 ** 6):06d}"
    db.add(EmailOtp(email=email, purpose=purpose, name=body.name.strip()[:120],
                    code_hash=_code_hash(email, code), expires_at=now + settings.otp_ttl_seconds,
                    created_at=now))
    minutes = settings.otp_ttl_seconds // 60
    if mail_configured():
        try:
            send_mail(email, *otp_email(code, purpose, minutes, email))
        except MailError:
            db.rollback()
            raise HTTPException(502, "couldn't send the email right now; try again in a minute")
    elif settings.is_production:
        db.rollback()
        raise HTTPException(503, "email sign-in is not configured on this server")
    else:
        log.warning("otp: SMTP not configured — DEV ONLY code for %s is %s", email, code)
    db.commit()
    return {"sent": True, "expires_in": settings.otp_ttl_seconds, "resend_in": OTP_RESEND_SECONDS}


@router.post("/otp/verify", response_model=Token, dependencies=[Depends(ip_limit("otp-verify", 15))])
def otp_verify(body: OtpVerify, db: Session = Depends(get_session)):
    email, purpose = _email(body.email), _purpose(body.purpose)
    code = re.sub(r"\D", "", body.code)
    otp = (db.query(EmailOtp).filter(EmailOtp.email == email, EmailOtp.purpose == purpose,
                                     EmailOtp.consumed == 0)
           .order_by(EmailOtp.created_at.desc()).first())
    if otp is None or otp.expires_at < time.time():
        raise HTTPException(400, "this code has expired — request a new one")
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "too many wrong codes — request a new one")
    if not hmac.compare_digest(otp.code_hash, _code_hash(email, code)):
        otp.attempts += 1
        left = OTP_MAX_ATTEMPTS - otp.attempts
        db.commit()
        raise HTTPException(400, f"wrong code — {left} {'try' if left == 1 else 'tries'} left"
                            if left else "too many wrong codes — request a new one")
    otp.consumed = 1
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        if purpose == "login":
            db.commit()
            raise HTTPException(404, "no account with this email — sign up first")
        user = User(email=email, name=otp.name or email.split("@")[0], password_hash="",
                    email_verified=1)
        db.add(user)
    else:
        user.email_verified = 1
    db.commit()
    db.refresh(user)
    log.info("auth: %s via email code (%s)", purpose, user.id)
    return _session_for(user)


def _verify_google(credential: str) -> dict:
    if not settings.google_client_id:
        raise HTTPException(503, "Google sign-in is not configured on this server")
    try:
        key = _google_keys.get_signing_key_from_jwt(credential)
        claims = jwt.decode(credential, key.key, algorithms=["RS256"],
                            audience=settings.google_client_id, issuer=GOOGLE_ISSUERS)
    except jwt.PyJWKClientError as e:
        log.warning("google: could not fetch signing keys (%s)", e)
        raise HTTPException(502, "couldn't reach Google to verify the sign-in; try again")
    except jwt.InvalidTokenError as e:
        log.info("google: rejected ID token (%s)", e)
        raise HTTPException(401, "Google sign-in could not be verified")
    if not claims.get("email") or not claims.get("email_verified"):
        raise HTTPException(401, "your Google account has no verified email")
    return claims


@router.post("/google", response_model=Token, dependencies=[Depends(ip_limit("auth-google", 20))])
def google(body: GoogleAuth, db: Session = Depends(get_session)):
    """Sign in or sign up with a Google ID token (same endpoint for both)."""
    claims = _verify_google(body.credential)
    email = claims["email"].strip().lower()
    user = db.query(User).filter(User.google_sub == claims["sub"]).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email, name=(claims.get("name") or email.split("@")[0])[:120],
                        password_hash="")
            db.add(user)
            log.info("auth: new account via Google")
        user.google_sub = claims["sub"]  # link Google to an existing email account
    user.email_verified = 1
    db.commit()
    db.refresh(user)
    return _session_for(user)
