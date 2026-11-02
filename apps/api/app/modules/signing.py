"""Explicit newsroom signatures; no automatic publication from an AI result."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.access import AnyMember, Db
from app.core.activity import broadcast, record
from app.core.errors import ApiError
from app.core.models import Item, Workspace
from app.modules.items import ItemOut

router = APIRouter(tags=["signing"])
SIGNATURE_FIELDS = {"signed_by", "signed_at", "signed_digest", "published_by", "published_at"}


class SignIn(BaseModel):
    verdict: Literal["true", "false", "misleading", "unverifiable"]
    reason: str = Field(min_length=10, max_length=2000)
    publish: bool = False


def digest(title, body, data):
    return hashlib.sha256(
        json.dumps(
            {
                "title": title,
                "body": body,
                "verdict": data.get("verdict"),
                "reason": data.get("reason"),
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


async def publication_guard(db, member, status, title, body, data):
    if status != "published":
        return
    if data.get("verdict") not in ("true", "false", "misleading", "unverifiable"):
        raise ApiError(409, "no_verdict", "A newsroom verdict is required to publish")
    workspace = await db.get(Workspace, member.workspace_id)
    if not (workspace.settings or {}).get("double_signature"):
        return
    if not member.at_least("editor"):
        raise ApiError(403, "editor_required", "An editor must release this verdict")
    if not data.get("signed_by") or data.get("signed_digest") != digest(title, body, data):
        raise ApiError(409, "signature_required", "Sign the current version before publication")
    if data["signed_by"] == member.user.id:
        raise ApiError(
            409, "second_signer_required", "A different editor must release this verdict"
        )


@router.post("/workspaces/{ws}/items/{item_id}/sign")
async def sign(item_id: uuid.UUID, body: SignIn, member: AnyMember, db: Db) -> ItemOut:
    item = await db.scalar(
        select(Item)
        .where(Item.id == item_id, Item.workspace_id == member.workspace_id)
        .with_for_update()
    )
    if item is None:
        raise ApiError(404, "not_found", "Item not found")
    if item.author_id != member.user.id and not member.at_least("editor"):
        raise ApiError(403, "forbidden", "Only the author or an editor can sign this dossier")
    workspace = await db.get(Workspace, member.workspace_id)
    data = {
        **item.data,
        "verdict": body.verdict,
        "reason": body.reason,
        "signed_by": member.user.id,
        "signed_at": datetime.now(UTC).isoformat(),
    }
    data["signed_digest"] = digest(item.title, item.body, data)
    # Under double signature this endpoint signs only; another editor releases via PATCH.
    item.status = (
        "published"
        if body.publish and not workspace.settings.get("double_signature")
        else "verified"
    )
    item.data = data
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "item",
        item.id,
        "sign",
        {"verdict": body.verdict, "status": item.status},
    )
    await db.commit()
    await db.refresh(item)
    await broadcast(
        member.workspace_id, "item.updated", ItemOut.model_validate(item).model_dump(mode="json")
    )
    return ItemOut.model_validate(item)
