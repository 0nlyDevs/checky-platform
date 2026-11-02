"""Accent-free word sets, for matching claims by the words they share (no AI involved)."""

import re
import unicodedata

STOP = {
    *[
        "les",
        "des",
        "une",
        "un",
        "le",
        "la",
        "de",
        "du",
        "et",
        "en",
        "au",
        "aux",
        "pour",
        "par",
        "sur",
        "dans",
        "que",
        "qui",
        "est",
        "sont",
        "ce",
    ],
    *[
        "cette",
        "ces",
        "avec",
        "plus",
        "pas",
        "ont",
        "été",
        "the",
        "and",
        "ny",
        "sy",
        "amin",
        "ary",
        "izay",
        "dia",
        "fa",
    ],
}


def words(text: str) -> set[str]:
    flat = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]+", flat) if len(w) >= 3 and w not in STOP}
