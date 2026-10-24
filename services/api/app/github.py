"""GitHub: sign-in through a GitHub App's user authorization, and a signed-in user's public repos.

Sign-in is GitHub's web flow. /api/auth/github/start issues a signed `state` and the authorize
URL; GitHub sends the browser back to the web app's /auth/github/callback with a one-time code;
/api/auth/github swaps it for a user token, reads the profile and verified emails, and returns a
Sherpa session. The GitHub token is used for that one request and never stored.

Public repos are read with the app's client ID and secret (a higher rate limit than anonymous
calls, and no user token to keep), and cached for a few minutes per account.
"""
import logging
import re
import secrets
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException

from .config import settings

log = logging.getLogger(__name__)

API = "https://api.github.com"
AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
CALLBACK_PATH = "/auth/github/callback"  # the web app's page; register <web origin>/auth/github/callback
STATE_TTL = 600
STATE_AUD = "github-state"  # an audience, so a state can never pass as a session token
REPOS_TTL = 300
MAX_PAGES = 3  # 300 most recently pushed repos
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "sherpa-ai-mentor"}
_repos: Dict[str, Tuple[float, List[dict]]] = {}


def configured() -> bool:
    return bool(settings.github_client_id and settings.github_client_secret)


def _allowed_redirect(uri: str) -> bool:
    if not uri.endswith(CALLBACK_PATH):
        return False
    origin = uri[: -len(CALLBACK_PATH)]
    origins = [o.strip().rstrip("/") for o in settings.allowed_origins.split(",") if o.strip()]
    return origin in origins or ("*" in origins and re.match(r"^https?://[^/]+$", origin) is not None)


def start(redirect_uri: str, link_user_id: Optional[str] = None) -> dict:
    """The authorize URL and its state. With link_user_id, the callback links GitHub to that account."""
    if not configured():
        raise HTTPException(503, "GitHub sign-in is not configured on this server")
    if not _allowed_redirect(redirect_uri):
        raise HTTPException(422, "redirect_uri must be <one of this server's web origins>" + CALLBACK_PATH)
    state = jwt.encode({"aud": STATE_AUD, "n": secrets.token_urlsafe(16), "r": redirect_uri,
                        "u": link_user_id, "exp": int(time.time()) + STATE_TTL},
                       settings.jwt_secret_key, algorithm="HS256")
    query = urlencode({"client_id": settings.github_client_id, "redirect_uri": redirect_uri, "state": state})
    return {"url": f"{AUTHORIZE_URL}?{query}", "state": state}


def check_state(state: str, redirect_uri: str) -> Optional[str]:
    """Verify a state from start(); returns the account to link, if any."""
    try:
        claims = jwt.decode(state, settings.jwt_secret_key, algorithms=["HS256"], audience=STATE_AUD)
    except jwt.InvalidTokenError:
        raise HTTPException(400, "this GitHub sign-in has expired; try again")
    if claims.get("r") != redirect_uri:
        raise HTTPException(400, "GitHub sign-in came back to an unexpected address")
    return claims.get("u")


def profile(code: str, redirect_uri: str) -> dict:
    """Swap the code for a user token and read who it belongs to: id, login, name, verified emails."""
    if not configured():
        raise HTTPException(503, "GitHub sign-in is not configured on this server")
    try:
        with httpx.Client(timeout=10, headers=_HEADERS) as c:
            r = c.post(TOKEN_URL, headers={"Accept": "application/json"},
                       data={"client_id": settings.github_client_id,
                             "client_secret": settings.github_client_secret,
                             "code": code, "redirect_uri": redirect_uri})
            token = r.json().get("access_token") if r.status_code == 200 else None
            if not token:
                log.info("github: code exchange refused (%s)", r.status_code == 200 and r.json().get("error"))
                raise HTTPException(401, "GitHub sign-in could not be verified; try again")
            auth = {"Authorization": f"Bearer {token}"}
            u = c.get(f"{API}/user", headers=auth)
            u.raise_for_status()
            user = u.json()
            e = c.get(f"{API}/user/emails", headers=auth)  # needs the app's "Email addresses: read" permission
            emails = e.json() if e.status_code == 200 else []
    except httpx.HTTPError as err:
        log.warning("github: sign-in request failed (%s)", err)
        raise HTTPException(502, "couldn't reach GitHub to finish signing in; try again")
    verified = [x["email"].strip().lower() for x in sorted(emails, key=lambda x: not x.get("primary"))
                if isinstance(x, dict) and x.get("verified") and x.get("email")]
    return {"id": str(user["id"]), "login": user["login"], "name": user.get("name") or user["login"],
            "emails": verified}


def _repo(x: dict) -> dict:
    return {"full_name": x["full_name"], "name": x["name"], "description": x.get("description") or "",
            "url": x["html_url"], "language": x.get("language") or "", "stars": x.get("stargazers_count", 0),
            "fork": bool(x.get("fork")), "archived": bool(x.get("archived")),
            "pushed_at": x.get("pushed_at") or "", "size_kb": x.get("size", 0)}


def _fetch_repos(login: str) -> List[dict]:
    out: List[dict] = []
    auth: Optional[Tuple[str, str]] = (settings.github_client_id, settings.github_client_secret) if configured() else None
    try:
        with httpx.Client(timeout=10, headers=_HEADERS) as c:
            for page in range(1, MAX_PAGES + 1):
                params = {"type": "owner", "sort": "pushed", "per_page": 100, "page": page}
                r = c.get(f"{API}/users/{login}/repos", params=params, auth=auth)
                if r.status_code == 401 and auth:  # app credentials refused: read anonymously instead
                    auth = None
                    r = c.get(f"{API}/users/{login}/repos", params=params)
                if r.status_code == 404:
                    raise HTTPException(404, f"GitHub has no account named {login}")
                if r.status_code in (403, 429):
                    raise HTTPException(429, "GitHub's rate limit was reached; try again in a few minutes")
                r.raise_for_status()
                batch = r.json()
                out += [_repo(x) for x in batch if not x.get("private")]
                if len(batch) < 100:
                    break
    except httpx.HTTPError as err:
        log.warning("github: listing repos for %s failed (%s)", login, err)
        raise HTTPException(502, "couldn't reach GitHub to list repositories; try again")
    return out


def public_repos(login: str, refresh: bool = False) -> List[dict]:
    """A GitHub account's own public repos, most recently pushed first."""
    if not LOGIN_RE.match(login):
        raise HTTPException(422, "not a GitHub username")
    key = login.lower()
    hit = _repos.get(key)
    if hit and not refresh and time.time() - hit[0] < REPOS_TTL:
        return hit[1]
    repos = _fetch_repos(login)
    if len(_repos) > 500:
        _repos.clear()
    _repos[key] = (time.time(), repos)
    return repos
