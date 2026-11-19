"""Run separately: python worker.py. No models or background jobs in the gateway."""
import asyncio
import base64
import os
import tempfile
import time
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select, update, or_, text

from db import AsyncSessionLocal, init_db, engine
from models.schemas import Session, TranscriptSegment, AnalysisJob
from services.jobs import claim_job, heartbeat, complete_job, fail_job, terminal, mark_uploaded
from services.limits import SESSION_SECONDS
from services.storage import AudioStorage, StorageError
from utils.logger import logger


def cleanup_worker_files(directory=None):
    root = Path(directory or tempfile.gettempdir()).resolve()
    for folder in root.glob("saylo-worker-*"):
        if folder.is_symlink() or not folder.is_dir() or folder.resolve().parent != root:
            continue
        path = folder / "audio.pcm"
        if path.is_symlink() or not path.is_file() or time.time() - path.stat().st_mtime < 3600:
            continue
        path.unlink()
        # Never recursively remove a directory or unrelated files.
        with suppress(OSError): folder.rmdir()


async def payload_for(job):
    async with AsyncSessionLocal() as db:
        session = await db.scalar(select(Session).where(Session.id == job.sessionId, Session.userId == job.userId))
        if not session:
            raise ValueError("session_missing")
        rows = (await db.scalars(select(TranscriptSegment).where(TranscriptSegment.sessionId == session.id)
                                .order_by(TranscriptSegment.createdAt, TranscriptSegment.id))).all()
        return {"scenario": session.scenario, "context": session.contextJson or {},
                "transcript": [{"speaker": row.speaker, "text": row.text,
                                "ts": row.createdAt.isoformat(),
                                "audioStartSeconds": row.audioStartSeconds,
                                "audioEndSeconds": row.audioEndSeconds} for row in rows]}


