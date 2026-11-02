"""Framing signals: how a text is written, distinct from whether it is true.

The Lecteur asks for them in its one model call; `clean_framing` keeps only verbatim quotes
and explicitly named targets. How solid a reading is lives in `app/core/confidence.py`, what a
site shows about itself in `app/core/credibility.py`. No publisher ratings, no ideology scale.
"""

from typing import Literal

from pydantic import BaseModel, Field


class FramingSignal(BaseModel):
    kind: Literal["loaded_language", "political_framing", "clickbait", "opinion_as_fact"]
    quote: str = Field(min_length=5, max_length=300)
    explanation: str = Field(min_length=1, max_length=400)
    target: str = Field(default="", max_length=120)


class EditorialDraft(BaseModel):
    signals: list[FramingSignal] = Field(default_factory=list, max_length=6)


def clean_framing(raw: dict, text: str) -> list[dict]:
    draft = EditorialDraft.model_validate(raw)
    out = []
    for signal in draft.signals:
        if signal.quote not in text:
            continue
        if signal.target and signal.target not in text:
            continue
        if signal.kind == "political_framing" and (
            not signal.target or signal.target not in signal.quote
        ):
            continue
        out.append(signal.model_dump())
    return out
