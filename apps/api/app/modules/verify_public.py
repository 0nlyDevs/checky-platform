"""« Est-ce déjà vérifié ? » in layers, for anyone, without an account.

1. A newsroom signed a verdict on it → that verdict, its byline and its confidence in words.
2. Otherwise a fact-checker published a review → relayed as *theirs* (« Vérifié par AFP Factuel »);
   no Malagasy newsroom needs to confirm it.
3. Otherwise the facts code can state at once: a communiqué diff against the registry of originals,
   an official figure, a video's first appearance, the tone of the message, and whether a newsroom
   already follows the rumour (« Une rédaction s'en occupe depuis … »).

Never a model verdict, never a percentage, never a dossier: the crew's fact agents (slice « crew »,
`crew.public_facts`) answer when they are there; otherwise this module asks the registry, the
figures, the tone lexicon and the fact-checkers itself, all without a model.
"""

import asyncio
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from app.core import dates, places, websearch
from app.core.access import Db
from app.core.errors import ApiError
from app.core.models import Item, Workspace
from app.core.public_checks import public_check_budget
from app.core.words import words
from app.modules import imagecheck, public

log = logging.getLogger("checky.verify_public")
router = APIRouter(tags=["public-verify"])

FACT_KEYS = ("provenance", "registry", "figures", "tone", "credibility")
# Who published a review, by the fact-checker's host (IFCN signatories and the French-speaking ones).
PUBLISHERS = {
    "factuel.afp.com": "AFP Factuel",
    "africacheck.org": "Africa Check",
    "observers.france24.com": "Les Observateurs de France 24",
    "lemonde.fr": "Les Décodeurs (Le Monde)",
    "francetvinfo.fr": "Vrai ou Fake (franceinfo)",
    "liberation.fr": "CheckNews (Libération)",
    "rfi.fr": "Les dessous de l'infox (RFI)",
    "20minutes.fr": "Fake Off (20 Minutes)",
    "snopes.com": "Snopes",
    "politifact.com": "PolitiFact",
    "factcheck.org": "FactCheck.org",
    "fullfact.org": "Full Fact",
    "maldita.es": "Maldita",
    "chequeado.com": "Chequeado",
    "boomlive.in": "BOOM",
    "altnews.in": "Alt News",
    "dubawa.org": "Dubawa",
    "pesacheck.org": "PesaCheck",
    "reuters.com": "Reuters Fact Check",
    "apnews.com": "AP Fact Check",
}
MATCH = 0.5  # same bar for « signed », « followed » and grouping questions (see public.overlap)


class VerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, max_length=6000)
    url: str | None = Field(default=None, max_length=2000)

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str | None) -> str | None:
        return imagecheck.ImageIn.public_http(value) if value else None

    @model_validator(mode="after")
    def content(self):
        self.text = (self.text or "").strip() or None
        if not self.url and len(self.text or "") < 3:
            raise ValueError("A public link or at least three text characters are needed")
        return self


class ReviewOut(BaseModel):
    publisher: str
    url: str
    rating: str | None  # the fact-checker's own words, never mapped onto our verdicts
    date: str | None
    title: str


class FactOut(BaseModel):
    kind: Literal["registry", "figure", "provenance", "tone", "credibility"]
    text: str
    source: str | None = None
    date: str | None = None
    url: str | None = None
    # registry: the word diff against the original ({op: equal|insert|delete|replace, a, b})
    diff: list[dict[str, Any]] = Field(default_factory=list)


class VerifyOut(BaseModel):
    status: Literal["signed", "external", "facts", "none"]
    signed: public.VerdictOut | None = None
    external: list[ReviewOut] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    known: list[FactOut] = Field(default_factory=list)
    followed_since: datetime | None = None
    tracked_ref: str | None = None
    tracked_id: uuid.UUID | None = None
    search_status: Literal["done", "unavailable", "skipped"] = "skipped"