async def infer(job):
    payload = await payload_for(job)
    payload["job_id"] = job.id
    payload["session_id"] = job.sessionId
    if job.audioKey:
        with tempfile.TemporaryDirectory(prefix="saylo-worker-") as directory:
            path = Path(directory) / "audio.pcm"
            await AudioStorage().download(job.audioKey, path, job.audioBytes)
            # Preserve the existing analysis API and every recorded sample.
            # Only the bounded, single-concurrency worker materializes base64.
            payload["audio_b64"] = base64.b64encode(await asyncio.to_thread(path.read_bytes)).decode("ascii")
    token = os.getenv("ANALYSIS_SERVICE_TOKEN", "")
    if len(token) < 32:
        raise ValueError("analysis_service_not_configured")
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=60)) as client:
        response = await client.post(os.getenv("ANALYSIS_SERVICE_URL", "http://localhost:8000").rstrip("/") + "/analyze",
                                     json=payload, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or "insights" not in data:
            raise ValueError("invalid_analysis_response")
        return data


async def poll_progress(job, stop: asyncio.Event):
    token = os.getenv("ANALYSIS_SERVICE_TOKEN", "")
    url = os.getenv("ANALYSIS_SERVICE_URL", "http://localhost:8000").rstrip("/") + f"/progress/{job.id}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            while not stop.is_set():
                try:
                    response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
                    if response.status_code == 200:
                        body = response.json()
                        events = body.get("events") or []
                        if events:
                            latest = events[-1]
                            async with AsyncSessionLocal() as db:
                                await db.execute(update(AnalysisJob).where(
                                    AnalysisJob.id == job.id, AnalysisJob.status == "RUNNING"
                                ).values(progress={"events": events, "current": latest}))
                                await db.commit()
                except (httpx.HTTPError, ValueError):
                    pass
                try:
                    await asyncio.wait_for(stop.wait(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
    except asyncio.CancelledError:
        raise


async def keep_lease(job, task):
    try:
        while True:
            await asyncio.sleep(20)
            async with AsyncSessionLocal() as db:
                if not await heartbeat(db, job.id, job.leaseToken):
                    task.cancel()
                    return
    except Exception:
        # Never publish results after an uncertain lease; another worker recovers.
        task.cancel()


async def process(job):
    task = asyncio.create_task(infer(job))
    lease = asyncio.create_task(keep_lease(job, task))
    stop_progress = asyncio.Event()
    progress_task = asyncio.create_task(poll_progress(job, stop_progress))
    try:
        data = await task
        async with AsyncSessionLocal() as db:
            if await complete_job(db, job.id, job.leaseToken, data):
                logger.info("[worker] analysis persisted", {"jobId": job.id})
    except asyncio.CancelledError:
        # Cancellation releases no claim. Its lease safely expires after restart.
        if asyncio.current_task().cancelling():
            raise
    except Exception as exc:
        retryable = not isinstance(exc, ValueError)
        code = "analysis_unavailable"
        if isinstance(exc, StorageError): code = "audio_storage_unavailable"
        if isinstance(exc, ValueError): code = "invalid_analysis_response"
        if isinstance(exc, httpx.HTTPStatusError):
            retryable = exc.response.status_code >= 500 or exc.response.status_code == 429
        logger.warn("[worker] attempt failed", {"errorType": type(exc).__name__})
        async with AsyncSessionLocal() as db:
            await fail_job(db, job.id, job.leaseToken, code, retryable)
    finally:
        task.cancel()
        lease.cancel()
        stop_progress.set()
        progress_task.cancel()
        with suppress(asyncio.CancelledError): await lease
        with suppress(asyncio.CancelledError): await progress_task
        with suppress(asyncio.CancelledError, Exception): await task


async def maintenance():
    await asyncio.to_thread(cleanup_worker_files)
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        # A hard gateway restart cannot resume Gemini or recover its ephemeral PCM.
        # Preserve the transcript and explicitly report interruption, never score
        # missing audio as if the complete voice recording had been available.
        await db.execute(update(Session).where(Session.status == "LIVE",
            or_(Session.createdAt < now - timedelta(seconds=SESSION_SECONDS + 90),
                Session.liveHeartbeatAt < now - timedelta(seconds=90)))
            .values(status="FAILED", failureCode="live_session_interrupted", updatedAt=now))
        pending = (await db.scalars(select(AnalysisJob).where(AnalysisJob.status == "UPLOADING")
                                   .order_by(AnalysisJob.createdAt).limit(25))).all()
        await db.commit()
    for job in pending:
        try:
            exists = await AudioStorage().exists(job.audioKey, job.audioBytes)
            async with AsyncSessionLocal() as db:
                current = await db.scalar(select(AnalysisJob).where(AnalysisJob.id == job.id).with_for_update())
                if not current or current.status != "UPLOADING": continue
                if exists:
                    await mark_uploaded(db, job.id)
                elif job.createdAt < now - timedelta(minutes=10):
                    await terminal(db, current, "audio_upload_incomplete")
                    await db.commit()
        except (StorageError, httpx.HTTPError):
            pass  # Retention expiry below is independent of Storage availability.
    async with AsyncSessionLocal() as db:
        expired = (await db.scalars(select(AnalysisJob).where(
            AnalysisJob.status.in_(("UPLOADING", "QUEUED")), AnalysisJob.expiresAt <= now).with_for_update())).all()
        for job in expired: await terminal(db, job, "job_expired")
        cleanup = (await db.scalars(select(AnalysisJob).where(AnalysisJob.audioKey.is_not(None),
            AnalysisJob.audioDeletedAt.is_(None),
            or_(AnalysisJob.status == "SUCCEEDED", AnalysisJob.expiresAt <= now))
            .order_by(AnalysisJob.createdAt).limit(25))).all()
        await db.commit()
    for job in cleanup:
        try:
            await AudioStorage().delete(job.audioKey)
            async with AsyncSessionLocal() as db:
                await db.execute(update(AnalysisJob).where(AnalysisJob.id == job.id).values(audioDeletedAt=datetime.utcnow()))
                await db.commit()
        except (StorageError, httpx.HTTPError):
            logger.warn("[worker] audio cleanup pending")
    # Account deletion cascades the jobs, so cleanup must also find orphaned
    # objects. Read Storage metadata; delete exclusively through its HTTP API.
    async with AsyncSessionLocal() as db:
        if db.bind.dialect.name != "postgresql": return
        keys = (await db.execute(text('''SELECT name FROM storage.objects o
            WHERE bucket_id = 'saylo-audio' AND created_at < :cutoff
            AND NOT EXISTS (SELECT 1 FROM public."AnalysisJob" j
                WHERE j."audioKey" = o.name AND j."expiresAt" > :now
                AND j.status IN ('UPLOADING', 'QUEUED', 'RUNNING'))
            ORDER BY created_at LIMIT 25'''), {"cutoff": now.replace(tzinfo=timezone.utc) - timedelta(hours=24), "now": now})).scalars().all()
    for key in keys:
        try: await AudioStorage().delete(key)
        except (StorageError, httpx.HTTPError):
            logger.warn("[worker] orphan cleanup pending")


async def main():
    await init_db()
    try:
        while True:
            try:
                await maintenance()
                async with AsyncSessionLocal() as db: job = await claim_job(db)
                if job:
                    logger.info("[worker] claimed job", {"jobId": job.id, "attempt": job.attempts})
                    await process(job)
                else: await asyncio.sleep(5)
            except Exception as exc:
                logger.warn("[worker] retrying after service failure", {"errorType": type(exc).__name__})
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
