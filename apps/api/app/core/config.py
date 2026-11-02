from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")

    database_url: str = "postgresql://fanilo:fanilo@localhost:5432/fanilo"
    # Tests run each request on a fresh event loop, so pooled connections must be off there.
    db_pool: bool = True
    # Number of in-process job workers; 0 disables them (tests run jobs explicitly).
    job_workers: int = 2

    auth_jwks_url: str = "http://localhost:3000/api/auth/jwks"
    auth_issuer: str = "http://localhost:3000"
    auth_audience: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    @property
    def async_database_url(self) -> str:
        # Same DATABASE_URL as the web app, with the asyncpg driver for SQLAlchemy.
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
