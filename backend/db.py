"""
Async SQLAlchemy engine with a small PostgreSQL pool and local SQLite support.
Production startup checks versioned migrations instead of creating tables.
"""

import os
import ssl
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv(Path(__file__).resolve().parent / ".env")


def database_settings(raw: str):
    if raw.startswith("file:"):
        raw = "sqlite+aiosqlite:///" + raw[5:]
    url = make_url(raw)
    if url.drivername.startswith("sqlite"):
        if os.environ.get("NODE_ENV") == "production":
            raise RuntimeError("Production requires Supabase PostgreSQL DATABASE_URL")
        return url.set(drivername="sqlite+aiosqlite"), {"connect_args": {"check_same_thread": False}}
    if url.get_backend_name() not in ("postgres", "postgresql"):
        raise RuntimeError("DATABASE_URL must use PostgreSQL or local SQLite")
    query = dict(url.query)
    query.pop("sslmode", None)
    query.pop("ssl", None)
    connect = {"server_settings": {"timezone": "UTC"}}
    if os.environ.get("DATABASE_SSL", "verify-full") != "disable":
        connect["ssl"] = ssl.create_default_context(cafile=os.environ.get("DATABASE_SSL_CA_FILE") or None)
    elif url.host not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("DATABASE_SSL=disable is restricted to loopback test databases")
    return url.set(drivername="postgresql+asyncpg", query=query), {
        "connect_args": connect, "pool_size": 2, "max_overflow": 0,
        "pool_pre_ping": True, "pool_recycle": 300, "pool_timeout": 15,
    }


_url, _settings = database_settings(os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./dev.db"))
engine = create_async_engine(_url, echo=False, hide_parameters=True, **_settings)
if engine.dialect.name == "sqlite":
    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            from migrations.runner import check_schema
            await conn.run_sync(check_schema)
        else:
            from models.schemas import Base
            from migrations.phase1 import upgrade
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(upgrade)
            for table in Base.metadata.tables.values():
                for index in table.indexes:
                    await conn.run_sync(lambda sync, ix=index: ix.create(sync, checkfirst=True))
