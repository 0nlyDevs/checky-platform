"""App tables (schema `app`). User ids are Better Auth ids (text), with no FK across schemas."""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
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
    and_,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.core.db import Base

# Better Auth's user table (schema `better_auth`), read-only here and never migrated by Alembic.
auth_user = Table(
    "user",
    Base.metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text),
    Column("email", Text),
    schema="better_auth",
)

# Places are structured everywhere (`{name, country, region, locality, lat, lng}`, see
# app/core/places.py): a claim can come from anywhere in the world. Beats (rubriques) belong to
# each newsroom (`workspace.settings.beats`); these are only the defaults a new newsroom starts with.
DEFAULT_BEATS = (
    "santé", "éducation", "politique", "économie", "énergie", "sécurité", "environnement",
    "transport", "sport", "culture", "société", "international",
)  # fmt: skip


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
    # Opt-in: the newsroom's published verdicts are shown to the public and it receives public tips.
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Newsroom settings, merged on PATCH (no migration for a new key): `beats` (its rubriques),
    # `timezone` (IANA, default Indian/Antananarivo), `ai_enabled` (off = only the fact checks
    # run, « Mode sans IA »), `country`.
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Set by the Checky team (PLATFORM_ADMINS), never by the newsroom: none | pending | approved |
    # refused. Until it is approved the newsroom works privately and nothing of it leaves.
    verification: Mapped[str] = mapped_column(String(16), default="none", server_default="none")
    # newsroom | institution. An institution (a ministry, a utility…) holds the portal: it seals
    # its own communiqués, declares its pages and numbers, and sees the fakes that use its name.
    # It is verified by the Checky team like a newsroom; there are no roles inside either.
    kind: Mapped[str] = mapped_column(String(16), default="newsroom", server_default="newsroom")

    @hybrid_property
    def publishes(self) -> bool:
        """Its verdicts, tips, SMS and registry may reach the public: opted in and verified."""
        return bool(self.is_public and self.verification == "approved")

    @publishes.inplace.expression
    @classmethod
    def _publishes(cls):
        return and_(cls.is_public.is_(True), cls.verification == "approved")


class NewsroomRequest(_Row):
    """A newsroom's request to be verified, read only by the Checky team (personal data)."""

    __tablename__ = "newsroom_request"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), unique=True
    )
    outlet: Mapped[str] = mapped_column(String(160))
    # radio | tv | press | online
    kind: Mapped[str] = mapped_column(String(16))
    city: Mapped[str] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    website: Mapped[str] = mapped_column(String(500))
    full_name: Mapped[str] = mapped_column(String(160))
    job_title: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(32))  # E.164
    email: Mapped[str] = mapped_column(String(254))
    press_card: Mapped[str | None] = mapped_column(String(120))
    submitted_by: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Membership(_Row):
    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"), {"schema": "app"})

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE")
    )
    user_id: Mapped[str] = mapped_column(Text, index=True)


class Invitation(_Row):
    __tablename__ = "invitation"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True)
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


class File(_Row):
    """An object uploaded to storage. `ready` once the browser's upload has been confirmed."""

    __tablename__ = "file"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    uploaded_by: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(String(400), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int]
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # EXIF for images, page count for PDFs, duration for audio later.
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Source(_Row):
    """A piece of evidence: a web page, a document, an image, audio or pasted text."""

    __tablename__ = "source"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.item.id", ondelete="SET NULL"), index=True
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.file.id", ondelete="SET NULL")
    )
    created_by: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    title: Mapped[str] = mapped_column(String(500), default="")
    url: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(300))
    published_at: Mapped[str | None] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text)


