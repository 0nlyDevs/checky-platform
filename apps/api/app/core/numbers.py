"""Numbers a text claims (« 72 heures », « +40 % », « 3 cas », « 25 674 196 habitants », « 3 300 ariary
le kilo »), found by code so they can be set against official figures without a model.

Only numbers that carry a unit are taken: a bare number is a date, a year, a reference (N° 2026-118)
or a phone number far more often than a claim. Times of day (« à 6 h », « 23h47 ») and dates
(« 3 novembre ») are left out on purpose.
"""

import re
import unicodedata
from typing import Any

from app.core.words import words

# 25 674 196 · 1.500 · 25,6 · 40 · +12 (thin and non-breaking spaces count as separators)
_NUMBER = r"[+\-−]?\s?(?:\d{1,3}(?:[   .]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
_SCALE = r"milliards?|millions?|mille|md|k"
_SCALES = {"milliard": 1e9, "milliards": 1e9, "md": 1e9, "million": 1e6, "millions": 1e6}
_SCALES |= {"mille": 1e3, "k": 1e3}

_PERCENT = r"%|pour\s?cent|pourcent|isan-jato"
_CURRENCY = r"ariary|mga|fmg|ar|euros?|€|us\s?\$|\$\s?us|dollars?|usd|\$"
_DURATION = (
    r"heures?|hrs?|h|minutes?|min|jours?|j|semaines?|mois|années?|ans?|ora|andro|volana|taona"
)
_COUNT = (
    r"cas|morts?|décès|victimes?|blessés?|personnes?|habitants?|malgaches|élèves?|candidats?"
    r"|ménages?|familles?|maisons?|enfants?|patients?|sinistrés?|déplacés?|tonnes?|kilos?|kg"
    r"|litres?|km|kilomètres?|mm|voix|bulletins?|quartiers?|fokontany|communes?|écoles?|lits?"
    r"|vaccins?|doses?|emplois?|salariés?|fonctionnaires?|médecins?|mponina|olona|maty"
)
_RATE = r"jour|j|semaine|mois|an|année|quartier|personne|habitant|kilo|kg|litre|kwh|mois"

_UNIT = rf"(?P<unit>{_PERCENT}|{_CURRENCY}|{_DURATION}|{_COUNT})"
PATTERN = re.compile(
    rf"(?<![\w/.,\-])(?P<num>{_NUMBER})"
    rf"(?:\s?(?P<scale>{_SCALE})\b)?"
    rf"\s?(?:d['’]\s?|de\s)?{_UNIT}(?![\w])"
    rf"(?:\s?(?:/|par|le|la|l['’])\s?(?P<per>{_RATE})\b)?",
    re.IGNORECASE,
)

# Hours in each duration unit, so « 3 jours » and « 72 heures » compare.
_HOURS = {"h": 1, "hr": 1, "hrs": 1, "heure": 1, "heures": 1, "ora": 1}
_HOURS |= {"min": 1 / 60, "minute": 1 / 60, "minutes": 1 / 60}
_HOURS |= {"j": 24, "jour": 24, "jours": 24, "andro": 24}
_HOURS |= {"semaine": 168, "semaines": 168, "mois": 730, "volana": 730}
_HOURS |= {"an": 8760, "ans": 8760, "année": 8760, "années": 8760, "taona": 8760}

_UP = {"hausse", "augmentation", "augmente", "plus", "monte", "grimpe", "bond", "fiakarana"}
_DOWN = {"baisse", "diminution", "diminue", "recul", "chute", "moins", "fihenanana"}
# « à 6 h », « vers 18 h », « dès 5 h »: a time of day, not a duration.
_TIME_BEFORE = {"a", "vers", "des", "avant", "apres", "jusqu", "jusqua", "depuis", "tamin", "amin"}
# Clauses end at these marks; the sentence is the wider context.
_CLAUSE = re.compile(r"[,;:!?\n()]|\.(?!\d)|\s[-–—]\s")
_SENTENCE = re.compile(r"[!?\n]|\.(?!\d)")


def _fold(text: str) -> str:
    flat = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in flat if not unicodedata.combining(c))


def _value(raw: str) -> float:
    s = raw.replace("−", "-").replace(" ", "").replace(" ", "").replace(" ", "")
    if re.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "")
    return float(s.replace(",", "."))


def _kind(unit: str) -> str:
    u = unit.lower()
    if re.fullmatch(_PERCENT, u, re.IGNORECASE):
        return "percent"
    if re.fullmatch(_CURRENCY, u, re.IGNORECASE):
        return "amount"
    if re.fullmatch(_DURATION, u, re.IGNORECASE):
        return "duration"
    return "count"


