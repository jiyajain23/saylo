"""
Async SQLAlchemy engine + session factory.
Replaces Prisma client (db.ts).
Uses the same SQLite database file via DATABASE_URL env var.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Load backend/.env explicitly
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path, override=True)

_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")

# If legacy Prisma URL format is encountered (e.g. file:./dev.db), convert to SQLAlchemy
if _DATABASE_URL.startswith("file:"):
    _path = _DATABASE_URL.replace("file:", "", 1)
    _DATABASE_URL = f"sqlite+aiosqlite:///{_path}"
elif not _DATABASE_URL.startswith("sqlite+aiosqlite://") and _DATABASE_URL.startswith("sqlite://"):
    _DATABASE_URL = _DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://", 1)

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


async def init_db() -> None:
    """Create all tables on first run. Safe to call on every startup."""
    from models.schemas import Base  # import here to avoid circular deps
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
