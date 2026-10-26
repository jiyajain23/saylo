"""Transactional, checksummed SQL migrations. Run: python -m migrations.runner [--check]."""
import asyncio
import hashlib
import sys
from pathlib import Path

from sqlalchemy import inspect, text

SQL_DIR = Path(__file__).parent / "sql"


def revisions():
    return [(p.name, hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest(), p.read_text(encoding="utf-8"))
            for p in sorted(SQL_DIR.glob("*.sql"))]


def check_schema(connection):
    if not inspect(connection).has_table("saylo_schema_migrations", schema="public"):
        raise RuntimeError("Run python -m migrations.runner before starting the PostgreSQL gateway")
    applied = dict(connection.execute(text("SELECT version, checksum FROM public.saylo_schema_migrations")).all())
    for version, checksum, _ in revisions():
        if applied.get(version) != checksum:
            raise RuntimeError(f"Missing or changed database migration: {version}")


def upgrade(connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Versioned migrations require a Supabase PostgreSQL database")
    connection.execute(text("SELECT pg_advisory_xact_lock(72850124)"))
    connection.execute(text("CREATE TABLE IF NOT EXISTS public.saylo_schema_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
    connection.execute(text("REVOKE ALL ON public.saylo_schema_migrations FROM anon, authenticated"))
    applied = dict(connection.execute(text("SELECT version, checksum FROM public.saylo_schema_migrations")).all())
    for version, checksum, sql in revisions():
        if version in applied:
            if applied[version] != checksum:
                raise RuntimeError(f"Applied migration was edited: {version}")
            continue
        # Files contain simple SQL statements only, no procedural bodies.
        for statement in sql.split(";"):
            if statement.strip():
                connection.execute(text(statement))
        connection.execute(text("INSERT INTO public.saylo_schema_migrations (version, checksum) VALUES (:version, :checksum)"),
                           {"version": version, "checksum": checksum})
    check_schema(connection)


async def main():
    from db import engine
    try:
        async with engine.begin() as connection:
            await connection.run_sync(check_schema if "--check" in sys.argv else upgrade)
        print("Saylo PostgreSQL migrations verified.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
