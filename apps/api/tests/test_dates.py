"""Dates are worked out in code, in Madagascar time, and written out in French."""

from datetime import UTC, date, datetime, timedelta

from app.core import dates


def test_parse_reads_the_formats_sources_come_in():
    assert dates.parse("2019-01-14") == date(2019, 1, 14)
    # 22:30 UTC is already the next day in Antananarivo (UTC+3).
    assert dates.parse("2026-10-28T22:30:00Z") == date(2026, 10, 29)
    assert dates.parse("2019:03:12 10:00:00") == date(2019, 3, 12)  # EXIF
    assert dates.parse("D:20190312101500+02'00'") == date(2019, 3, 12)  # PDF
    assert dates.parse(datetime(2026, 10, 28, 22, 30, tzinfo=UTC)) == date(2026, 10, 29)
    for unknown in (None, "", "hier", "12/03/2019", "2019-13-40", "1970-01-01"):
        assert dates.parse(unknown) is None
    assert dates.parse(dates.today() + timedelta(days=5)) is None  # the future is a bad date


def test_dates_are_said_in_french():
    assert dates.fr(date(2019, 3, 12)) == "12 mars 2019"
    assert dates.fr(date(2026, 5, 1)) == "1er mai 2026"
    rumour = date(2026, 10, 29)
    assert dates.gap(date(2026, 10, 29), rumour) == "le jour de la rumeur"
    assert dates.gap(date(2026, 10, 28), rumour) == "1 jour avant la rumeur"
    assert dates.gap(date(2026, 8, 29), rumour) == "2 mois avant la rumeur"
    assert dates.gap(date(2019, 1, 14), rumour) == "7 ans avant la rumeur"
    assert dates.gap(date(2026, 11, 2), rumour) == "4 jours après la rumeur"
    assert dates.published_line("2019-01-14") == "publiée le 14 janvier 2019"
    assert dates.published_line(None) == "date de publication inconnue"


def test_a_page_date_guessed_as_today_without_metadata_is_unknown():
    from app.workers.ingest import page_date

    today, old = dates.today().isoformat(), "2019-02-08"
    bare = "<html><body><p>Jeudi, le site affiche la date du jour.</p></body></html>"
    assert page_date(bare, today) is None  # the site's header, not the article's date
    assert page_date(bare, old) == old
    og = f'<meta property="article:published_time" content="{today}T06:00:00+03:00">'
    assert page_date(f"<html><head>{og}</head></html>", None) == today
    ld = '<script type="application/ld+json">{"datePublished": "2019-01-28T15:51:17Z"}</script>'
    assert page_date(f"<html>{ld}</html>", today) == "2019-01-28"  # metadata beats the guess