class Transcript(_Row):
    """Timestamped transcript of an audio source. Segments: [{start, end, text}] in seconds."""

    __tablename__ = "transcript"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.source.id", ondelete="CASCADE"), unique=True
    )
    language: Mapped[str | None] = mapped_column(String(10))
    duration_s: Mapped[float | None]
    model: Mapped[str] = mapped_column(String(80))
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # F3: key quotes and checkable claims picked by the AI, each tied to a timestamp.
    highlights: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Chunk(_Row):
    """A passage of a source with its embedding. `start_s`/`end_s` for transcripts."""

    __tablename__ = "chunk"
    __table_args__ = (
        Index(
            "ix_chunk_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"schema": "app"},
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.source.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    ord: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    start_s: Mapped[float | None]
    end_s: Mapped[float | None]
    embedding: Mapped[list[float]] = mapped_column(Vector(get_settings().embed_dim))
    embed_model: Mapped[str] = mapped_column(String(80))


class Place(Base):
    """A geocoded place (OpenStreetMap Nominatim), cached by the text that was looked up."""

    __tablename__ = "place"
    __table_args__ = {"schema": "app"}  # noqa: RUF012 - SQLAlchemy convention

    query: Mapped[str] = mapped_column(String(200), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(80))
    region: Mapped[str | None] = mapped_column(String(120))
    locality: Mapped[str | None] = mapped_column(String(120))
    lat: Mapped[float | None]
    lng: Mapped[float | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Contact(_Row):
    """The Annuaire: who can prove it. An institution, a press officer or an expert, with the topics
    and places they can settle, their official pages and how to reach them. Private to the newsroom
    unless `shared`. Never scraped personal numbers: entered by newsrooms or the institutions."""

    __tablename__ = "contact"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(
        String(20), default="institution"
    )  # institution|officer|expert|journalist|person|media|page
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200), default="")
    institution: Mapped[str] = mapped_column(String(200), default="")
    topics: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    # {name, country, region, locality, lat, lng}; empty = national / any place
    location: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    phone: Mapped[str | None] = mapped_column(String(60))
    whatsapp: Mapped[str | None] = mapped_column(String(60))
    email: Mapped[str | None] = mapped_column(String(200))
    website: Mapped[str | None] = mapped_column(Text)
    # [{"kind": "facebook|site|x|…", "url": "…", "verified": true}] declared by the institution
    official_pages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    hours: Mapped[str | None] = mapped_column(String(200))
    shared: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Track record kept by code: last_answer_hours, last_answered_at, asked, answered, communiques
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ContactRequest(_Row):
    """A question sent to a contact about a claim (« Envoyer la question »). The reply comes back
    through `token` without an account and becomes a dated source of the dossier."""

    __tablename__ = "contact_request"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.item.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.contact.id", ondelete="SET NULL")
    )
    created_by: Mapped[str] = mapped_column(Text)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    question: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), default="email")  # email|whatsapp|sms|call
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # {"stance": "confirms|denies|unknown", "text": "…", "name": "…"}
    answer: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.source.id", ondelete="SET NULL")
    )


class Communique(_Row):
    """The Registre: an original communiqué, decree or notice as its issuer published it, with the
    fingerprint of the file, so a circulating copy can be matched (Authentique / Modifié /
    Introuvable / Incohérent). `sealed` holds the issuer's Ed25519 signature when it has one."""

    __tablename__ = "communique"
    __table_args__ = (Index("ix_communique_issuer_number", "issuer", "number"), {"schema": "app"})

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    added_by: Mapped[str] = mapped_column(Text)
    issuer: Mapped[str] = mapped_column(String(200))
    number: Mapped[str | None] = mapped_column(String(60))
    issued_on: Mapped[str | None] = mapped_column(String(10))  # YYYY-MM-DD
    title: Mapped[str] = mapped_column(String(500), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    url: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.file.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(20), default="original")  # original|fake_caught
    # Workspaces (other newsrooms) that confirmed the entry; verified once a second one did.
    confirmed_by: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    # {"key_id", "payload", "signature", "sealed_at"} — see app/core/seal.py
    sealed: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    location: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class SealKey(_Row):
    """An issuer's Ed25519 key pair. The private key is stored encrypted with SEAL_SECRET; the
    public key is published so any phone can check a seal offline."""

    __tablename__ = "seal_key"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    issuer: Mapped[str] = mapped_column(String(200))
    key_id: Mapped[str] = mapped_column(String(40), unique=True)
    public_key: Mapped[str] = mapped_column(Text)  # base64 raw 32 bytes
    private_key_enc: Mapped[str] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InstitutionAlert(_Row):
    """« Alerte faux »: a check somewhere (desk, public page, extension, phone) met a text that uses
    a verified institution's name and does not match its registered communiqués (Modifié,
    Introuvable, Incohérent, or a fake a newsroom caught). The institution's press office sees it
    in its portal and may publish a denial. One row per distinct text: seen again, `count` grows.
    Which newsroom checked it is never kept."""

    __tablename__ = "institution_alert"
    __table_args__ = (UniqueConstraint("workspace_id", "fingerprint"), {"schema": "app"})

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    # modified | not_found | inconsistent | fake_caught
    status: Mapped[str] = mapped_column(String(20))
    # desk | public | extension | phone | sms: where the check was made
    channel: Mapped[str] = mapped_column(String(20), default="desk")
    text: Mapped[str] = mapped_column(Text, default="")
    fingerprint: Mapped[str] = mapped_column(String(64))
    # Where it circulated (the link checked), and a picture of it when the check had one.
    url: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    number: Mapped[str | None] = mapped_column(String(60))
    original_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.communique.id", ondelete="SET NULL")
    )
    count: Mapped[int] = mapped_column(default=1, server_default="1")
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # The denial the institution sealed in answer, or the moment it set the alert aside.
    denial_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.communique.id", ondelete="SET NULL")
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Figure(_Row):
    """« Chiffres officiels »: one official figure, dated and sourced. `workspace_id` empty = a
    figure every newsroom shares (World Bank, national statistics seeds)."""

    __tablename__ = "figure"
    __table_args__ = (Index("ix_figure_topic", "topic"), {"schema": "app"})

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    added_by: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(300))
    value: Mapped[str] = mapped_column(String(80))
    unit: Mapped[str | None] = mapped_column(String(40))
    as_of: Mapped[str | None] = mapped_column(String(10))  # YYYY-MM-DD, or YYYY
    country: Mapped[str | None] = mapped_column(String(80))
    location: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(Text)
    communique_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.communique.id", ondelete="SET NULL")
    )
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Signal(_Row):
    """« Mots surveillés »: a word or name the desk watches in bulletins, clips, tips and SMS."""

    __tablename__ = "signal"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[str] = mapped_column(Text)
    word: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    hits: Mapped[int] = mapped_column(default=0)


