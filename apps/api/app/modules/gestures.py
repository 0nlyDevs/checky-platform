"""« Les gestes » of a fact-checker, done in code: who a message says it comes from, and whether
its page, its phone number and its press headline are the ones on record.

    attribution     « Selon le ministère… »: the institution a message speaks for, against the
                    registry of originals (« Aucun communiqué de JIRAMA au registre ne dit cela »)
    official_page   a Facebook, TikTok, X, Instagram or YouTube page or a site, against the pages
                    the Annuaire's contacts declared (verified / declared / another page declared)
    number          phone numbers in a notice, against the numbers the Annuaire's contacts
                    declared (« Ce numéro n'est pas un numéro déclaré de … », never « arnaque »)
    press_article   a headline attributed to an outlet of the Annuaire, against that outlet's
                    items kept by Veille

Each fact is `{kind, status, text, subject, proof}`; no model is involved and nothing is
concluded: « Introuvable » never means « Faux ». Desk only: it reads the newsroom's own contacts
and those other newsrooms shared, and the registry of the newsrooms that publish. Phone numbers
are read with `app.core.countries` in the newsroom's country.
"""

import re
import uuid
from collections import defaultdict
from typing import Any
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import countries, credibility, dates, places
from app.core.access import AnyMember, Db
from app.core.errors import ApiError
from app.core.models import Communique, Contact, Item, Workspace
from app.core.words import words

router = APIRouter(tags=["gestures"])

# Words that present a statement as coming from someone (French, Malagasy, English).
CUES = re.compile(
    r"\b(selon|d['’]apr[eè]s|annonc\w*|inform\w*|affirm\w*|d[ée]clar\w*|confirm\w*|indiqu\w*"
    r"|pr[ée]cis\w*|communiqu\w*|ordonn\w*|d[ée]cid\w*|fait savoir|a dit|dit que|estime|assure"
    r"|araka|hoy|nambara\w*|nanambara|nilaza|milaza|according to|announc\w*|said|says|stated)\b",
    re.IGNORECASE,
)
SENTENCE = re.compile(r"(?<=[.!?…])\s+|\n+")
PLATFORMS: dict[str, tuple[str, ...]] = {
    "facebook": ("facebook.com", "fb.com", "fb.me"),
    "tiktok": ("tiktok.com",),
    "x": ("x.com", "twitter.com"),
    "instagram": ("instagram.com",),
    "youtube": ("youtube.com",),
}
# A page written without its scheme in a notice: « facebook.com/jirama.officiel ».
BARE_PAGE = re.compile(
    r"(?<![\w/.])(?:https?://)?(?:www\.|m\.|web\.)?(?:facebook|fb|tiktok|x|twitter|instagram)\.com"
    r"/[\w.@/?=&-]+",
    re.IGNORECASE,
)
LINK = re.compile(r"https?://[^\s<>«»\"]+")
# Paths that are not a page (a video, a share link, a search…).
NOT_PAGES = {"watch", "share", "sharer", "sharer.php", "events", "hashtag", "photo", "photo.php",
             "reel", "reels", "stories", "login", "home.php", "search", "marketplace"}  # fmt: skip


# --- shared helpers --------------------------------------------------------------------------


def _demo_free(name: str) -> str:
    return re.sub(r"\s*\(\s*d[ée]mo\s*\)\s*", " ", name or "", flags=re.IGNORECASE).strip()


def label(c: Contact) -> str:
    """How a contact is named in a fact: its institution, else its name (without « (démo) »)."""
    if c.kind == "officer" and c.institution:
        return c.institution
    return _demo_free(c.name) or c.institution


def _aliases(name: str) -> set[str]:
    from app.modules.registry import _aliases

    return _aliases(_demo_free(name))


def _mentions(text: str, name: str) -> bool:
    from app.modules.registry import _mentions

    return bool(name) and _mentions(places.fold(text), _demo_free(name))


def _same(a: str, b: str) -> bool:
    return _mentions(a, b) or _mentions(b, a)


def _compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", places.fold(s))


def _verified_on(c: Contact) -> str | None:
    return dates.fr(c.verified_at.astimezone(dates.EAT).date()) if c.verified_at else None


async def contacts(db: AsyncSession, ws: uuid.UUID) -> list[Contact]:
    """The Annuaire a check reads: the newsroom's own entries and those other newsrooms shared."""
    stmt = select(Contact).where(or_(Contact.workspace_id == ws, Contact.shared.is_(True)))
    return list(await db.scalars(stmt.order_by(Contact.created_at).limit(800)))