# --- 1. a newsroom already signed it; 3b. a newsroom already follows it
async def followed(db: Db, text: str) -> Item | None:
    """The unpublished claim of a public newsroom that is about this text, if any."""
    asked = words(text)
    if len(asked) < 2:
        return None
    rows = await db.scalars(
        select(Item)
        .join(Workspace, Workspace.id == Item.workspace_id)
        .where(Workspace.is_public.is_(True), Item.type == "claim", Item.status != "published")
        .order_by(Item.created_at.desc())
        .limit(500)
    )
    best, best_score = None, 0.0
    for item in rows:
        score = max(
            (public.overlap(asked, w) for w in (words(item.title), words(item.body)) if w),
            default=0.0,
        )
        if score >= MATCH and score > best_score:
            best, best_score = item, score
    return best


def place_in(text: str) -> dict[str, Any]:
    """The Malagasy region or town a message names (offline gazetteer), or {}."""
    return places.gazetteer(re.sub(r"[^\w'’-]+", " ", text)) or {}


# --- 2. fact-checkers' reviews, relayed as theirs
def _query(text: str, n: int = 12) -> str:
    """The message's meaningful words in order, as a search query (no AI)."""
    seen: list[str] = []
    for token in re.findall(r"[\w'’-]+", text):
        if words(token) and token.lower() not in seen:
            seen.append(token.lower())
        if len(seen) >= n:
            break
    return " ".join(seen)


