"""Dated reference figures, attributed to an explicit source; no invented statistics."""

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from sqlalchemy import or_, select

from app.core import dates
from app.core.access import AnyMember, Db
from app.core.models import Figure

router = APIRouter(tags=["figures"])


class FigureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=300)
    value: str = Field(min_length=1, max_length=80)
    unit: str | None = Field(default=None, max_length=40)
    as_of: str = Field(min_length=4, max_length=10)
    country: str | None = Field(default=None, max_length=80)
    source_name: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl

    @field_validator("as_of")
    @classmethod
    def period(cls, value):
        parsed = dates.parse(value + "-01-01" if len(value) == 4 and value.isdigit() else value)
        if not parsed or parsed > dates.today():
            raise ValueError("Use a past or current YYYY or YYYY-MM-DD observation date")
        return value


class FigureOut(FigureIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


@router.get("/workspaces/{ws}/figures")
async def figures(
    member: AnyMember, db: Db, q: str = Query(default="", max_length=200)
) -> list[FigureOut]:
    stmt = select(Figure).where(
        or_(Figure.workspace_id == member.workspace_id, Figure.workspace_id.is_(None))
    )
    if q:
        stmt = stmt.where(
            or_(
                Figure.label.ilike(f"%{q}%"),
                Figure.topic.ilike(f"%{q}%"),
                Figure.country.ilike(f"%{q}%"),
            )
        )
    return [
        FigureOut.model_validate(row)
        for row in await db.scalars(stmt.order_by(Figure.as_of.desc()).limit(100))
    ]


@router.post("/workspaces/{ws}/figures", status_code=201)
async def create_figure(body: FigureIn, member: AnyMember, db: Db) -> FigureOut:
    figure = Figure(
        workspace_id=member.workspace_id, added_by=member.user.id, **body.model_dump(mode="json")
    )
    db.add(figure)
    await db.commit()
    return FigureOut.model_validate(figure)
