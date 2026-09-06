"""
SQLAlchemy async ORM models and Pydantic schemas.
Mirrors the Prisma schema (apps/api/prisma/schema.prisma).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, field_validator
from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── Enums ──────────────────────────────────────────────────────────────────────

class SessionScenario(str, enum.Enum):
    INTERVIEW = "INTERVIEW"
    PITCH = "PITCH"
    MEETING = "MEETING"


class SessionStatus(str, enum.Enum):
    LIVE = "LIVE"
    ENDED = "ENDED"
    ANALYZING = "ANALYZING"
    READY = "READY"
    FAILED = "FAILED"


# ── ORM Models ─────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "User"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sessions: Mapped[list["Session"]] = relationship("Session", back_populates="user")


class Session(Base):
    __tablename__ = "Session"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updatedAt: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    status: Mapped[str] = mapped_column(String, default="LIVE")
    scenario: Mapped[str] = mapped_column(String, default="INTERVIEW")
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    persona: Mapped[str] = mapped_column(String, default="DEFAULT")
    pressureLevel: Mapped[int] = mapped_column(Integer, default=0)

    userId: Mapped[Optional[str]] = mapped_column(String, ForeignKey("User.id"), nullable=True)
    user: Mapped[Optional["User"]] = relationship("User", back_populates="sessions")

    contextRaw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contextJson: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    segments: Mapped[list["TranscriptSegment"]] = relationship(
        "TranscriptSegment", back_populates="session", cascade="all, delete-orphan"
    )
    analysis: Mapped[Optional["AnalysisResult"]] = relationship(
        "AnalysisResult", back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class TranscriptSegment(Base):
    __tablename__ = "TranscriptSegment"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sessionId: Mapped[str] = mapped_column(String, ForeignKey("Session.id", ondelete="CASCADE"))
    session: Mapped["Session"] = relationship("Session", back_populates="segments")

    createdAt: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    speaker: Mapped[str] = mapped_column(String)   # "user" | "ai"
    text: Mapped[str] = mapped_column(Text)


class AnalysisResult(Base):
    __tablename__ = "AnalysisResult"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sessionId: Mapped[str] = mapped_column(String, ForeignKey("Session.id", ondelete="CASCADE"), unique=True)
    session: Mapped["Session"] = relationship("Session", back_populates="analysis")

    createdAt: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    speechMetrics: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    nlpMetrics: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    alignment: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    highlights: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    strengths: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    weaknesses: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    suggestions: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)


# ── Pydantic request/response schemas ──────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    scenario: str = "INTERVIEW"
    persona: str = "DEFAULT"
    pressureLevel: int = 0
    title: Optional[str] = None
    contextText: Optional[str] = None
    resumeText: Optional[str] = None
    jobDescription: Optional[str] = None
    topicNotes: Optional[str] = None
    freeText: Optional[str] = None

    @field_validator("pressureLevel")
    @classmethod
    def validate_pressure(cls, v: int) -> int:
        if v not in (0, 1, 2, 3):
            raise ValueError("pressureLevel must be 0-3")
        return v


class CreateSegmentRequest(BaseModel):
    speaker: str   # "user" | "ai"
    text: str

    @field_validator("speaker")
    @classmethod
    def validate_speaker(cls, v: str) -> str:
        if v not in ("user", "ai"):
            raise ValueError("speaker must be 'user' or 'ai'")
        return v

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text must not be empty")
        return v[:4000]


class SessionSummary(BaseModel):
    id: str
    createdAt: datetime
    updatedAt: datetime
    status: str
    scenario: str
    title: Optional[str]

    class Config:
        from_attributes = True


class SegmentOut(BaseModel):
    id: str
    sessionId: str
    createdAt: datetime
    speaker: str
    text: str

    class Config:
        from_attributes = True


class AnalysisResultOut(BaseModel):
    id: str
    sessionId: str
    createdAt: datetime
    speechMetrics: Optional[Any]
    nlpMetrics: Optional[Any]
    alignment: Optional[Any]
    confidence: Optional[float]
    highlights: Optional[Any]
    strengths: Optional[Any]
    weaknesses: Optional[Any]
    suggestions: Optional[Any]

    class Config:
        from_attributes = True


class SessionDetail(BaseModel):
    id: str
    createdAt: datetime
    updatedAt: datetime
    status: str
    scenario: str
    title: Optional[str]
    persona: str
    pressureLevel: int
    contextRaw: Optional[str]
    contextJson: Optional[Any]
    segments: list[SegmentOut] = []
    analysis: Optional[AnalysisResultOut] = None

    class Config:
        from_attributes = True
