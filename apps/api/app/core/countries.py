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
