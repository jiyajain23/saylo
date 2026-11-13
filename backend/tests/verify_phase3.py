"""Secret-safe diagnostics; --storage-smoke writes/deletes one synthetic PCM object."""
import asyncio
import base64
import json
import sys
import tempfile
import tracemalloc
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text
from db import engine
from migrations.runner import check_schema
from services.storage import AudioStorage
from utils.audio import AudioBufferStore


async def main():
    report = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await conn.run_sync(check_schema)
            report["phase3_migration_verified"] = True
            report["job_rls_enabled"] = bool(await conn.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.\"AnalysisJob\"'::regclass")))
            report["active_owner_unique_index"] = bool(await conn.scalar(text("SELECT indisunique AND indisvalid FROM pg_index WHERE indexrelid = 'public.ix_job_one_active_owner'::regclass")))
            report["end_user_job_writes_denied"] = not bool(await conn.scalar(text("SELECT has_table_privilege('authenticated', 'public.\"AnalysisJob\"', 'INSERT,UPDATE,DELETE')")))
            report["storage_policy_count_requires_review_if_nonzero"] = await conn.scalar(text("SELECT count(*) FROM pg_policies WHERE schemaname='storage' AND tablename='objects'"))
    except Exception as exc:
        report["database_error_type"] = type(exc).__name__
    finally: await engine.dispose()
    try:
        storage = AudioStorage()
        await storage.check_private()
        report["server_key_and_private_bucket_verified"] = True
        if "--storage-smoke" in sys.argv:
            key = f"_verification/{uuid4()}.pcm"
            try:
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "synthetic.pcm"
                    path.write_bytes(b"\x00\x00\x01\x00")
                    await storage.upload(key, path, 4)
                    report["uploaded_exact_size"] = await storage.exists(key, 4)
                    await storage.download(key, Path(directory) / "download.pcm", 4)
                    report["download_matches"] = (Path(directory) / "download.pcm").read_bytes() == path.read_bytes()
                    async with httpx.AsyncClient(timeout=15) as client:
                        response = await client.get(storage.object_url(key))
                        report["anonymous_audio_denied"] = response.status_code in (400, 401, 403, 404)
            finally:
                await storage.delete(key)
                report["synthetic_object_deleted"] = not await storage.exists(key, 4)
    except Exception as exc:
        report["storage_error_type"] = type(exc).__name__
    with tempfile.TemporaryDirectory() as directory:
        store = AudioBufferStore(Path(directory), max_bytes=28_800_000)
        chunk = base64.b64encode(bytes(32000)).decode()
        tracemalloc.start()
        try:
            for _ in range(900): store.append("synthetic", chunk)
            _, peak = tracemalloc.get_traced_memory()
        finally: tracemalloc.stop()
        report["pcm_15_minutes_disk_bytes"] = store.seal("synthetic").stat().st_size
        report["pcm_buffer_peak_python_allocated_bytes"] = peak
        store.clear("synthetic")
    print(json.dumps(report, indent=2))


if __name__ == "__main__": asyncio.run(main())