def _currency(unit: str) -> str:
    u = re.sub(r"\s", "", unit.lower())
    if u in ("ariary", "mga", "ar"):
        return "MGA"
    if u == "fmg":
        return "FMG"
    if u in ("euro", "euros", "€"):
        return "EUR"
    return "USD"


def _span(text: str, start: int, end: int, splitter: re.Pattern) -> str:
    left = max((m.end() for m in splitter.finditer(text, 0, start)), default=0)
    right = next((m.start() for m in splitter.finditer(text, end)), len(text))
    return re.sub(r"\s+", " ", text[left:right]).strip()


def _direction(text: str, start: int, raw: str) -> str | None:
    if raw.strip().startswith("+"):
        return "up"
    if raw.strip()[:1] in "-−":
        return "down"
    before = words(_fold(text[max(0, start - 40) : start]))
    if before & _UP:
        return "up"
    if before & _DOWN:
        return "down"
    return None


def extract_numbers(text: str) -> list[dict[str, Any]]:
    """Each number with a unit the text states: what it claims as written, its kind
    (percent|amount|count|duration), its value in a comparable base (hours, ariary, units),
    whether it is a rate (« par jour »), the direction words around it, and its context."""
    found: list[dict[str, Any]] = []
    text = text or ""
    for m in PATTERN.finditer(text):
        raw, unit = m["num"], m["unit"]
        start, end = m.start(), m.end()
        folded_before = _fold(text[max(0, start - 12) : start]).split()
        kind = _kind(unit)
        # 23h47, 6h30: a clock time; « à 6 h »: a time of day.
        clock = re.match(r"\d", text[end : end + 1]) or (
            folded_before and re.sub(r"\W", "", folded_before[-1]) in _TIME_BEFORE
        )
        if kind == "duration" and clock:
            continue
        try:
            number = _value(raw)
        except ValueError:
            continue
        scale = _SCALES.get((m["scale"] or "").lower(), 1)
        base = abs(number) * scale
        if kind == "duration":
            base = abs(number) * _HOURS.get(unit.lower(), 1)
        found.append(
            {
                "claimed": re.sub(r"\s+", " ", m.group(0)).strip(),
                "kind": kind,
                "value": abs(number) * scale,
                "base": base,
                "unit": unit,
                "currency": _currency(unit) if kind == "amount" else None,
                "per": (m["per"] or "").lower() or None,
                "direction": _direction(text, start, raw),
                "decimals": len(re.split(r"[.,]", raw.strip())[-1])
                if re.search(r",\d+$|\.\d{1,2}$", raw.strip())
                else 0,
                "context": _span(text, start, end, _SENTENCE)[:240],
                "clause": _span(text, start, end, _CLAUSE),
                "start": start,
                "end": end,
            }
        )
    return found


def parse_figure(value: str, unit: str | None) -> dict[str, Any] | None:
    """An official figure's value and unit read the same way as a claim (« 4 » « h/jour »)."""
    text = f"{value} {unit or ''}".strip()
    hits = extract_numbers(text)
    if hits:
        return hits[0]
    try:
        number = _value(value.strip())
    except ValueError:
        return None
    return {
        "claimed": text,
        "kind": "count",
        "value": abs(number),
        "base": abs(number),
        "unit": unit or "",
        "currency": None,
        "per": None,
        "direction": "up" if value.strip().startswith("+") else None,
        "decimals": 0,
    }


def same(claimed: dict[str, Any], official: dict[str, Any]) -> bool:
    """Whether a claimed number says what the official figure says, allowing for the rounding a
    person would do (« 30 millions » for 30,3 millions; « 12 % » for 12,4 %)."""
    if claimed["kind"] == "percent":
        both = claimed["direction"] and official.get("direction")
        if both and claimed["direction"] != official["direction"]:
            return False
        return abs(claimed["base"] - official["base"]) <= 0.5
    if claimed["kind"] == "duration" and (claimed["per"] or None) != (official.get("per") or None):
        return False
    if claimed["kind"] == "amount" and claimed["currency"] != official.get("currency"):
        return False
    if official["base"] == 0:
        return claimed["base"] == 0
    # The last digit written sets how precise the claim is: « 30 millions » means 29,5 to 30,5
    # millions, « 3 jours » 60 to 84 hours; never tighter than 2 % of the official figure.
    written = _value_digits(claimed)
    per_unit = claimed["base"] / written if written else 1
    step = 10 ** -claimed.get("decimals", 0) * per_unit
    tolerance = max(0.02 * official["base"], 0.5 * step)
    return abs(claimed["base"] - official["base"]) <= tolerance


def _value_digits(claimed: dict[str, Any]) -> float:
    """The number as written, before its scale word (« 30 » in « 30 millions »)."""
    m = re.match(rf"\s*({_NUMBER})", claimed["claimed"])
    try:
        return abs(_value(m[1])) if m else claimed["value"]
    except ValueError:
        return claimed["value"]
