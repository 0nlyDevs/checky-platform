from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_settings = get_settings()
engine = create_async_engine(
    _settings.async_database_url,
    pool_pre_ping=True,
    **({} if _settings.db_pool else {"poolclass": NullPool}),
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """All app tables live in the `app` schema; Better Auth owns `better_auth`."""


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