def fact(kind: str, status: str, text: str, subject: str = "", **proof: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": status,
        "text": text,
        "subject": subject,
        "proof": {k: v for k, v in proof.items() if v not in (None, "", [], {})},
    }


# --- « Page officielle ? » -------------------------------------------------------------------


def page_key(url: str | None) -> tuple[str, str] | None:
    """(platform, handle) for a social page, ("site", registrable domain) for a website, or None
    for a link that is not a page (a Facebook video, a share link…). Case and dots do not count."""
    raw = (url or "").strip()
    if not raw or raw.lower().startswith("tel:"):
        return None
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    for prefix in ("www.", "m.", "mobile.", "web.", "mbasic."):
        host = host.removeprefix(prefix)
    if not host or "." not in host:
        return None
    segments = [s for s in parts.path.split("/") if s]
    query = parse_qs(parts.query)
    for platform, hosts in PLATFORMS.items():
        if not any(host == h or host.endswith("." + h) for h in hosts):
            continue
        handle = None
        if platform == "facebook":
            if query.get("id") and (not segments or segments[0].endswith(".php")):
                handle = "id:" + query["id"][0]
            elif segments and segments[0] in ("pages", "pg") and len(segments) > 1:
                handle = segments[1]
            elif segments and segments[0] == "groups" and len(segments) > 1:
                handle = "groups/" + segments[1]
            elif segments and segments[0].lower() not in NOT_PAGES:
                handle = segments[0]
        elif platform == "youtube":
            if segments and segments[0].startswith("@"):
                handle = segments[0]
            elif len(segments) > 1 and segments[0] in ("channel", "c", "user"):
                handle = segments[1]
        elif segments:
            handle = segments[0]
        if not handle or handle.lower() in NOT_PAGES:
            return None
        handle = handle.lower().lstrip("@").replace(".", "")
        return (platform, handle) if handle else None
    return ("site", credibility.registrable(host))


def show_page(url: str) -> str:
    """« facebook.com/jirama.officiel », the way a person reads it aloud."""
    try:
        parts = urlsplit(url if "://" in url else "https://" + url)
    except ValueError:
        return url
    host = (parts.hostname or "").removeprefix("www.")
    path = parts.path.rstrip("/")
    return f"{host}{path}" if path and path != "/" else host


def _declared_pages(c: Contact, verified_only: bool) -> list[str]:
    """The pages a contact declared (its official numbers aside); with `verified_only`, only once
    a journalist verified the contact."""
    if verified_only and not c.verified_at:
        return []
    out = [
        str(p.get("url"))
        for p in c.official_pages or []
        if p.get("kind") != "phone" and p.get("url") and (p.get("verified") or not verified_only)
    ]
    if c.website and c.website not in out:
        out.append(c.website)
    return out


async def official_page(
    db: AsyncSession,
    ws: uuid.UUID,
    url: str,
    *,
    title: str | None = None,
    pool: list[Contact] | None = None,
) -> dict[str, Any]:
    """Is this page one a contact declared in the Annuaire? `declared` (verified),
    `declared_unverified` (declared, not yet verified by the newsroom), `other_page` (the page
    carries an institution's name, the institution declared another one) or `not_declared`."""
    key = page_key(url)
    subject = show_page(url)
    if key is None:
        return fact("official_page", "not_a_page", "Ce lien n'est pas une page : rien à comparer.",
                    subject)  # fmt: skip
    pool = pool if pool is not None else await contacts(db, ws)
    for verified_only in (True, False):
        for c in pool:
            for page in _declared_pages(c, verified_only):
                if page_key(page) != key:
                    continue
                who = label(c)
                if verified_only:
                    return fact(
                        "official_page",
                        "declared",
                        f"Page déclarée officielle par {who}, vérifiée le {_verified_on(c)}.",
                        subject,
                        institution=who,
                        url=page,
                        verified_on=_verified_on(c),
                        contact_id=str(c.id),
                    )
                return fact(
                    "official_page",
                    "declared_unverified",
                    f"Page déclarée par {who} dans l'Annuaire, pas encore vérifiée par la "
                    "rédaction.",
                    subject,
                    institution=who,
                    url=page,
                    contact_id=str(c.id),
                )
    # The page carries an institution's name (in its address or its title) that declared others.
    handle = _compact(key[1])
    for c in pool:
        declared = _declared_pages(c, True)
        if not declared:
            continue
        who = label(c)
        names = {a for n in (c.name, c.institution) if n for a in _aliases(n)}
        in_handle = any(len(_compact(a)) >= 4 and _compact(a) in handle for a in names)
        in_title = bool(title) and any(_mentions(title or "", n) for n in (c.name, c.institution))
        if not (in_handle or in_title):
            continue
        same_kind = [p for p in declared if (page_key(p) or ("", ""))[0] == key[0]] or declared
        shown = ", ".join(show_page(p) for p in same_kind[:3])
        noun = "un autre site" if key[0] == "site" else "une autre page"
        return fact(
            "official_page",
            "other_page",
            f"{who} a déclaré {noun} : {shown}. Celle-ci porte son nom mais n'est pas dans "
            "l'Annuaire.",
            subject,
            institution=who,
            pages=same_kind[:3],
            verified_on=_verified_on(c),
            contact_id=str(c.id),
        )
    return fact("official_page", "not_declared", "Page non déclarée dans l'Annuaire.", subject)


