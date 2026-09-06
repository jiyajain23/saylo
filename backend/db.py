"""
Async SQLAlchemy engine + session factory.
Replaces Prisma client (db.ts).
Uses the same SQLite database file via DATABASE_URL env var.
"""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")

# SQLite async engine. echo=True in dev to log queries.
_IS_DEV = os.environ.get("NODE_ENV") != "production"

engine = create_async_engine(
    _DATABASE_URL,
    echo=_IS_DEV,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        yield session
