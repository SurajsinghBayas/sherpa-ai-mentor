"""Newcomer user study — record timed tasks for control vs Sherpa groups and summarise.

Participants are pseudonymous (P1, P2 …). Only signed-in facilitators can write or read.
"""
import csv
import io
import statistics

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..db import get_session
from ..dbmodels import StudyResult, User
from ..models import StudyResultCreate
from ..security import get_current_user

router = APIRouter(prefix="/api/study", tags=["study"])

TASKS = {
    "architecture": {"title": "Map the architecture",
                     "prompt": "Name the 3-5 main parts of the system and draw how they connect.",
                     "max_score": 3},
    "flow": {"title": "Explain the signup flow",
             "prompt": "Explain what happens when a user signs up: name the files involved, in order.",
             "max_score": 4},
    "starter": {"title": "Plan a first contribution",
                "prompt": "Pick a starter task and write a concrete plan: files to change and how to test.",
                "max_score": 2},
}


def _row(r: StudyResult) -> dict:
    return {"id": r.id, "participant": r.participant, "group": r.group, "task": r.task,
            "repo": r.repo, "seconds": r.seconds, "score": r.score, "max_score": r.max_score,
            "useful": r.useful, "trustworthy": r.trustworthy, "reuse": r.reuse,
            "notes": r.notes, "created_at": str(r.created_at or "")}


@router.get("/protocol")
def protocol():
    return {"tasks": TASKS, "groups": ["control", "sherpa"],
            "rubric": "Score against the maintainer's reference answer; record time to first correct answer."}


@router.post("/results", status_code=201)
def add_result(body: StudyResultCreate, user: User = Depends(get_current_user),
               db: Session = Depends(get_session)):
    if body.group not in ("control", "sherpa"):
        raise HTTPException(422, "group must be control or sherpa")
    if body.task not in TASKS:
        raise HTTPException(422, f"task must be one of {sorted(TASKS)}")
    if body.seconds <= 0 or body.seconds > 4 * 3600:
        raise HTTPException(422, "seconds must be between 1 and 14400")
    max_score = TASKS[body.task]["max_score"]
    if not 0 <= body.score <= max_score:
        raise HTTPException(422, f"score must be between 0 and {max_score}")
    r = StudyResult(recorded_by=user.id, participant=body.participant.strip()[:60] or "P?",
                    group=body.group, task=body.task, repo=body.repo.strip()[:200],
                    seconds=body.seconds, score=body.score, max_score=max_score,
                    useful=body.useful, trustworthy=body.trustworthy, reuse=body.reuse,
                    notes=body.notes.strip()[:2000])
    db.add(r)
    db.commit()
    db.refresh(r)
    return _row(r)


@router.get("/results")
def list_results(user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    rows = (db.query(StudyResult).filter(StudyResult.recorded_by == user.id)
            .order_by(StudyResult.created_at.asc()).all())
    return [_row(r) for r in rows]


@router.delete("/results/{result_id}", status_code=204)
def delete_result(result_id: str, user: User = Depends(get_current_user),
                  db: Session = Depends(get_session)):
    r = db.query(StudyResult).filter(StudyResult.id == result_id,
                                     StudyResult.recorded_by == user.id).first()
    if not r:
        raise HTTPException(404, "result not found")
    db.delete(r)
    db.commit()


@router.get("/summary")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    rows = db.query(StudyResult).filter(StudyResult.recorded_by == user.id).all()
    out = []
    for task in TASKS:
        entry = {"task": task, "title": TASKS[task]["title"], "max_score": TASKS[task]["max_score"]}
        for g in ("control", "sherpa"):
            rs = [r for r in rows if r.task == task and r.group == g]
            entry[g] = {
                "n": len(rs),
                "mean_minutes": round(statistics.mean(r.seconds for r in rs) / 60, 1) if rs else None,
                "median_minutes": round(statistics.median(r.seconds for r in rs) / 60, 1) if rs else None,
                "mean_score": round(statistics.mean(r.score for r in rs), 2) if rs else None,
            }
        c, s = entry["control"]["mean_minutes"], entry["sherpa"]["mean_minutes"]
        entry["time_saved_pct"] = round(100 * (c - s) / c) if c and s is not None else None
        out.append(entry)
    sher = [r for r in rows if r.group == "sherpa" and r.useful]
    sus = {k: round(statistics.mean(getattr(r, k) for r in sher), 1) if sher else None
           for k in ("useful", "trustworthy", "reuse")}
    return {"tasks": out, "satisfaction": sus,
            "participants": {g: len({r.participant for r in rows if r.group == g})
                             for g in ("control", "sherpa")}}


@router.get("/results.csv", response_class=PlainTextResponse)
def export_csv(user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    rows = db.query(StudyResult).filter(StudyResult.recorded_by == user.id).all()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["participant", "group", "task", "repo", "seconds", "score",
                                        "max_score", "useful", "trustworthy", "reuse", "notes", "created_at"])
    w.writeheader()
    for r in rows:
        w.writerow({k: v for k, v in _row(r).items() if k != "id"})
    return buf.getvalue()
