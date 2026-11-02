"""« Sources officielles »: the official sites of a country, added by its newsrooms.

The rule in `confidence.is_official` already knows government domains everywhere (gov.mg,
gouv.sn, go.ke…) and a few institutes. A newsroom adds the rest for its country (a statistics
office, a regulator, a utility); the list is shared with every newsroom of that country. A site
counts for everyone only when the newsroom that added it is verified by Checky; it always counts
for the newsroom itself.
"""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import AnyMember, Db
from app.core.confidence import is_official
from app.core.errors import ApiError
from app.core.models import OfficialSource, Workspace
from app.core.places import fold

router = APIRouter(tags=["official"])


def host_of(value: str) -> str | None:
    from urllib.parse import urlsplit

    value = value.strip()
    if "://" not in value:
        value = "https://" + value
    try:
        host = (urlsplit(value).hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    host = host.removeprefix("www.")
    return host if "." in host and len(host) <= 253 else None


async def _country(db: AsyncSession, ws: uuid.UUID) -> str:
    from app.modules.workspaces import newsroom_settings

    return newsroom_settings(await db.get(Workspace, ws)).country


async def country_hosts(db: AsyncSession, ws: uuid.UUID) -> set[str]:
    """Hosts that count as official for this newsroom: its own entries, and those of verified
    newsrooms of the same country."""
    country = fold(await _country(db, ws))
    rows = await db.execute(
        select(OfficialSource.host, OfficialSource.country)
        .join(Workspace, Workspace.id == OfficialSource.workspace_id)
        .where(or_(OfficialSource.workspace_id == ws, Workspace.verification == "approved"))
    )
    return {h for h, c in rows.all() if fold(c) == country}


class OfficialIn(BaseModel):
    url: str = Field(min_length=4, max_length=500)
    name: str = Field(min_length=2, max_length=160)

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        return " ".join(value.split())


class OfficialOut(BaseModel):
    id: uuid.UUID
    host: str
    name: str
    country: str
    mine: bool
    # Counted for every newsroom of the country (added by a verified newsroom).
    shared: bool


@router.get("/workspaces/{ws}/official-sources")
async def list_official(member: AnyMember, db: Db) -> list[OfficialOut]:
    country = await _country(db, member.workspace_id)
    rows = await db.execute(
        select(OfficialSource, Workspace.verification)
        .join(Workspace, Workspace.id == OfficialSource.workspace_id)
        .order_by(OfficialSource.name)
    )
    out = []
    for o, verification in rows.all():
        mine = o.workspace_id == member.workspace_id
        shared = verification == "approved"
        if fold(o.country) != fold(country) or not (mine or shared):
            continue
        out.append(
            OfficialOut(
                id=o.id, host=o.host, name=o.name, country=o.country, mine=mine, shared=shared
            )
        )
    return out


@router.post("/workspaces/{ws}/official-sources", status_code=201)
async def add_official(body: OfficialIn, member: AnyMember, db: Db) -> OfficialOut:
    host = host_of(body.url)
    if host is None:
        raise ApiError(422, "invalid_url", "Give the site's address")
    if is_official(f"https://{host}"):
        raise ApiError(409, "already_official", "This site is already official by rule")
    country = await _country(db, member.workspace_id)
    existing = await db.scalar(select(OfficialSource).where(OfficialSource.host == host))
    if existing and fold(existing.country) == fold(country):
        raise ApiError(409, "already_listed", "This site is already listed for the country")
    o = OfficialSource(
        country=country,
        host=host,
        name=body.name,
        workspace_id=member.workspace_id,
        added_by=member.user.id,
    )
    db.add(o)
    await db.commit()
    ws = await db.get(Workspace, member.workspace_id)
    return OfficialOut(
        id=o.id,
        host=o.host,
        name=o.name,
        country=o.country,
        mine=True,
        shared=ws.verification == "approved",
    )


@router.delete("/workspaces/{ws}/official-sources/{source_id}", status_code=204)
async def remove_official(source_id: uuid.UUID, member: AnyMember, db: Db) -> None:
    o = await db.get(OfficialSource, source_id)
    if o is None or o.workspace_id != member.workspace_id:
        # Only the newsroom that added a site removes it.
        raise ApiError(404, "not_found", "Official source not found")
    await db.delete(o)
    await db.commit()
