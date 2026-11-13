"""PostgreSQL-backed jobs: transactional enqueue, fenced leases, bounded retries."""
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, update, text, func
from models.schemas import Session, TranscriptSegment, AnalysisJob, AnalysisResult
from services.limits import lock_owner

ACTIVE = ("UPLOADING", "QUEUED", "RUNNING")
LEASE_SECONDS = 90
MAX_ATTEMPTS = 3
RETENTION_HOURS = 24


async def enqueue(db, session_id, owner, audio_key, audio_bytes):
    await lock_owner(db, owner)
    session = await db.scalar(select(Session).where(Session.id == session_id, Session.userId == owner))
    if not session: raise HTTPException(404, "not_found")
    existing = await db.scalar(select(AnalysisJob).where(AnalysisJob.sessionId == session_id, AnalysisJob.userId == owner))
    if existing:
        await db.commit()
        return existing
    if session.status not in ("LIVE", "ENDED"):
        raise HTTPException(409, session.failureCode or "session_not_completable")
    if session.audioBytes and not audio_key:
        raise HTTPException(409, "recorded_audio_unavailable")
    if not await db.scalar(select(TranscriptSegment.id).where(TranscriptSegment.sessionId == session_id,
                                    TranscriptSegment.speaker == "user").limit(1)):
        raise HTTPException(422, "no_user_speech")
    if await db.scalar(select(AnalysisJob.id).where(AnalysisJob.userId == owner, AnalysisJob.status.in_(ACTIVE)).limit(1)):
        raise HTTPException(429, "analysis_already_pending")
    if db.bind.dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(72850126)"))
    reserved = await db.scalar(select(func.coalesce(func.sum(AnalysisJob.audioBytes), 0))
                              .where(AnalysisJob.audioDeletedAt.is_(None)))
    pending = await db.scalar(select(func.count()).select_from(AnalysisJob).where(AnalysisJob.status.in_(ACTIVE)))
    if reserved + audio_bytes > 512 * 1024 * 1024 or pending >= 50:
        raise HTTPException(429, "demo_capacity_reached")
    now = datetime.utcnow()
    job = AnalysisJob(id=str(uuid4()), sessionId=session_id, userId=owner,
                      status="UPLOADING" if audio_key else "QUEUED", audioKey=audio_key,
                      audioBytes=audio_bytes, expiresAt=now + timedelta(hours=RETENTION_HOURS))
    session.status = "ANALYZING"
    session.audioBytes = audio_bytes
    session.updatedAt = now
    db.add(job)
    await db.commit()
    return job


async def mark_uploaded(db, job_id):
    await db.execute(update(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.status == "UPLOADING")
                     .values(status="QUEUED", updatedAt=datetime.utcnow()))
    await db.commit()


async def claim_job(db):
    now = datetime.utcnow()
    if db.bind.dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(72850125)"))
    else:
        await db.execute(update(AnalysisJob).values(attempts=AnalysisJob.attempts))
    # One active inference globally, including accidentally duplicated workers.
    if await db.scalar(select(AnalysisJob.id).where(AnalysisJob.status == "RUNNING", AnalysisJob.leaseExpiresAt > now).limit(1)):
        await db.commit()
        return None
    job = await db.scalar(select(AnalysisJob).where(
        or_(and_(AnalysisJob.status == "QUEUED", AnalysisJob.availableAt <= now),
            and_(AnalysisJob.status == "RUNNING", AnalysisJob.leaseExpiresAt <= now)))
        .order_by(AnalysisJob.createdAt).with_for_update(skip_locked=True).limit(1))
    if not job:
        await db.commit()
        return None
    if job.attempts >= MAX_ATTEMPTS or job.expiresAt <= now:
        await terminal(db, job, "retry_limit" if job.attempts >= MAX_ATTEMPTS else "job_expired")
        await db.commit()
        return None
    job.status = "RUNNING"
    job.attempts += 1
    job.leaseToken = str(uuid4())
    job.leaseExpiresAt = now + timedelta(seconds=LEASE_SECONDS)
    job.heartbeatAt = job.updatedAt = now
    await db.commit()
    return job


async def heartbeat(db, job_id, token):
    now = datetime.utcnow()
    result = await db.execute(update(AnalysisJob).where(AnalysisJob.id == job_id,
        AnalysisJob.leaseToken == token, AnalysisJob.status == "RUNNING", AnalysisJob.leaseExpiresAt > now)
        .values(heartbeatAt=now, leaseExpiresAt=now + timedelta(seconds=LEASE_SECONDS)))
    await db.commit()
    return result.rowcount == 1


async def terminal(db, job, code):
    job.status = "FAILED"
    job.errorCode = code
    job.progress = {"current": {"stage": "analysis", "status": "failed", "error": code}, "events": []}
    job.leaseToken = None
    job.leaseExpiresAt = None
    job.updatedAt = datetime.utcnow()
    await db.execute(update(Session).where(Session.id == job.sessionId, Session.userId == job.userId)
                     .values(status="FAILED", failureCode=code, updatedAt=datetime.utcnow()))


async def current_claim(db, job_id, token):
    return await db.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id,
        AnalysisJob.status == "RUNNING", AnalysisJob.leaseToken == token,
        AnalysisJob.leaseExpiresAt > datetime.utcnow()).with_for_update())


async def complete_job(db, job_id, token, data):
    job = await current_claim(db, job_id, token)
    if not job: return False
    insights = data.get("insights") or {}
    fields = {"speechMetrics": data.get("speech"), "nlpMetrics": data.get("nlp"),
              "alignment": data.get("alignment"), "confidence": data.get("confidence"),
              **{key: insights.get(key) for key in ("highlights", "strengths", "weaknesses", "suggestions")},
              **{key: data.get(key) for key in ("voice", "emotion", "vision", "jobs", "errors", "insights", "scoring_version")}}
    result = await db.scalar(select(AnalysisResult).where(AnalysisResult.sessionId == job.sessionId))
    if result:
        for key, value in fields.items(): setattr(result, key, value)
    else: db.add(AnalysisResult(id=str(uuid4()), sessionId=job.sessionId, **fields))
    await db.execute(update(Session).where(Session.id == job.sessionId, Session.userId == job.userId)
                     .values(status="READY", failureCode=None, updatedAt=datetime.utcnow()))
    job.status = "SUCCEEDED"
    job.progress = {"current": {"stage": "analysis", "status": "completed"}, "events": []}
    job.errorCode = None
    job.leaseToken = job.leaseExpiresAt = None
    job.updatedAt = datetime.utcnow()
    await db.commit()
    return True


async def fail_job(db, job_id, token, code, retryable=True):
    job = await current_claim(db, job_id, token)
    if not job: return False
    if retryable and job.attempts < MAX_ATTEMPTS and job.expiresAt > datetime.utcnow():
        job.status = "QUEUED"
        job.availableAt = datetime.utcnow() + timedelta(seconds=30 * job.attempts)
        job.errorCode = code
        job.leaseToken = job.leaseExpiresAt = None
        job.updatedAt = datetime.utcnow()
        job.progress = {"current": {"stage": "analysis", "status": "retrying"}, "events": []}
    else: await terminal(db, job, code)
    await db.commit()
    return True
