from functools import lru_cache
from typing import Literal
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

    # AI gateway: providers are tried in this order; one without a key is skipped. Each *_API_KEY
    # may hold several keys separated by commas (one per teammate); they are used in turn.
    llm_providers: str = "groq,gemini,nvidia,claude"
    groq_api_key: str = ""
    gemini_api_key: str = ""
    nvidia_api_key: str = ""
    claude_api_key: str = ""
    # Optional: Google Fact Check Tools (claim reviews by fact-checkers worldwide), a Google Cloud
    # API key with that API enabled.
    google_factcheck_api_key: str = ""
    search_ipv4_only: bool = True
    web_search_provider: Literal["auto", "tavily", "duckduckgo"] = "auto"
    tavily_api_key: str = ""
    # Empty means the gateway's default model for that provider.
    llm_model_groq: str = ""
    llm_model_gemini: str = ""
    llm_model_nvidia: str = ""
    llm_model_claude: str = ""
    # Claude thinks before answering; "low" keeps chat answers quick and cheap.
    claude_effort: str = "low"
    ai_timeout: float = 30.0
    # Embeddings for RAG. Chosen on 25 Oct: both Gemini models scored 18/18 on French, Malagasy
    # and cross-language retrieval; embedding-2 is the newer one. Never change mid-event without
    # rebuilding every vector (scripts/reembed_all.py).
    embed_provider: str = "gemini"
    embed_model: str = "gemini-embedding-2"
    embed_dim: int = 768
    # Speech-to-text (Groq Whisper). large-v3 is the stronger one for Malagasy.
    stt_model: str = "whisper-large-v3"
    stt_timeout: float = 120.0
    # Text to speech for the assistant's voice mode (optional; without a key the browser's voice reads)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = (
        "JBFqnCBsd6RMkjVDRZzb"  # "George", a default voice (free plans cannot use library voices)
    )
    elevenlabs_model: str = "eleven_flash_v2_5"
    elevenlabs_model_mg: str = (
        "eleven_v3"  # Malagasy: no language code on these models, v3 sounds best
    )
    # Attempts per provider on 429, 5xx or timeout before falling back to the next one.
    ai_attempts: int = 2
    # Cache keyed on the request (stored in app.ai_cache), so reloads and demo rehearsals do
    # not burn free-tier quota.
    ai_cache: bool = False
    # Largest estimated prompt (tokens) a provider is sent; bigger ones go straight to the next
    # provider. Groq's free tier allows 8 000 tokens per minute, so a 12 000-token prompt can only
    # fail there. 0 = no limit.
    llm_max_prompt_tokens_groq: int = 6000
    llm_max_prompt_tokens_gemini: int = 0
    llm_max_prompt_tokens_nvidia: int = 0
    llm_max_prompt_tokens_claude: int = 0
    # How long a provider key is set aside after a 429 or repeated failures (seconds).
    ai_cooldown: float = 30.0

    # Optional pixel detector. Off until an operator configures AND evaluates a service.
    # Only this server holds its credential; selected image bytes never go to it by default.
    image_detector_url: str = ""
    image_detector_token: str = ""
    image_detector_validated: bool = False
    # Or Sightengine's `genai` model (https://sightengine.com, free plan): both keys set = configured.
    # It takes precedence over IMAGE_DETECTOR_URL and still waits for IMAGE_DETECTOR_VALIDATED.
    sightengine_api_user: str = ""
    sightengine_api_secret: str = ""
    # Anonymous checks have no LLM verdict generation. Both routes share these per-process caps.
    public_checks_per_window: int = 12  # requests per address, per 10 minutes
    public_checks_per_day: int = 1000  # all addresses, per 24-hour budget period
    public_checks_concurrency: int = 2
    # Query preparation only, never an anonymous truth verdict. Paid Claude is excluded in code.
    public_preparation_enabled: bool = True
    public_preparation_providers: str = "groq,gemini,nvidia"
    # Separate opt-in: a validated private detector is not automatically offered anonymously.
    public_image_detector_enabled: bool = False
    # Header holding the visitor's address, set by the edge proxy itself (rate limits key on it).
    # Empty = the socket peer; on Render (RENDER set) it defaults to Cloudflare's CF-Connecting-IP.
    client_ip_header: str = ""

    # Where the public site lives (links in SMS, cards, posters, attestations: /verifies/{id}).
    public_web_url: str = "http://localhost:3000"
    # Encrypts issuers' private seal keys at rest and signs attestations; any long random string.
    seal_secret: str = ""
    # The Android SMS gateway (or the simulator in Paramètres) sends `X-Gateway-Secret` with it.
    sms_gateway_secret: str = ""
    # Radio streams captured for « À l'antenne »: "Station|https://stream.url|Region,…" (empty = off).
    radio_streams: str = ""
    # RSS feeds of the national press for Veille (comma list; empty = off).
    press_feeds: str = ""

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
