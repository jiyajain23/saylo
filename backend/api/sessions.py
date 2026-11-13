"""
HTTP session routes — port of routes/sessions.ts.
Handles CRUD for sessions, transcript segments, analysis triggering, and progress analytics.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx
from cuid2 import cuid_wrapper
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db import get_db
from services.auth import Principal, current_user
from models.schemas import (
    AnalysisJob,
    CreateSegmentRequest,
    CreateSessionRequest,
    Session,
    TranscriptSegment,
    User,
)
from services.context import build_structured_context
from services.scenarios import (
    SCENARIOS,
    normalize_persona,
    normalize_pressure_level,
    normalize_scenario,
)
from utils.audio import audio_buffer_store
from utils.logger import logger
from services import completion
from services.jobs import enqueue, mark_uploaded
from services.limits import check_new_session, lock_owner, MAX_TRANSCRIPT_CHARS
from services.storage import AudioStorage, StorageError

router = APIRouter(prefix="/sessions", tags=["sessions"])

# CUID generator (compatible with Prisma's cuid())
cuid_generate = cuid_wrapper()

# ── Constants ──────────────────────────────────────────────────────────────────
SESSION_LIST_LIMIT = 100


# ── Helpers ────────────────────────────────────────────────────────────────────

_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def sanitize_text(value: str) -> str:
    """Strip ASCII control chars (except tab/newline/CR) to prevent injection."""
    return _CONTROL_RE.sub("", value).strip()


def _session_to_dict(s: Session, include_segments: bool = False, include_analysis: bool = False) -> dict:
    d: dict[str, Any] = {
        "id": s.id,
        "createdAt": s.createdAt.isoformat(),
        "updatedAt": s.updatedAt.isoformat(),
        "status": s.status,
        "scenario": s.scenario,
        "title": s.title,
        "persona": s.persona,
        "pressureLevel": s.pressureLevel,
    }
    if include_segments:
        d["segments"] = [
            {
                "id": seg.id,
                "sessionId": seg.sessionId,
                "createdAt": seg.createdAt.isoformat(),
                "speaker": seg.speaker,
                "text": seg.text,
                "audioStartSeconds": seg.audioStartSeconds,
                "audioEndSeconds": seg.audioEndSeconds,
            }
            for seg in sorted(s.segments, key=lambda x: x.createdAt)
        ]
    if include_analysis and s.analysis:
        ar = s.analysis
        d["analysis"] = {
            "id": ar.id,
            "sessionId": ar.sessionId,
            "createdAt": ar.createdAt.isoformat(),
            "speechMetrics": ar.speechMetrics,
            "nlpMetrics": ar.nlpMetrics,
            "alignment": ar.alignment,
            "confidence": ar.confidence,
            "highlights": ar.highlights,
            "strengths": ar.strengths,
            "weaknesses": ar.weaknesses,
            "suggestions": ar.suggestions,
            "voice": ar.voice,
            "emotion": ar.emotion,
            "vision": ar.vision,
            "jobs": ar.jobs,
            "errors": ar.errors,
            "insights": ar.insights,
            "scoring_version": ar.scoring_version,
        }
    return d


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/progress")
async def get_progress(db: AsyncSession = Depends(get_db), user: Principal = Depends(current_user)):
    """Aggregate analytics for the progress dashboard."""
    result = await db.execute(
        select(Session).where(Session.userId == user.id).options(selectinload(Session.analysis)).order_by(Session.createdAt.asc())
    )
    sessions = result.scalars().all()

    ready = [s for s in sessions if s.analysis and s.analysis.confidence is not None]

    confidence_trend = [
        {
            "sessionId": s.id,
            "title": s.title,
            "scenario": s.scenario,
            "createdAt": s.createdAt.isoformat(),
            "confidence": s.analysis.confidence,
        }
        for s in ready
    ]

    # Repeated issue counts across sessions
    issue_counts: dict[str, int] = {}
    for s in ready:
        weaknesses = s.analysis.weaknesses or []
        if isinstance(weaknesses, list):
            for w in weaknesses:
                if isinstance(w, str):
                    issue_counts[w] = issue_counts.get(w, 0) + 1

    # Per-scenario breakdown
    by_scenario = []
    for scenario in SCENARIOS:
        scenario_ready = [s for s in ready if s.scenario == scenario]
        scenario_all = [s for s in sessions if s.scenario == scenario]
        avg = (
            sum(s.analysis.confidence for s in scenario_ready) / len(scenario_ready)
            if scenario_ready else None
        )
        by_scenario.append({
            "scenario": scenario,
            "sessions": len(scenario_all),
            "analyzed": len(scenario_ready),
            "avgConfidence": round(avg, 3) if avg is not None else None,
        })

    # Per-skill trend (last 20 analyzed sessions)
    skill_trend = []
    for s in ready[-20:]:
        nlp = s.analysis.nlpMetrics or {}
        speech = s.analysis.speechMetrics or {}
        skill_trend.append({
            "sessionId": s.id,
            "title": s.title,
            "scenario": s.scenario,
            "createdAt": s.createdAt.isoformat(),
            "confidence": s.analysis.confidence,
            "clarity": nlp.get("clarity"),
            "structure": nlp.get("structure"),
            "relevance": nlp.get("relevance"),
            "speechScore": speech.get("score"),
        })

    avg_confidence = (
        round(sum(s.analysis.confidence for s in ready) / len(ready), 3) if ready else None
    )

    return {
        "totalSessions": len(sessions),
        "analyzedSessions": len(ready),
        "avgConfidence": avg_confidence,
        "confidenceTrend": confidence_trend,
        "skillTrend": skill_trend,
        "repeatedIssues": sorted(
            [{"issue": k, "count": v} for k, v in issue_counts.items()],
            key=lambda x: -x["count"],
        )[:5],
        "byScenario": by_scenario,
    }


@router.get("/")
async def list_sessions(db: AsyncSession = Depends(get_db), user: Principal = Depends(current_user)):
    """Return the most recent sessions (summary only)."""
    result = await db.execute(
        select(Session).where(Session.userId == user.id).order_by(Session.createdAt.desc()).limit(SESSION_LIST_LIMIT)
    )
    sessions = result.scalars().all()
    return {
        "sessions": [
            {
                "id": s.id,
                "createdAt": s.createdAt.isoformat(),
                "updatedAt": s.updatedAt.isoformat(),
                "status": s.status,
                "scenario": s.scenario,
                "title": s.title,
            }
            for s in sessions
        ]
    }


@router.post("/", status_code=201)
async def create_session(body: CreateSessionRequest, db: AsyncSession = Depends(get_db), user: Principal = Depends(current_user)):
    """Create a new interview session, optionally storing structured context."""
    # Sanitize text fields
    title = sanitize_text(body.title)[:120] if body.title else None
    context_raw, context_json = build_structured_context({
        "scenario": body.scenario,
        "resumeText": body.resumeText,
        "jobDescription": body.jobDescription,
        "topicNotes": body.topicNotes,
        "freeText": body.freeText or body.contextText,
    })
    has_context = bool(context_raw.strip())

    # Minimal local profile; identity comes exclusively from the verified JWT.
    # Concurrent creates must not race on User's primary key.
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    await db.execute(insert(User).values(id=user.id).on_conflict_do_nothing(index_elements=["id"]))
    await check_new_session(db, user.id)
    session = Session(
        id=cuid_generate(),
        userId=user.id,
        scenario=normalize_scenario(body.scenario),
        persona=normalize_persona(body.persona),
        pressureLevel=normalize_pressure_level(body.pressureLevel),
        title=title,
        contextRaw=context_raw if has_context else None,
        contextJson=context_json if has_context else None,
        updatedAt=datetime.utcnow(),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {
        "session": {
            "id": session.id,
            "status": session.status,
            "scenario": session.scenario,
            "createdAt": session.createdAt.isoformat(),
            "title": session.title,
            "persona": session.persona,
            "pressureLevel": session.pressureLevel,
        }
    }


@router.get("/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db), user: Principal = Depends(current_user)):
    """Return a single session with all transcript segments and analysis."""
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.segments), selectinload(Session.analysis))
        .where(Session.id == session_id, Session.userId == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="not_found")
    detail = _session_to_dict(session, include_segments=True, include_analysis=True)
    detail["failureCode"] = session.failureCode
    job = await db.scalar(select(AnalysisJob).where(AnalysisJob.sessionId == session_id, AnalysisJob.userId == user.id))
    if job:
        detail["analysisJob"] = {"status": job.status, "attempts": job.attempts, "errorCode": job.errorCode,
                                 "updatedAt": job.updatedAt.isoformat(),
                                 "heartbeatAt": job.heartbeatAt.isoformat() if job.heartbeatAt else None,
                                 "progress": job.progress}
    return {"session": detail}


@router.post("/{session_id}/segments", status_code=201)
async def add_segment(
    session_id: str,
    body: CreateSegmentRequest,
    db: AsyncSession = Depends(get_db),
    user: Principal = Depends(current_user),
):
    """Append a transcript segment to a session."""
    result = await db.execute(select(Session).where(Session.id == session_id, Session.userId == user.id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="not_found")

    await lock_owner(db, user.id)
    await db.refresh(session)
    if session.status != "LIVE":
        raise HTTPException(409, "session_not_live")
    total = await db.scalar(select(func.coalesce(func.sum(func.length(TranscriptSegment.text)), 0)).where(TranscriptSegment.sessionId == session_id))
    if total + len(body.text) > MAX_TRANSCRIPT_CHARS:
        raise HTTPException(413, "transcript_limit")
    seg = TranscriptSegment(
        id=cuid_generate(),
        sessionId=session_id,
        speaker=body.speaker,
        text=sanitize_text(body.text),
    )
    db.add(seg)
    await db.commit()
    await db.refresh(seg)

    return {
        "segment": {
            "id": seg.id,
            "sessionId": seg.sessionId,
            "createdAt": seg.createdAt.isoformat(),
            "speaker": seg.speaker,
            "text": seg.text,
        }
    }


@router.post("/{session_id}/end")
async def end_session(session_id: str, db: AsyncSession = Depends(get_db), user: Principal = Depends(current_user)):
    async with completion.end_lock(session_id):
        return await _end_session(session_id, db, user)


async def _end_session(session_id, db, user):
    """Confirm final speech, stage private audio, and durably enqueue exactly once."""
    session = await db.scalar(select(Session).where(Session.id == session_id, Session.userId == user.id))
    if not session:
        raise HTTPException(404, "not_found")
    if session.status == "READY":
        return {"ok": True}
    existing = await db.scalar(select(AnalysisJob).where(AnalysisJob.sessionId == session_id, AnalysisJob.userId == user.id))
    if existing and existing.status != "UPLOADING":
        return {"ok": True}
    # Do not hold a pool connection while Gemini callbacks need the database.
    await db.commit()
    try:
        await completion.drain(session_id)
    except (TimeoutError, RuntimeError):
        raise HTTPException(409, "final_turn_not_confirmed")
    path = audio_buffer_store.seal(session_id)
    size = audio_buffer_store.size(session_id)
    storage = None
    if path:
        try:
            storage = AudioStorage()
            await storage.check_private()
        except (StorageError, httpx.HTTPError):
            raise HTTPException(503, "private_audio_storage_unavailable") from None
    job = await enqueue(db, session_id, user.id, f"{user.id}/{session_id}.pcm" if path else None, size)
    logger.info("[analysis] durable job saved", {"sessionId": session_id, "jobId": job.id, "status": job.status})
    if job.status == "UPLOADING" and path:
        try:
            await storage.upload(job.audioKey, path, job.audioBytes)
            await mark_uploaded(db, job.id)
            audio_buffer_store.clear(session_id)
        except (StorageError, httpx.HTTPError):
            # Durable UPLOADING row lets a worker recover an uploaded object if
            # the gateway dies between Storage success and QUEUED commit.
            raise HTTPException(503, "audio_upload_pending_retry") from None
    return {"ok": True}
