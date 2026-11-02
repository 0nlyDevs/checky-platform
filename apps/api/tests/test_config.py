from app.core.config import Settings


def _url(database_url: str) -> str:
    return Settings(database_url=database_url).async_database_url


def test_plain_url_gets_the_asyncpg_driver():
    assert _url("postgresql://u:p@localhost:5432/fanilo") == (
        "postgresql+asyncpg://u:p@localhost:5432/fanilo"
    )


def test_libpq_ssl_params_are_translated_for_asyncpg():
    # Neon hands out libpq-style URLs; asyncpg rejects sslmode/channel_binding.
    url = _url(
        "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    assert url == "postgresql+asyncpg://u:p@ep-x.eu-central-1.aws.neon.tech/neondb?ssl=require"


def test_other_query_params_are_kept():
    url = _url("postgresql://u:p@h/db?sslmode=verify-full&application_name=api")
    assert url == "postgresql+asyncpg://u:p@h/db?application_name=api&ssl=verify-full"
