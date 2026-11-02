"""App tables (schema `app`). User ids are Better Auth ids (text), with no FK across schemas."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Better Auth's user table (schema `better_auth`; Supabase reserves `auth`), read-only here and never migrated by Alembic.
auth_user = Table(
    "user",
    Base.metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text),
    Column("email", Text),
    schema="better_auth",
)

ROLES = ("admin", "editor", "journalist")


class _Row(Base):
    __abstract__ = True
    __table_args__ = {"schema": "app"}  # noqa: RUF012 - SQLAlchemy convention

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Workspace(_Row):
    __tablename__ = "workspace"

    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140), unique=True)


class Membership(_Row):
    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"), {"schema": "app"})

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE")
    )
    user_id: Mapped[str] = mapped_column(Text, index=True)
    role: Mapped[str] = mapped_column(String(20))


class Invitation(_Row):
    __tablename__ = "invitation"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Item(_Row):
    __tablename__ = "item"
    __table_args__ = (
        Index("ix_item_tags", "tags", postgresql_using="gin"),
        Index("ix_item_data", "data", postgresql_using="gin"),
        {"schema": "app"},
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(40), default="claim")
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="to_check")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Comment(_Row):
    __tablename__ = "comment"

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.item.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)


class Activity(_Row):
    __tablename__ = "activity"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str] = mapped_column(Text)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(20))
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Job(_Row):
    __tablename__ = "job"
    __table_args__ = (
        # The worker's claim query scans queued jobs oldest first.
        Index("ix_job_queued", "created_at", postgresql_where="status = 'queued'"),
        {"schema": "app"},
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiCall(_Row):
    """One provider attempt through the AI gateway. Never stores prompt or answer text."""

    __tablename__ = "ai_call"

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    latency_ms: Mapped[int]
    tokens_in: Mapped[int | None]
    tokens_out: Mapped[int | None]
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
