"""Upload a codebase from the user's device: ZIP, a folder (zipped in the browser), or the CLI.

POST   /api/uploads                 multipart `file` (a .zip) + optional `name`, `origin`
                                     → job in `review` with a manifest; nothing indexed yet
POST   /api/uploads/{job}/start      confirm (or retry a failed job, no re-upload) → `queued`
GET    /api/uploads/{job}            status, stage, progress (poll this)
GET    /api/uploads                  your recent jobs
DELETE /api/uploads/{job}            discard a job that isn't running
"""
import logging
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..dbmodels import IngestJob, Repo, User
from ..guards import enforce
from ..ingest import IngestError
from ..security import get_current_user
from .. import uploads as up

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/uploads", tags=["uploads"])

KEEP_PAYLOAD = 24 * 3600  # unconfirmed / failed uploads keep their files this long


def _job(db: Session, job_id: str, user: User) -> IngestJob:
    job = db.get(IngestJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "upload not found")
    if up.mark_if_stale(job):
        db.commit()
    return job


def _purge(db: Session, user: User) -> None:
    """Drop the stored files of old unconfirmed/failed uploads (the job record stays)."""
    cutoff = time.time() - KEEP_PAYLOAD
    for j in db.query(IngestJob).filter(IngestJob.user_id == user.id,
                                        IngestJob.payload.isnot(None),
                                        IngestJob.status.in_(("review", "failed")),
                                        IngestJob.updated_at < cutoff):
        j.payload = None
        if j.status == "review":
            j.status, j.detail = "failed", "expired before it was confirmed; upload again"
    db.commit()


@router.post("", status_code=201)
def create_upload(request: Request, file: UploadFile = File(...), name: str = Form(""),
                  origin: str = Form("zip"), user: User = Depends(get_current_user),
                  db: Session = Depends(get_session)):
    enforce(request, "upload", 10, 60, who=user.id)
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"the upload is over {settings.max_upload_mb} MB; leave out "
                                 "build output and dependencies (node_modules, dist, .git)")
    if not data:
        raise HTTPException(422, "the upload is empty")
    fallback = (file.filename or "").rsplit("/", 1)[-1]
    fallback = fallback[:-4] if fallback.lower().endswith(".zip") else fallback
    try:
        sources, manifest = up.read_zip(data, name.strip()[:120])
    except IngestError as e:
        raise HTTPException(422, str(e))
    if not name.strip() and manifest["name"] == "uploaded-project" and fallback:
        manifest["name"] = fallback[:120]
    _purge(db, user)
    repo_id = up.upload_repo_id(user.id, manifest["name"])
    existing = db.get(Repo, repo_id)
    now = time.time()
    job = IngestJob(user_id=user.id, repo_id=repo_id, name=manifest["name"],
                    origin=origin if origin in ("zip", "folder", "cli") else "zip",
                    status="review", stage="review", progress=0, manifest=manifest,
                    payload=up.pack(sources), created_at=now, updated_at=now)
    db.add(job)
    db.commit()
    log.info("upload %s: %s (%s) %d files, %d skipped", job.id, manifest["name"], job.origin,
             manifest["file_count"], manifest["skipped_count"])
    return {**up.job_out(job), "updates_existing": existing is not None and existing.owner_id == user.id}


@router.post("/{job_id}/start")
def start_upload(job_id: str, request: Request, user: User = Depends(get_current_user),
                 db: Session = Depends(get_session)):
    """Confirm a reviewed upload, or retry a failed one with the files already stored."""
    from ..main import _charge  # quotas live with the other routes
    enforce(request, "upload-start", 10, 60, who=user.id)
    job = _job(db, job_id, user)
    if job.status not in ("review", "failed"):
        raise HTTPException(409, f"this upload is already {job.status}")
    if not job.payload:
        raise HTTPException(410, "the uploaded files have expired; upload again")
    running = [j for j in db.query(IngestJob).filter(IngestJob.user_id == user.id,
                                                     IngestJob.status.in_(("queued", "processing")))
               if not up.mark_if_stale(j)]
    db.commit()
    if running:
        raise HTTPException(409, "another upload is still indexing; wait for it to finish")
    if db.get(Repo, job.repo_id) is None:
        owned = db.query(Repo).filter(Repo.owner_id == user.id).count()
        if owned >= settings.max_repos_per_user:
            raise HTTPException(429, f"repo limit reached ({settings.max_repos_per_user}); "
                                     "delete one before adding another")
    _charge(db, user, "ingest")
    # conditional update: two clicks (or tabs) can't both queue the same job
    claimed = (db.query(IngestJob)
               .filter(IngestJob.id == job_id, IngestJob.status.in_(("review", "failed")))
               .update({IngestJob.status: "queued", IngestJob.stage: "queued", IngestJob.progress: 0,
                        IngestJob.detail: "", IngestJob.attempts: IngestJob.attempts + 1,
                        IngestJob.updated_at: time.time()}, synchronize_session=False))
    db.commit()
    if claimed != 1:
        raise HTTPException(409, "this upload was started already")
    up.submit(job_id)
    db.expire_all()
    return up.job_out(db.get(IngestJob, job_id))


@router.get("/{job_id}")
def get_upload(job_id: str, user: User = Depends(get_current_user),
               db: Session = Depends(get_session)):
    return up.job_out(_job(db, job_id, user))


@router.get("")
def list_uploads(user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    jobs = (db.query(IngestJob).filter(IngestJob.user_id == user.id)
            .order_by(IngestJob.created_at.desc()).limit(20).all())
    if any(up.mark_if_stale(j) for j in jobs):
        db.commit()
    return {"uploads": [up.job_out(j) for j in jobs]}


@router.delete("/{job_id}", status_code=204)
def discard_upload(job_id: str, user: User = Depends(get_current_user),
                   db: Session = Depends(get_session)):
    job = _job(db, job_id, user)
    if job.status in ("queued", "processing"):
        raise HTTPException(409, "can't discard an upload while it is indexing")
    db.delete(job)
    db.commit()
