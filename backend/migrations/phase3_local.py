"""Additive local SQLite upgrade; hosted PostgreSQL uses revision 002."""
from sqlalchemy import inspect, text


def upgrade(connection):
    columns = {c["name"] for c in inspect(connection).get_columns("Session")}
    for name, kind in {"audioBytes": "INTEGER NOT NULL DEFAULT 0", "liveHeartbeatAt": "TIMESTAMP",
                       "failureCode": "VARCHAR"}.items():
        if name not in columns:
            connection.execute(text(f'ALTER TABLE "Session" ADD COLUMN "{name}" {kind}'))
    job_columns = {c["name"] for c in inspect(connection).get_columns("AnalysisJob")} if inspect(connection).has_table("AnalysisJob") else set()
    if "progress" not in job_columns:
        connection.execute(text('ALTER TABLE "AnalysisJob" ADD COLUMN "progress" JSON'))
