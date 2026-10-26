"""Non-destructive additions for existing local SQLite databases.

No rows or old columns are changed. Roll back application code while leaving
these nullable columns in place. PostgreSQL migrations follow in Phase 2.
"""
from sqlalchemy import inspect, text


def upgrade(connection):
    additions = {
        "TranscriptSegment": {"audioStartSeconds": "FLOAT", "audioEndSeconds": "FLOAT"},
        "AnalysisResult": {"voice": "JSON", "emotion": "JSON", "vision": "JSON", "jobs": "JSON",
                           "errors": "JSON", "insights": "JSON", "scoring_version": "VARCHAR"},
    }
    inspector = inspect(connection)
    for table, columns in additions.items():
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column, kind in columns.items():
            if column not in existing:
                connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {kind}'))
