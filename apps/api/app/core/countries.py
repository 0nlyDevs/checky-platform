"""Countries by ISO 3166-1 alpha-2 code, with French names and phone numbers, from `phonenumbers`.

Checky works in any country: nothing here is tied to Madagascar except the default.
"""

from functools import cache

import phonenumbers
from phonenumbers import geocoder

DEFAULT = "MG"


@cache
def name(code: str, lang: str = "fr") -> str | None:
    """« Madagascar » for "MG"; None for a code phonenumbers does not know."""
    code = code.upper()
    if code not in phonenumbers.SUPPORTED_REGIONS:
        return None
    example = phonenumbers.example_number(code)
    return (geocoder.country_name_for_number(example, lang) if example else None) or code


@cache
def all_countries(lang: str = "fr") -> list[tuple[str, str]]:
    """Every (code, name), sorted by name."""
    pairs = [(c, name(c, lang) or c) for c in phonenumbers.SUPPORTED_REGIONS]
    return sorted(pairs, key=lambda p: p[1].casefold())


def code_for(value: str | None) -> str | None:
    """A code from a code or a French name (« Madagascar » → "MG")."""
    if not value:
        return None
    value = value.strip()
    if value.upper() in phonenumbers.SUPPORTED_REGIONS:
        return value.upper()
    folded = value.casefold()
    return next((c for c, n in all_countries() if n.casefold() == folded), None)


def phone(raw: str, country: str = DEFAULT) -> str | None:
    """The number in E.164 (+261341234567), read as a local number of `country`; None if invalid."""
    try:
        parsed = phonenumbers.parse(raw, country.upper())
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def phones_in(text: str, country: str = DEFAULT, limit: int = 6) -> list[tuple[str, str]]:
    """The valid phone numbers a text gives, as (as written, E.164), in order, without repeats.
    Years, amounts and communiqué numbers (« N° 2026-118 », « 1 200 000 Ar ») are not numbers."""
    out: list[tuple[str, str]] = []
    matcher = phonenumbers.PhoneNumberMatcher(
        text or "", country.upper(), leniency=phonenumbers.Leniency.STRICT_GROUPING
    )
    for match in matcher:
        e164 = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
        if e164 not in [e for _, e in out]:
            out.append((match.raw_string, e164))
        if len(out) >= limit:
            break
    return out


def display(e164: str) -> str:
    """« +261341234567 » → « +261 34 12 345 67 », the way the country writes it abroad."""
    try:
        parsed = phonenumbers.parse(e164)
    except phonenumbers.NumberParseException:
        return e164
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