def _publisher(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for domain, name in PUBLISHERS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return host or "Fact-checkeur"


def review(raw: dict[str, Any], asked: set[str]) -> ReviewOut | None:
    """One fact-checker result as a relayed review, or None when it is not about this message."""
    url, title = str(raw.get("url") or ""), str(raw.get("title") or "").strip()
    if not url.startswith(("http://", "https://")) or not title:
        return None
    snippet = str(raw.get("snippet") or "")
    publisher, rating = raw.get("publisher"), raw.get("rating")
    if m := re.match(r"^(.+?) : « (.+?) »", snippet):  # websearch's ClaimReview line
        publisher, rating = publisher or m[1], rating or m[2]
    claim = snippet.split("Affirmation :", 1)[1] if "Affirmation :" in snippet else ""
    about = words(f"{title} {claim}")
    shared = asked & about
    if len(shared) < 2 or len(shared) / max(1, min(len(about), len(asked))) < 0.3:
        return None
    day = dates.parse(raw.get("date"))
    return ReviewOut(
        publisher=str(publisher or _publisher(url))[:120],
        url=url,
        rating=str(rating)[:120] if rating else None,
        date=day.isoformat() if day else None,
        title=title[:300],
    )


# --- 3. the facts, from the crew's fact agents or asked here without a model
async def _fallback_facts(db: Db, text: str, newsrooms: list[uuid.UUID | None]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    async def reviews():
        try:
            async with asyncio.timeout(20):
                return await websearch.fact_checks(_query(text), k=6)
        except (TimeoutError, websearch.SearchUnavailable, httpx.HTTPError) as exc:
            log.info("public verify: fact-checkers unavailable (%s)", type(exc).__name__)
            return None

    searching = asyncio.create_task(reviews())
    # One database session cannot run two queries at once: the registry and figures go in turn
    # while the fact-checkers are searched.
    try:
        from app.modules.registry import match_text

        for ws_id in newsrooms:
            found = await match_text(db, ws_id, text)
            if isinstance(found, dict) and found.get("status") not in (None, "none"):
                out["registry"] = found
                break
    except (ImportError, AttributeError):
        pass
    except Exception:  # another slice's agent: reported, never fatal
        log.exception("public verify: registry match failed")
    try:
        from app.modules.figures import check_numbers

        rows = await check_numbers(db, newsrooms[0], text)
        if rows:
            out["figures"] = [r for r in rows if isinstance(r, dict)]
    except (ImportError, AttributeError):
        pass
    except Exception:
        log.exception("public verify: figures check failed")
    try:
        from app.core.tone import analyse

        out["tone"] = analyse(text)
    except (ImportError, AttributeError):
        pass
    except Exception:
        log.exception("public verify: tone failed")
    out["fact_checks"] = await searching
    return out


async def gather_facts(db: Db, text: str, url: str | None) -> dict[str, Any]:
    try:
        from app.modules.crew import public_facts
    except (ImportError, AttributeError):
        public_facts = None
    if public_facts is not None:
        try:
            async with asyncio.timeout(45):
                found = await public_facts(db, text, url)
            if isinstance(found, dict):
                return found
        except Exception:  # the crew is down or slow: ask the agents here instead
            log.exception("public verify: crew.public_facts failed")
    rooms: list[uuid.UUID | None] = [w.id for w in await public.public_newsrooms(db)] or [None]
    return await _fallback_facts(db, text, rooms)


def _registry_fact(r: dict[str, Any]) -> FactOut | None:
    status, issuer = r.get("status"), r.get("issuer") or "l'institution"
    number = r.get("number") or ""
    original = r.get("communique") if isinstance(r.get("communique"), dict) else {}
    default = {
        "authentic": f"Le communiqué {number} de {issuer} existe tel quel dans le registre.",
        "modified": f"Le communiqué {number} de {issuer} existe, mais son texte a été modifié.",
        "not_found": f"Introuvable dans le registre de {issuer} (cela ne prouve rien à lui seul).",
        "inconsistent": f"Le numéro {number} ne suit pas la numérotation de {issuer}.",
    }.get(status)
    if default is None:
        return None
    return FactOut(
        kind="registry",
        text=str(r.get("summary") or default),
        source=f"Registre des originaux · {issuer}",
        date=original.get("issued_on"),
        url=original.get("url"),
        diff=[d for d in r.get("diff") or [] if isinstance(d, dict)][:200],
    )


def _figure_fact(r: dict[str, Any]) -> FactOut | None:
    fig = r.get("figure") if isinstance(r.get("figure"), dict) else None
    if not fig or r.get("verdict") not in ("matches", "differs"):
        return None
    official = (
        f"{fig.get('label')} : {fig.get('value')}{' ' + fig['unit'] if fig.get('unit') else ''}"
    )
    text = (
        f"Chiffre officiel : {official}. Le message annonce {r.get('claimed')}."
        if r["verdict"] == "differs"
        else f"Le chiffre {r.get('claimed')} correspond au chiffre officiel ({official})."
    )
    if fig.get("old"):
        text += " Ce chiffre officiel est ancien."
    return FactOut(
        kind="figure",
        text=text,
        source=fig.get("source_name"),
        date=fig.get("as_of"),
        url=fig.get("source_url"),
    )


def _provenance_fact(p: dict[str, Any]) -> FactOut | None:
    first = dates.parse(p.get("first_seen"))
    if not first:
        return None
    text = f"Cette image ou cette vidéo circulait déjà le {dates.fr(first)}."
    if p.get("verdict_hint") == "old_media_new_caption":
        text += " Une ancienne image est présentée comme nouvelle."
    links = p.get("reverse_links") or []
    first_link = links[0] if links and isinstance(links[0], dict) else {}
    return FactOut(
        kind="provenance",
        text=text,
        source=p.get("source") or "Recherche de la première apparition",
        date=first.isoformat(),
        url=first_link.get("url"),
    )


def _tone_fact(t: dict[str, Any]) -> FactOut | None:
    level = t.get("level")
    if level not in ("sensationnaliste", "marqué"):
        return None
    quotes = [s.get("quote") for s in t.get("signals") or [] if isinstance(s, dict)]
    quoted = ", ".join(f"« {q} »" for q in quotes[:4] if q)
    return FactOut(
        kind="tone",
        text=f"Ton {level} du message{(' : ' + quoted) if quoted else ''}.",
        source="Lexique du ton (sans IA)",
    )


KNOWN = {
    "fact_checker": "site d'un fact-checkeur reconnu",
    "official": "page officielle déclarée dans l'Annuaire",
    "press": "média de presse déclaré",
}


def _credibility_fact(c: dict[str, Any]) -> FactOut | None:
    domain = c.get("domain")
    if not domain:
        return None
    found = [
        str(s.get("detail") or s.get("key"))
        for s in c.get("signals") or []
        if isinstance(s, dict) and s.get("status") == "found"
    ]
    parts = [KNOWN[c["known"]]] if c.get("known") in KNOWN else []
    if found:
        parts.append("trouvé : " + ", ".join(found[:5]))
    if not parts:
        return None
    return FactOut(
        kind="credibility",
        text=f"Source {domain} : {' ; '.join(parts)}.",
        source="Fiabilité de la source (signaux, jamais une note)",
    )


def known_facts(facts: dict[str, Any]) -> list[FactOut]:
    out: list[FactOut | None] = []
    if isinstance(facts.get("provenance"), dict):
        out.append(_provenance_fact(facts["provenance"]))
    if isinstance(facts.get("registry"), dict):
        out.append(_registry_fact(facts["registry"]))
    out += [_figure_fact(r) for r in facts.get("figures") or [] if isinstance(r, dict)]
    if isinstance(facts.get("tone"), dict):
        out.append(_tone_fact(facts["tone"]))
    if isinstance(facts.get("credibility"), dict):
        out.append(_credibility_fact(facts["credibility"]))
    return [f for f in out if f is not None]


def _reviews_in(facts: dict[str, Any]) -> list[dict[str, Any]] | None:
    for key in ("fact_checks", "fact_checkers", "factcheckers", "reviews"):
        if key in facts:
            value = facts[key]
            if isinstance(value, dict):  # an agent's envelope {results: […]}
                value = value.get("results") or value.get("reviews")
            return [r for r in value or [] if isinstance(r, dict)] if value is not None else None
    return None


async def _read(url: str) -> str:
    from app.modules import linkcheck

    try:
        async with asyncio.timeout(15):
            page = await linkcheck.read_link(url)
    except (TimeoutError, ValueError, OSError, httpx.HTTPError):
        return ""
    return str(page.get("text") or page.get("title") or "")[:6000]


async def layered(db: Db, text: str, url: str | None) -> VerifyOut:
    if not text and url:
        text = await _read(url)
    if not text:
        return VerifyOut(status="none")
    signed = await public.best_published(db, text, k=1, threshold=MATCH)
    if signed:
        return VerifyOut(status="signed", signed=signed[0][1])
    facts = await gather_facts(db, text, url)
    raw_reviews = _reviews_in(facts)
    asked = words(text)
    seen, external = set(), []
    for raw in raw_reviews or []:
        r = review(raw, asked)
        if r and r.url not in seen:
            seen.add(r.url)
            external.append(r)
    tracked = await followed(db, text)
    known = known_facts(facts)
    status = "external" if external else "facts" if (known or tracked) else "none"
    return VerifyOut(
        status=status,
        external=external[:4],
        facts={k: facts[k] for k in FACT_KEYS if facts.get(k)},
        known=known,
        followed_since=tracked.created_at if tracked else None,
        tracked_ref=(tracked.data or {}).get("ref") if tracked else None,
        tracked_id=tracked.id if tracked else None,
        search_status="unavailable" if raw_reviews is None else "done",
    )


@router.post("/public/verify", dependencies=[Depends(public_check_budget)])
async def verify(body: VerifyIn, db: Db) -> VerifyOut:
    try:
        async with asyncio.timeout(60):
            return await layered(db, body.text or "", body.url)
    except TimeoutError as exc:
        raise ApiError(
            503, "public_check_unavailable", "The check took too long, try again"
        ) from exc
