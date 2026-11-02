"""Dates the AI is given instead of left to guess, in Madagascar time and in French.

A model does not know today's date and is unreliable at date arithmetic, so the code works the
dates out: today, when a rumour was first seen, when each source was published, and how far
apart they are. Prompts carry the result as plain sentences; checks after the model use the
numbers.
"""

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

# Madagascar has no daylight saving time: a fixed offset needs no time zone database.
EAT = timezone(timedelta(hours=3))
MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
# A source published more than this before a rumour cannot confirm it on its own.
STALE_DAYS = 30


def now() -> datetime:
    return datetime.now(EAT)


def today() -> date:
    return now().date()


def parse_moment(value: Any) -> datetime | None:
    """A datetime in Madagascar time, from a datetime or an ISO string with a time zone."""
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    else:
        return None
    return moment.astimezone(EAT) if moment.tzinfo else moment


def parse(value: Any) -> date | None:
    """A calendar date from a datetime, an ISO string, EXIF ("2019:03:12 10:00:00") or PDF
    ("D:20190312…") metadata. Anything implausible (before 1990, after tomorrow) is unknown."""
    if isinstance(value, date) and not isinstance(value, datetime):
        found: date | None = value
    elif moment := parse_moment(value):
        found = moment.date()
    elif isinstance(value, str) and (m := re.search(r"(\d{4})[-:/]?(\d{2})[-:/]?(\d{2})", value)):
        try:
            found = date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    else:
        return None
    if found.year < 1990 or found > today() + timedelta(days=1):
        return None
    return found


def fr(d: date) -> str:
    """12 mars 2019, 1er mai 2026."""
    return f"{d.day}{'er' if d.day == 1 else ''} {MONTHS[d.month - 1]} {d.year}"


def fr_moment(moment: datetime) -> str:
    return f"{fr(moment.date())} à {moment:%H:%M}"


def span(days: int) -> str:
    """A distance in days, rounded the way a person would say it."""
    n = abs(days)
    if n < 60:
        return f"{n} jour{'s' if n > 1 else ''}"
    if n < 730:
        return f"{round(n / 30.44)} mois"
    return f"{n // 365} ans"


def today_line() -> str:
    """The sentence every prompt carries, so the model never guesses what day it is."""
    return f"Aujourd'hui : {fr(today())} (heure de Madagascar)."


def published_line(value: Any) -> str:
    """'publiée le 12 mars 2019' or 'date de publication inconnue'."""
    d = parse(value)
    return f"publiée le {fr(d)}" if d else "date de publication inconnue"


def gap(source: date, rumour: date) -> str:
    """Where a source sits against the rumour: '7 ans avant la rumeur', 'le jour de la rumeur'."""
    days = (rumour - source).days
    if days == 0:
        return "le jour de la rumeur"
    return f"{span(days)} {'avant' if days > 0 else 'après'} la rumeur"
