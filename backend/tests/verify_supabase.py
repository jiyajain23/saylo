"""Read-only Supabase diagnostics. Never print URLs, credentials, or user data."""
import asyncio
import json
import os
from pathlib import Path

import httpx
from dotenv import dotenv_values, load_dotenv
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / "backend" / ".env")


async def main():
    report = {}
    frontend = {**dotenv_values(ROOT / "frontend" / ".env"), **dotenv_values(ROOT / "frontend" / ".env.local")}
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    report["frontend_project_matches"] = frontend.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/") == url and bool(url)
    key = frontend.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "")
    report["publishable_key_present"] = bool(key)
    report["analysis_token_present"] = len(os.environ.get("ANALYSIS_SERVICE_TOKEN", "")) >= 32
    report["storage_server_key_present"] = bool(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SECRET_KEY"))
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url + "/auth/v1/.well-known/jwks.json")
            response.raise_for_status()
            report["asymmetric_signing_keys"] = any(k.get("alg") in ("ES256", "RS256") for k in response.json().get("keys", []))
            response = await client.get(url + "/auth/v1/settings", headers={"apikey": key})
            report["auth_settings_accessible"] = response.status_code == 200
    except Exception as exc:
        report["auth_error_type"] = type(exc).__name__
    try:
        from db import engine
        from migrations.runner import check_schema
        try:
            async with engine.connect() as conn:
                report["database_is_postgresql"] = engine.dialect.name == "postgresql"
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                report["database_connected"] = await conn.scalar(text("SELECT 1")) == 1
                report["database_tls"] = bool(await conn.scalar(text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")))
                await conn.run_sync(check_schema)
                report["migration_checksums_match"] = True
                rows = (await conn.execute(text("SELECT relname, relrowsecurity FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relname IN ('User', 'Session', 'TranscriptSegment', 'AnalysisResult')"))).all()
                report["rls_enabled_on_all_four_tables"] = len(rows) == 4 and all(r[1] for r in rows)
                report["owner_policies"] = await conn.scalar(text("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename IN ('User', 'Session', 'TranscriptSegment', 'AnalysisResult')"))
        finally:
            await engine.dispose()
    except Exception as exc:
        report["database_error_type"] = type(exc).__name__
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