def pages_in(text: str, url: str | None) -> list[str]:
    """The pages a check is about: the link read, then the links and bare pages of the text."""
    found: list[str] = []
    for candidate in [url or "", *LINK.findall(text or ""), *BARE_PAGE.findall(text or "")]:
        candidate = candidate.rstrip(".,;:!?)»")
        key = page_key(candidate)
        if key and key not in [page_key(f) for f in found]:
            found.append(candidate)
    return found[:3]


# --- « Numéro officiel ? » -------------------------------------------------------------------


def _numbers_of(c: Contact, country: str) -> list[str]:
    """A contact's numbers in E.164: its professional phone and WhatsApp, its official numbers."""
    out: list[str] = []
    raw = [c.phone, c.whatsapp]
    raw += [str(p.get("url")).removeprefix("tel:") for p in c.official_pages or []
            if p.get("kind") == "phone"]  # fmt: skip
    for value in raw:
        if value and (n := countries.phone(str(value), country)) and n not in out:
            out.append(n)
    return out


async def known_institutions(db: AsyncSession, ws: uuid.UUID, pool: list[Contact]) -> list[str]:
    """Institution names a message may cite: the registry's issuers (this newsroom's and those of
    the newsrooms that publish), the Annuaire's institutions and the list the registry keeps."""
    from app.modules.registry import INSTITUTIONS

    issuers = set(
        await db.scalars(
            select(Communique.issuer)
            .join(Workspace, Workspace.id == Communique.workspace_id)
            .where(or_(Communique.workspace_id == ws, Workspace.publishes))
            .distinct()
            .limit(300)
        )
    )
    annuaire = {
        _demo_free(n)
        for c in pool
        if c.kind in ("institution", "officer")
        for n in (c.institution, c.name if c.kind == "institution" else "")
        if n
    }
    return [n for n in {*issuers, *annuaire, *INSTITUTIONS} if n]


def cited_institutions(text: str, known: list[str]) -> list[str]:
    from app.modules.registry import quoted_issuers

    return quoted_issuers(text, known)