class Route(_Row):
    """« Le trajet »: one stop of a rumour (`side` = rumour: where it was seen) or of the truth
    (`side` = truth: where the correction went). Added by code on every gesture, or by hand."""

    __tablename__ = "route"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.item.id", ondelete="CASCADE"), index=True
    )
    added_by: Mapped[str] = mapped_column(Text)
    side: Mapped[str] = mapped_column(String(10))  # rumour|truth
    # facebook|whatsapp|tiktok|radio|sms|press|web|poster|institution|voice|other
    channel: Mapped[str] = mapped_column(String(20))
    place: Mapped[str] = mapped_column(String(300), default="")  # page, group, station, outlet
    location: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # the proof: {url, source_id, clip_at_s, screenshot_file_id, sms_count, note}
    proof: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # rumour stops: seen; truth stops: sent|received|broadcast
    status: Mapped[str] = mapped_column(String(20), default="seen")
    auto: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class RadioClip(_Row):
    """A veilleur's « Enregistrer » or a server-captured bulletin: a station, a time, a clip and
    what was heard (transcribed when French, said in one sentence when Malagasy)."""

    __tablename__ = "radio_clip"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[str] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.source.id", ondelete="SET NULL")
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.item.id", ondelete="SET NULL"), index=True
    )
    station: Mapped[str] = mapped_column(String(120))
    location: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    language: Mapped[str | None] = mapped_column(String(10))
    heard_text: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(20), default="veilleur")  # veilleur|capture
    status: Mapped[str] = mapped_column(String(20), default="new")  # new|followed|ignored|checked
    clip_at_s: Mapped[float | None]


class RadioPartner(_Row):
    """A partner radio that receives flashes and marks them « Diffusé » through a token link."""

    __tablename__ = "radio_partner"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    frequency: Mapped[str | None] = mapped_column(String(40))
    location: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    contact_role: Mapped[str | None] = mapped_column(String(120))
    whatsapp: Mapped[str | None] = mapped_column(String(60))
    sms: Mapped[str | None] = mapped_column(String(60))
    format_pref: Mapped[str] = mapped_column(String(20), default="script")  # script|audio
    hours: Mapped[str | None] = mapped_column(String(120))
    token: Mapped[str] = mapped_column(String(64), unique=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class PublicQuestion(_Row):
    """What people ask with no verdict yet (web « Me prévenir », SMS), by place; notified once a
    verdict is signed. Phone numbers are stored scrambled (HMAC) and shown masked."""

    __tablename__ = "public_question"

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="SET NULL"), index=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.item.id", ondelete="SET NULL"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(10), default="web")  # web|sms|voice
    location: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    contact_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    contact_masked: Mapped[str | None] = mapped_column(String(60))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemberPref(_Row):
    """« Ma rubrique »: a member's beats, places and language in a newsroom."""

    __tablename__ = "member_pref"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"), {"schema": "app"})

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(Text)
    beats: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    regions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    language: Mapped[str] = mapped_column(String(5), default="fr")
    station: Mapped[str | None] = mapped_column(String(120))  # a veilleur's radio


