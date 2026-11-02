"""Workspace-curated contacts. A declared official page is not automatically verified."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import or_, select

from app.core.access import AnyMember, Db, Editor
from app.core.activity import record
from app.core.errors import ApiError
from app.core.models import Contact

router = APIRouter(tags=["directory"])


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="", max_length=200)
    institution: str = Field(default="", max_length=200)
    topics: list[str] = Field(default_factory=list, max_length=20)
    phone: str | None = Field(default=None, max_length=60, pattern=r"^\+?[0-9 ()-]{3,60}$")
    email: str | None = Field(default=None, max_length=200, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    website: HttpUrl | None = None


class ContactOut(ContactIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    verified_at: datetime | None
    verified_by: str | None


@router.get("/workspaces/{ws}/contacts")
async def contacts(
    member: AnyMember, db: Db, q: str = Query(default="", max_length=200)
) -> list[ContactOut]:
    stmt = select(Contact).where(Contact.workspace_id == member.workspace_id)
    if q:
        stmt = stmt.where(
            or_(
                Contact.name.ilike(f"%{q}%"),
                Contact.institution.ilike(f"%{q}%"),
                Contact.role.ilike(f"%{q}%"),
            )
        )
    return [
        ContactOut.model_validate(row)
        for row in await db.scalars(stmt.order_by(Contact.name).limit(100))
    ]


@router.post("/workspaces/{ws}/contacts", status_code=201)
async def create_contact(body: ContactIn, member: AnyMember, db: Db) -> ContactOut:
    contact = Contact(
        workspace_id=member.workspace_id, created_by=member.user.id, **body.model_dump(mode="json")
    )
    db.add(contact)
    await db.flush()
    await record(db, member.workspace_id, member.user.id, "contact", contact.id, "create")
    await db.commit()
    return ContactOut.model_validate(contact)


@router.patch("/workspaces/{ws}/contacts/{contact_id}")
async def edit_contact(
    contact_id: uuid.UUID, body: ContactIn, member: Editor, db: Db
) -> ContactOut:
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Contact not found")
    for key, value in body.model_dump(mode="json").items():
        setattr(contact, key, value)
    # Changing identity or channels invalidates any previous verification.
    contact.verified_at = contact.verified_by = None
    await record(db, member.workspace_id, member.user.id, "contact", contact.id, "update")
    await db.commit()
    return ContactOut.model_validate(contact)
