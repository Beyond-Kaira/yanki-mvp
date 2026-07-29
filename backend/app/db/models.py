"""SQLAlchemy models — the four tables from the SPEC.

Design note: the models are deliberately SQLite-compatible so most tests run
against an in-memory SQLite database. The only Postgres-specific type is the
``kyc`` JSONB column, declared with ``.with_variant`` so it degrades to plain
JSON on SQLite. Timestamps use Python-side defaults (``_utcnow``) rather than
DB ``now()`` so ``create_all`` works on SQLite; the Alembic migration adds
server-side defaults for Postgres.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Analysis(Base):
    """One analysis run. This table doubles as the job queue (see jobs/queue.py)."""

    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    current_step: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Salted hash of the submitter's client IP (P5.0 rate limiting). Nullable:
    # rows created before this column, and any future non-HTTP callers, leave it
    # null. Never stores the raw IP.
    ip_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Checker fields (P5.1). All nullable/defaulted so existing MVP rows are
    # untouched. ``kind`` distinguishes an MVP crawl analysis ('mvp') from a
    # checker analysis ('checker'); brand/category/lang are stored NORMALIZED
    # (trim + casefold) on checker rows so the 24h reuse lookup is a plain
    # equality match. They stay null on MVP rows.
    kind: Mapped[str] = mapped_column(sa.Text, nullable=True, default="mvp", server_default="mvp")
    brand: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    category: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    lang: Mapped[str] = mapped_column(sa.Text, nullable=True, default="en", server_default="en")
    kyc: Mapped[dict[str, Any] | None] = mapped_column(
        sa.JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    geo_score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    footprint_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    total_responses: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    prompts: Mapped[list["Prompt"]] = relationship(
        cascade="all, delete-orphan", order_by="Prompt.created_at"
    )
    responses: Mapped[list["Response"]] = relationship(
        cascade="all, delete-orphan", order_by="Response.created_at"
    )


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    category: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow
    )


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False
    )
    engine: Mapped[str] = mapped_column(sa.Text, nullable=False)
    model: Mapped[str] = mapped_column(sa.Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    footprint: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    matched_snippet: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow
    )


class CheckerSubmission(Base):
    """One accepted checker submit (P5.1) — append-only demand signal + lead.

    The 24h cache shares a single ``analyses`` row across visitors, so leads and
    demand must be counted per submit here rather than on the analysis. Every
    accepted submit (cache hits included) inserts a row; ``email`` is filled
    later by ``POST /api/v1/checker/leads`` for that specific row, so two
    visitors served the same cached analysis each keep their own lead.
    """

    __tablename__ = "checker_submissions"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    # Salted client-IP hash — stays null in P5.1; P5.6 populates it (owns salt).
    ip_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    lang: Mapped[str] = mapped_column(sa.Text, nullable=False)
    email: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow
    )


class WaitlistSignup(Base):
    """One waitlist signup (P5.13) — a landing-page email capture.

    ``email`` is stored NORMALIZED (trim + lowercase) and is UNIQUE, so the
    submit path is an ``INSERT ... ON CONFLICT DO NOTHING RETURNING id``: a
    returned row means a genuinely new signup (which triggers the thank-you +
    notification emails), a null return means a duplicate (still answered 202,
    no enumeration). ``ip_hash`` reuses the existing salted-hash helper and stays
    null for any non-HTTP caller; the raw IP is never stored.
    """

    __tablename__ = "waitlist_signups"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    ip_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow
    )


class User(Base):
    """A registered user account."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        unique=True,
    )
    password_hash: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )


class AuthSession(Base):
    """One refresh-token generation within a device/session family.

    Every successful login starts a new ``family_id``. Refresh rotation consumes
    the current row and creates a successor with the same family id. Reuse of a
    consumed refresh token revokes the whole family.
    """

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        nullable=False,
        default=uuid.uuid4,
        index=True,
    )
    refresh_jti_hash: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        unique=True,
    )
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("auth_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )


class LlmCache(Base):
    __tablename__ = "llm_cache"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    cache_key: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    engine: Mapped[str] = mapped_column(sa.Text, nullable=False)
    model: Mapped[str] = mapped_column(sa.Text, nullable=False)
    response_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow
    )