class JournalistProfile(_Row):
    """What a journalist gives at sign-up: how to reach them and a photo of their press card.

    The card lives in the private bucket under `press-cards/<user>/…` and is shown only to the
    owner and, through a short-lived link, to the Checky team that reviews newsroom requests.
    """

    __tablename__ = "journalist_profile"

    user_id: Mapped[str] = mapped_column(Text, unique=True)
    phone: Mapped[str] = mapped_column(String(24))
    outlet: Mapped[str] = mapped_column(String(160))
    card_number: Mapped[str | None] = mapped_column(String(60))
    card_key: Mapped[str] = mapped_column(String(400))
    card_filename: Mapped[str] = mapped_column(String(255))
    card_mime: Mapped[str] = mapped_column(String(120))
    card_size_bytes: Mapped[int]
    card_sha256: Mapped[str] = mapped_column(String(64), index=True)


class SmsSubscriber(Base):
    """« ABONNE »: a basic phone that receives the flashes of its region. Number stored scrambled."""

    __tablename__ = "sms_subscriber"
    __table_args__ = {"schema": "app"}  # noqa: RUF012 - SQLAlchemy convention

    phone_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    phone_masked: Mapped[str] = mapped_column(String(60))
    region: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(5), default="fr")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SmsMessage(_Row):
    """One SMS in (a question) or out (a verdict, a flash); the gateway phone polls the outbox."""

    __tablename__ = "sms_message"
    __table_args__ = (
        Index(
            "ix_sms_outbox",
            "created_at",
            postgresql_where="direction = 'out' AND status = 'queued'",
        ),
        {"schema": "app"},
    )

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="SET NULL"), index=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.item.id", ondelete="SET NULL"), index=True
    )
    direction: Mapped[str] = mapped_column(String(3))  # in|out
    phone_hash: Mapped[str] = mapped_column(String(64), index=True)
    phone_masked: Mapped[str] = mapped_column(String(60))
    text: Mapped[str] = mapped_column(String(480))
    # received (in) · queued → sending → sent → delivered, or failed (out) · simulated (fictional)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # In: the sender's number sealed (Fernet, `contact.seal`), the one copy a push gateway needs
    # to answer later. Out: why the gateway refused it, when it did.
    phone_sealed: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(String(200))


class Season(_Row):
    """« Ça revient »: a calendar rule for a country (cyclone season, exams, pay days, elections),
    so the desk hears about this week's likely rumours before they spread."""

    __tablename__ = "season"

    country: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(80))
    start_month: Mapped[int]
    end_month: Mapped[int]
    note: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)


class AiCacheEntry(Base):
    """A cached AI answer, keyed on the SHA-256 of the request (messages, tools, parameters)."""

    __tablename__ = "ai_cache"
    __table_args__ = {"schema": "app"}  # noqa: RUF012 - SQLAlchemy convention

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OfficialSource(_Row):
    """A site a newsroom declared official for its country (« Sources officielles » in Réglages).
    Shared with every newsroom of that country, but only counted from verified newsrooms."""

    __tablename__ = "official_source"
    __table_args__ = (UniqueConstraint("workspace_id", "host"), {"schema": "app"})

    country: Mapped[str] = mapped_column(String(80), index=True)  # as in workspace.settings
    host: Mapped[str] = mapped_column(String(253))
    name: Mapped[str] = mapped_column(String(160))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    added_by: Mapped[str] = mapped_column(Text)


class Show(_Row):
    """« Studio »: one live radio or TV show checked as it airs. The browser records 8–10 s
    chunks; French is transcribed into `segments` ({start, end, text, chunk}), Malagasy never is
    (the producer types what was said). `chunks` lists the stored audio ({seq, start_s,
    duration_s, key, mime, size, transcribed}); `settings` holds the sound input, the speakers
    ({id, name, camp}) and who speaks when (`turns`: {at_s, speaker_id})."""

    __tablename__ = "show"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(200))
    topics: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    language: Mapped[str] = mapped_column(String(5), default="fr")  # fr|mg
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|live|ended
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    chunks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class ShowClaim(_Row):
    """A checkable sentence heard during a show (spotted by code, by the one cheap model call, or
    typed by the producer), with its flag (« Conforme à… », « Contredit par… », « Aucune source
    trouvée », never a verdict) and what the producer did with it."""

    __tablename__ = "show_claim"

    show_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.show.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app.workspace.id", ondelete="CASCADE"), index=True
    )
    at_s: Mapped[float] = mapped_column(default=0.0)
    end_s: Mapped[float | None]
    text: Mapped[str] = mapped_column(Text)
    speaker_id: Mapped[str | None] = mapped_column(String(40))
    origin: Mapped[str] = mapped_column(String(10), default="code")  # code|model|typed
    spotted: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # {kind: consistent|contradicted|no_source, evidence: [...]} — computed from sources, no model
    flag: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|sent|dismissed
    question: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app.item.id", ondelete="SET NULL")
    )
