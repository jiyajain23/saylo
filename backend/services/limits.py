"""Small demo limits; no external limiter or queue infrastructure."""
import os
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, update
from models.schemas import Session, User, AnalysisJob

SESSION_SECONDS = max(1, min(900, int(os.getenv("MAX_SESSION_SECONDS", "900"))))
DAILY_SESSIONS = max(1, int(os.getenv("DAILY_SESSION_LIMIT", "5")))
MAX_AUDIO_BYTES = SESSION_SECONDS * 16000 * 2
MAX_WS_BYTES = 256 * 1024
MAX_HTTP_BYTES = 128 * 1024
MAX_TRANSCRIPT_CHARS = 120000
MAX_LIVE_CONNECTIONS = int(os.getenv("MAX_LIVE_CONNECTIONS", "4"))
STALE_QUEUED_SECONDS = max(600, int(os.getenv("STALE_QUEUED_SECONDS", "1200")))


async def lock_owner(db, owner):
    # A row lock on PostgreSQL; a write lock in local SQLite regression tests.
    await db.execute(update(User).where(User.id == owner).values(id=owner))


async def check_new_session(db, owner):
    await lock_owner(db, owner)
    now = datetime.utcnow()
    await db.execute(update(Session).where(Session.userId == owner, Session.status == "LIVE",
                     Session.createdAt < now - timedelta(seconds=SESSION_SECONDS + 60))
                     .values(status="FAILED", failureCode="session_expired"))
    # A queued job older than the recovery window has no worker making progress.
    # Release the per-user admission slot while preserving the failed job and
    # transcript for inspection. RUNNING jobs are stale only after their lease
    # has expired; an actively heartbeating worker is left alone.
    stale_queued = await db.scalars(select(AnalysisJob).where(
        AnalysisJob.userId == owner,
        AnalysisJob.status.in_(["UPLOADING", "QUEUED"]),
        AnalysisJob.updatedAt < now - timedelta(seconds=STALE_QUEUED_SECONDS)))
    stale_jobs = list(stale_queued)
    stale_running = await db.scalars(select(AnalysisJob).where(
        AnalysisJob.userId == owner, AnalysisJob.status == "RUNNING",
        AnalysisJob.leaseExpiresAt < now))
    stale_jobs.extend(list(stale_running))
    if stale_jobs:
        stale_ids = [job.id for job in stale_jobs]
        await db.execute(update(AnalysisJob).where(AnalysisJob.id.in_(stale_ids)).values(
            status="FAILED", errorCode="worker_unavailable", leaseToken=None,
            leaseExpiresAt=None, updatedAt=now))
        await db.execute(update(Session).where(Session.userId == owner,
            Session.id.in_([job.sessionId for job in stale_jobs]),
            Session.status == "ANALYZING").values(status="FAILED",
            failureCode="worker_unavailable", updatedAt=now))
    if await db.scalar(select(Session.id).where(Session.userId == owner, Session.status == "LIVE").limit(1)):
        raise HTTPException(429, "live_session_limit")
    if await db.scalar(select(AnalysisJob.id).where(AnalysisJob.userId == owner,
                        AnalysisJob.status.in_(["UPLOADING", "QUEUED", "RUNNING"])).limit(1)):
        raise HTTPException(429, "analysis_already_pending")
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    count = await db.scalar(select(func.count()).select_from(Session).where(Session.userId == owner, Session.createdAt >= today))
    if count >= DAILY_SESSIONS:
        raise HTTPException(429, "daily_session_limit")
