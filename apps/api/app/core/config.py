from functools import lru_cache
from urllib.parse import parse_qsl, urlencode

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

    # S3-compatible object storage (Neon Object Storage); private bucket, presigned URLs only.
    storage_endpoint: str = ""
    storage_region: str = "eu-central-1"
    storage_access_key_id: str = ""
    storage_secret_access_key: str = ""
    storage_bucket: str = "uploads"

    # AI gateway: providers are tried in this order; one without a key is skipped.
    llm_providers: str = "groq,gemini,nvidia"
    groq_api_key: str = ""
    gemini_api_key: str = ""
    nvidia_api_key: str = ""
    # Empty means the gateway's default model for that provider.
    llm_model_groq: str = ""
    llm_model_gemini: str = ""
    llm_model_nvidia: str = ""
    ai_timeout: float = 30.0
    # Speech-to-text (Groq Whisper). large-v3 is the stronger one for Malagasy.
    stt_model: str = "whisper-large-v3"
    stt_timeout: float = 120.0
    # Attempts per provider on 429, 5xx or timeout before falling back to the next one.
    ai_attempts: int = 2
    # Development cache keyed on the request, so reloads do not burn free-tier quota.
    ai_cache: bool = False
    ai_cache_dir: str = ".ai-cache"

    @property
    def async_database_url(self) -> str:
        """Same DATABASE_URL as the web app, with the asyncpg driver for SQLAlchemy.

        Hosted Postgres (Neon) hands out libpq URLs; asyncpg takes `ssl` instead of
        `sslmode` and has no `channel_binding` parameter.
        """
        base, _, query = self.database_url.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        ).partition("?")
        params = [p for p in parse_qsl(query) if p[0] not in ("sslmode", "channel_binding")]
        sslmode = dict(parse_qsl(query)).get("sslmode")
        if sslmode:
            params.append(("ssl", sslmode))
        return f"{base}?{urlencode(params)}" if params else base

    @property
    def llm_provider_list(self) -> list[str]:
        return [p.strip() for p in self.llm_providers.split(",") if p.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