async def numbers(
    db: AsyncSession,
    ws: uuid.UUID,
    text: str,
    *,
    country: str = countries.DEFAULT,
    pool: list[Contact] | None = None,
    cited: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Each phone number of the text against the numbers declared in the Annuaire."""
    found = countries.phones_in(text, country)
    if not found:
        return []
    pool = pool if pool is not None else await contacts(db, ws)
    if cited is None:
        cited = cited_institutions(text, await known_institutions(db, ws, pool))
    owners: dict[str, list[Contact]] = defaultdict(list)
    for c in pool:
        for n in _numbers_of(c, country):
            owners[n].append(c)
    out = []
    for _raw, e164 in found[:4]:
        shown = countries.display(e164)
        if owners.get(e164):
            c = min(owners[e164], key=lambda x: (not x.verified_at, x.workspace_id != ws))
            who = label(c)
            state = (
                f"vérifié le {_verified_on(c)}"
                if c.verified_at
                else "déclaré, pas encore vérifié par la rédaction"
            )
            out.append(
                fact(
                    "number",
                    "declared",
                    f"Ce numéro est celui de {who} (Annuaire, {state}).",
                    shown,
                    institution=who,
                    verified_on=_verified_on(c),
                    contact_id=str(c.id),
                )
            )
            continue
        named = next(iter(cited), None)
        if not named:
            out.append(fact("number", "unknown", "Numéro absent de l'Annuaire.", shown))
            continue
        theirs = [c for c in pool if _same(label(c), named) and _numbers_of(c, country)]
        if not theirs:
            out.append(
                fact(
                    "number",
                    "unknown",
                    f"{named} n'a déclaré aucun numéro dans l'Annuaire : rien à comparer.",
                    shown,
                    institution=named,
                )
            )
            continue
        declared = list(dict.fromkeys(n for c in theirs for n in _numbers_of(c, country)))
        out.append(
            fact(
                "number",
                "not_declared",
                f"Ce numéro n'est pas un numéro déclaré de {named}.",
                shown,
                institution=named,
                declared=[countries.display(n) for n in declared[:4]],
            )
        )
    return out


# --- « Selon le ministère… » -----------------------------------------------------------------


def attributed(text: str, known: list[str]) -> list[str]:
    """Institutions the text speaks for: named in a sentence that presents a statement as theirs
    (« selon… », « … annonce », « communiqué de… », « araka ny… »)."""
    out: list[str] = []
    for sentence in SENTENCE.split(text or ""):
        if not CUES.search(sentence):
            continue
        for name in cited_institutions(sentence, known):
            if not any(_same(name, x) for x in out):
                out.append(name)
    return out[:3]


async def attribution(
    db: AsyncSession,
    ws: uuid.UUID,
    text: str,
    *,
    known: list[str],
    match: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    names = attributed(text, known)
    if not names:
        return []
    from app.modules.registry import match_text

    if match is None:
        match = await match_text(db, ws, text, with_contacts=False)
    issuers = list(
        await db.scalars(
            select(Communique.issuer)
            .join(Workspace, Workspace.id == Communique.workspace_id)
            .where(
                Communique.status == "original",
                or_(Communique.workspace_id == ws, Workspace.publishes),
            )
            .limit(1000)
        )
    )
    out = []
    for name in names:
        held = sum(_same(name, i) for i in issuers)
        original = match.get("communique") or {}
        if match.get("status") in ("authentic", "modified") and _same(
            name, str(match.get("issuer") or "")
        ):
            number = f" N° {match['number']}" if match.get("number") else ""
            day = dates.parse(original.get("issued_on"))
            when = f" du {dates.fr(day)}" if day else ""
            same = match["status"] == "authentic"
            out.append(
                fact(
                    "attribution",
                    "found" if same else "modified",
                    f"Le communiqué{number}{when} de {name} au registre dit cela."
                    if same
                    else f"Le communiqué{number}{when} de {name} existe au registre, mais ne dit "
                    "pas exactement cela.",
                    name,
                    institution=name,
                    communique_id=str(original.get("id")) if original.get("id") else None,
                    number=match.get("number"),
                    issued_on=original.get("issued_on"),
                    sealed=bool(original.get("sealed")),
                    url=original.get("url"),
                )
            )
        elif held:
            out.append(
                fact(
                    "attribution",
                    "not_found",
                    f"Aucun communiqué de {name} au registre ne dit cela (le registre peut être "
                    "incomplet).",
                    name,
                    institution=name,
                    originals=held,
                )
            )
        else:
            out.append(
                fact(
                    "attribution",
                    "no_reference",
                    f"Le message parle au nom de {name} ; aucun communiqué de {name} au registre : "
                    "rien à comparer.",
                    name,
                    institution=name,
                )
            )
    return out


# --- « Faux article de presse ? » --------------------------------------------------------------


def _outlet_domains(c: Contact) -> set[str]:
    out = set()
    for page in _declared_pages(c, False):
        key = page_key(page)
        if key and key[0] == "site":
            out.add(key[1])
    return out


def _own_words(outlet: str) -> set[str]:
    return words(outlet).union(*map(words, _aliases(outlet)))


def _headline(text: str, outlet: str) -> str:
    """The line of the text that reads as a headline: the longest one with three words or more
    once the outlet's own name is set aside."""
    own = _own_words(outlet)
    best = ""
    for line in re.split(r"\n+|\s[—–|]\s", text or ""):
        line = line.strip(" -–—|:·")
        if len(words(line) - own) >= 3 and len(line) > len(best):
            best = line
    return best[:300]


async def press_article(
    db: AsyncSession,
    ws: uuid.UUID,
    text: str,
    url: str | None,
    *,
    pool: list[Contact] | None = None,
) -> list[dict[str, Any]]:
    """A headline attributed to an outlet of the Annuaire (kind `media`), against the items of
    that outlet's feed that Veille stores (`Item` type `press`)."""
    pool = pool if pool is not None else await contacts(db, ws)
    outlets = [c for c in pool if c.kind == "media"]
    if not outlets:
        return []
    key = page_key(url) if url else None
    out = []
    for c in outlets:
        name = _demo_free(c.name)
        domains = _outlet_domains(c)
        if key and key[0] == "site" and key[1] in domains:
            out.append(
                fact(
                    "press_article",
                    "published",
                    f"Article publié sur le site de {name}.",
                    show_page(url or ""),
                    outlet=name,
                    url=url,
                )
            )
            continue
        if not _mentions(text, name):
            continue
        rows = list(
            await db.scalars(
                select(Item)
                .where(Item.workspace_id == ws, Item.type == "press")
                .order_by(Item.created_at.desc())
                .limit(1000)
            )
        )
        feed = [
            i
            for i in rows
            if _same(str((i.data or {}).get("outlet") or ""), name)
            or (page_key(str((i.data or {}).get("link") or "")) or ("", ""))[1] in domains
        ]
        headline = _headline(text, name)
        asked = words(headline) - _own_words(name)
        best, score = None, 0.0
        for item in feed:
            title = words(item.title)
            shared = asked & title
            ratio = len(shared) / max(1, min(len(asked), len(title)))
            if len(shared) >= 3 and ratio >= 0.6 and ratio > score:
                best, score = item, ratio
        if best is not None:
            day = dates.parse((best.data or {}).get("published_at"))
            when = f" le {dates.fr(day)}" if day else ""
            out.append(
                fact(
                    "press_article",
                    "published",
                    f"Publié par {name}{when}.",
                    headline,
                    outlet=name,
                    url=(best.data or {}).get("link"),
                    title=best.title,
                    date=day.isoformat() if day else None,
                )
            )
        elif feed:
            first = min(
                (
                    d
                    for i in feed
                    if (d := dates.parse((i.data or {}).get("published_at") or i.created_at))
                ),
                default=None,
            )
            since = f" depuis le {dates.fr(first)}" if first else ""
            out.append(
                fact(
                    "press_article",
                    "not_found",
                    f"Titre introuvable dans le flux de {name}{since}.",
                    headline,
                    outlet=name,
                    items=len(feed),
                    since=first.isoformat() if first else None,
                )
            )
        else:
            out.append(
                fact(
                    "press_article",
                    "no_feed",
                    f"Aucun article de {name} en mémoire dans la Veille : rien à comparer.",
                    headline,
                    outlet=name,
                )
            )
    return out[:2]


# --- all of them ------------------------------------------------------------------------------


async def facts(
    db: AsyncSession,
    ws: uuid.UUID,
    text: str | None,
    url: str | None = None,
    *,
    registry: dict[str, Any] | None = None,
    title: str | None = None,
) -> list[dict[str, Any]]:
    """Attribution, official page, official number and press article for one message."""
    from app.modules.directory import country_code

    text = (text or "").strip()
    pool = await contacts(db, ws)
    known = await known_institutions(db, ws, pool)
    out: list[dict[str, Any]] = []
    if text:
        out += await attribution(db, ws, text, known=known, match=registry)
    for page in pages_in(text, url):
        found = await official_page(db, ws, page, title=title if page == url else None, pool=pool)
        # A website that is nobody's is no news; a social page always says what it is.
        if found["status"] == "not_a_page" or (
            found["status"] == "not_declared" and (page_key(page) or ("site",))[0] == "site"
        ):
            continue
        out.append(found)
    if text:
        country = await country_code(db, ws)
        cited = cited_institutions(text, known)
        out += await numbers(db, ws, text, country=country, pool=pool, cited=cited)
    if text or url:
        out += await press_article(db, ws, text, url, pool=pool)
    return out


# --- route ------------------------------------------------------------------------------------


class GesturesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, max_length=6000)
    url: str | None = Field(default=None, max_length=2000)


class GestureOut(BaseModel):
    kind: str  # attribution | official_page | number | press_article
    status: str
    text: str
    subject: str
    proof: dict[str, Any]


@router.post("/workspaces/{ws}/gestures")
async def check_gestures(body: GesturesIn, member: AnyMember, db: Db) -> list[GestureOut]:
    """Attribution, official page, number and press article for a message (no model)."""
    if not ((body.text or "").strip() or (body.url or "").strip()):
        raise ApiError(422, "empty", "A text or a link is needed")
    found = await facts(db, member.workspace_id, body.text, (body.url or "").strip() or None)
    return [GestureOut(**f) for f in found]
