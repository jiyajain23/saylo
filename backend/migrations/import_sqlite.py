"""Explicit single-owner import from a read-only local SQLite snapshot.

Defaults to a count-only preview. --apply inserts in one PostgreSQL transaction,
refuses ID collisions and foreign owners, and never edits/rescores source data.
"""
import argparse
import asyncio
import sqlite3
from pathlib import Path
from uuid import UUID

from sqlalchemy import MetaData, create_engine, select, text
from sqlalchemy.dialects.postgresql import insert


def read_snapshot(path: Path, owner: str):
    if not path.is_file():
        raise ValueError("SQLite snapshot does not exist")
    source = create_engine("sqlite://", creator=lambda: sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True))
    try:
        metadata = MetaData()
        metadata.reflect(source)
        data = {}
        with source.connect() as connection:
            for table in ("Session", "TranscriptSegment", "AnalysisResult"):
                data[table] = [dict(row) for row in connection.execute(select(metadata.tables[table])).mappings()]
        if any(row.get("userId") not in (None, owner) for row in data["Session"]):
            raise ValueError("Snapshot contains another owner's sessions; supply a reviewed per-user export")
        return data
    finally:
        source.dispose()


async def import_rows(connection, data, owner):
    from models.schemas import Session, User, TranscriptSegment, AnalysisResult
    from migrations.runner import check_schema
    await connection.run_sync(check_schema)
    if not await connection.scalar(text("SELECT id FROM auth.users WHERE id = CAST(:owner AS UUID)"), {"owner": owner}):
        raise ValueError("Create the target Supabase Auth user before importing")
    await connection.execute(insert(User).values(id=owner).on_conflict_do_nothing(index_elements=["id"]))
    for model in (Session, TranscriptSegment, AnalysisResult):
        columns = {c.name for c in model.__table__.columns}
        for original in data[model.__tablename__]:
            row = {key: value for key, value in original.items() if key in columns}
            if model is Session:
                row["userId"] = owner
            # A conflicting ID aborts the complete import; never overwrite rows.
            await connection.execute(insert(model).values(**row))


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--owner", required=True, help="Supabase Auth UUID that owns every imported session")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    owner = str(UUID(args.owner))
    data = read_snapshot(args.source, owner)
    print({table: len(rows) for table, rows in data.items()})
    if not args.apply:
        print("Preview only. Source remains read-only. Add --apply after reviewing ownership and counts.")
        return
    from db import engine
    if engine.dialect.name != "postgresql":
        raise ValueError("Import destination must be PostgreSQL")
    try:
        async with engine.begin() as connection:
            await import_rows(connection, data, owner)
        print("Import committed. Existing transcripts and analysis scores were preserved.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
