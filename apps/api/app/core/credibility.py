"""« Fiabilité de la source »: what a site shows about itself, as signals, never a score.

Taken from NewsGuard's transparency checklist and Media Bias/Fact Check's site notes, kept to what
a machine can see honestly: a named author, a publication date, an about / contact / legal page,
a corrections policy, HTTPS, the domain's age (RDAP), and whether the site is a known
fact-checker, an official page the newsroom declared in its Annuaire, or a declared press outlet.

Each signal is `found`, `missing` (looked for, not found: « non trouvé », never « mauvais ») or
`unknown` (could not look). There is no total: a young domain or a missing contact page is a
reason to look closer, not a judgement. Political leaning is never inferred.
"""

import asyncio
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core import dates, websearch
from app.core.http import shared as shared_http

log = logging.getLogger("checky.credibility")

RDAP = "https://rdap.org/domain/{}"
RDAP_TIMEOUT = 5.0
CACHE_SECONDS, CACHE_MAX = 86_400.0, 500
YOUNG_DAYS = 180
_transport: httpx.AsyncBaseTransport | None = None  # tests swap in a mock
_rdap_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}

# Public second levels under which the registrable domain has three labels.
SECOND_LEVELS = {
    "com.mg", "org.mg", "gov.mg", "edu.mg", "co.uk", "org.uk", "gov.uk", "ac.uk", "com.au",
    "co.za", "com.br", "co.in", "com.ng", "co.ke", "com.fr", "gouv.fr", "co.jp",
}  # fmt: skip
PLATFORMS = (
    "facebook.com", "fb.watch", "tiktok.com", "x.com", "twitter.com", "youtube.com", "youtu.be",
    "instagram.com", "whatsapp.com", "t.me", "telegram.org",
)  # fmt: skip
# Display names of fact-checkers, for « Vérifié par AFP Factuel ». Others show their host.
FACT_CHECKER_NAMES = {
    "factuel.afp.com": "AFP Factuel",
    "factcheck.afp.com": "AFP Fact Check",
    "africacheck.org": "Africa Check",
    "observers.france24.com": "Les Observateurs de France 24",
    "lemonde.fr": "Les Décodeurs (Le Monde)",
    "francetvinfo.fr": "Vrai ou fake (franceinfo)",
    "liberation.fr": "CheckNews (Libération)",
    "rfi.fr": "Les dessous de l'infox (RFI)",
    "20minutes.fr": "Fake Off (20 Minutes)",
    "snopes.com": "Snopes",
    "politifact.com": "PolitiFact",
    "factcheck.org": "FactCheck.org",
    "fullfact.org": "Full Fact",
    "leadstories.com": "Lead Stories",
    "maldita.es": "Maldita",
    "newtral.es": "Newtral",
    "chequeado.com": "Chequeado",
    "aosfatos.org": "Aos Fatos",
    "correctiv.org": "Correctiv",
    "boomlive.in": "BOOM",
    "altnews.in": "Alt News",
    "dubawa.org": "Dubawa",
    "pesacheck.org": "PesaCheck",
    "reuters.com": "Reuters Fact Check",
    "apnews.com": "AP Fact Check",
}
# Outlets that declare themselves as press and that the desk meets often. A page's own
# NewsArticle / NewsMediaOrganization markup counts too; a newsroom's Annuaire can add others.
PRESS_HOSTS = {
    "lexpress.mg", "newsmada.com", "midi-madagasikara.mg", "madagascar-tribune.com", "2424.mg",
    "laverite.mg", "orange.mg", "rfi.fr", "afp.com", "lemonde.fr", "bbc.com", "france24.com",
    "jeuneafrique.com", "reuters.com", "apnews.com",
}  # fmt: skip
LINKS = {
    "about": r"a-propos|apropos|qui-sommes-nous|about|notre-equipe|redaction|mombamomba",
    "contact": r"contact|nous-contacter|mailto:",
    "legal": r"mentions-legales|mentions_legales|legal|imprint|impressum|cgu|conditions",
    "corrections": r"correction|rectificatif|erratum|errata|charte-deontolog|deontolog",
}
LINK_TEXT = {
    "about": r"à propos|qui sommes-nous|about us|la rédaction|mombamomba",
    "contact": r"contact|nous écrire",
    "legal": r"mentions légales|legal notice|conditions d'utilisation",
    "corrections": r"corrections|rectificatifs|charte|déontologie",
}


def host_of(url: str | None) -> str:
    try:
        return (urlsplit(url or "").hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def registrable(host: str) -> str:
    """news.example.co.uk -> example.co.uk; actu.lexpress.mg -> lexpress.mg."""
    labels = host.split(".")
    keep = 3 if ".".join(labels[-2:]) in SECOND_LEVELS else 2
    return ".".join(labels[-keep:])


def _matches(host: str, domains) -> str | None:
    return next((d for d in domains if host == d or host.endswith("." + d)), None)


def fact_checker_name(url: str) -> str | None:
    """The fact-checker's name when the URL is in its fact-checking section, else None."""
    if not websearch._fact_checker_url(url):
        return None
    host = host_of(url)
    return FACT_CHECKER_NAMES.get(_matches(host, FACT_CHECKER_NAMES) or "", host)


async def domain_age(domain: str) -> dict[str, Any] | None:
    """{registered: ISO day, days} from RDAP, cached a day in memory; None when unknown."""
    if not re.fullmatch(r"[a-z0-9.-]{3,253}", domain or ""):
        return None
    now = time.monotonic()
    if (hit := _rdap_cache.get(domain)) and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    found: dict[str, Any] | None = None
    try:
        async with asyncio.timeout(RDAP_TIMEOUT):
            r = await shared_http("rdap", _transport, RDAP_TIMEOUT).get(
                RDAP.format(domain),
                headers={"Accept": "application/rdap+json"},
                follow_redirects=True,
            )
        if r.status_code == 200:
            for event in r.json().get("events") or []:
                if event.get("eventAction") == "registration":
                    day = dates.parse(event.get("eventDate"))
                    if day:
                        found = {"registered": day.isoformat(), "days": (dates.today() - day).days}
                    break
    except (httpx.HTTPError, TimeoutError, ValueError, AttributeError) as exc:
        log.info("rdap %s: %s", domain, type(exc).__name__)
        return None  # a failure is not cached: the next check may get an answer
    if len(_rdap_cache) >= CACHE_MAX:
        _rdap_cache.pop(next(iter(_rdap_cache)))
    _rdap_cache[domain] = (now, found)
    return found


def _links(html: str) -> list[tuple[str, str]]:
    return [
        (href.lower(), re.sub(r"<[^>]+>|\s+", " ", label).strip().lower())
        for href, label in re.findall(
            r"<a\b[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
            html[:600_000],
            re.IGNORECASE | re.DOTALL,
        )
    ]


def _author(page: dict[str, Any], html: str) -> str | None:
    if page.get("author"):
        return str(page["author"])[:120]
    m = re.search(
        r"<meta[^>]+name\s*=\s*[\"']author[\"'][^>]+content\s*=\s*[\"']([^\"']{2,120})",
        html[:300_000],
        re.IGNORECASE,
    ) or re.search(r'"author"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]{2,120})"', html[:500_000])
    if m:
        return m.group(1).strip()
    if re.search(r"rel\s*=\s*[\"']author|itemprop\s*=\s*[\"']author|class\s*=\s*[\"'][^\"']*byline", html[:500_000], re.IGNORECASE):  # fmt: skip
        return ""
    return None


def _published(page: dict[str, Any], html: str) -> str | None:
    if day := dates.parse(page.get("published_at")):
        return day.isoformat()
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html[:500_000]) or re.search(
        r"<time[^>]+datetime\s*=\s*[\"']([^\"']+)", html[:500_000], re.IGNORECASE
    )
    day = dates.parse(m.group(1)) if m else None
    return day.isoformat() if day else None


def _declares_press(html: str) -> bool:
    return bool(
        re.search(
            r'"@type"\s*:\s*"(?:NewsArticle|NewsMediaOrganization|ReportageNewsArticle|AnalysisNewsArticle)"',
            html[:500_000],
        )
    )


def _signal(key: str, status: str, detail: str = "") -> dict[str, str]:
    return {"key": key, "status": status, "detail": detail}


async def rate(
    url: str,
    page: dict[str, Any] | None = None,
    text: str = "",
    *,
    html: str | None = None,
    official_hosts: set[str] | None = None,
    fetch: bool = True,
) -> dict[str, Any]:
    """{domain, url, platform, known: fact_checker|official|press|None, name, signals: [...]}.

    `page` is what `linkcheck.read_link` returned (author, published_at…); `html` the raw page
    when the caller already has it, otherwise it is fetched once (SSRF-guarded) unless `fetch` is
    False. Nothing here is a verdict on the content."""
    from app.workers import ingest

    page = page or {}
    host = host_of(page.get("final_url") or url)
    domain = registrable(host) if host else ""
    scheme = urlsplit(page.get("final_url") or url or "").scheme
    out: dict[str, Any] = {"domain": domain, "host": host, "url": url, "platform": None}
    if not host:
        return {**out, "known": None, "name": None, "signals": []}
    if platform := _matches(host, PLATFORMS):
        # The page is a post: what counts is the account that published it, not the platform.
        return {
            **out,
            "platform": platform,
            "known": None,
            "name": None,
            "signals": [
                _signal("https", "found" if scheme == "https" else "missing"),
                _signal(
                    "author",
                    "found" if page.get("author") else "unknown",
                    str(page.get("author") or ""),
                ),
            ],
        }
    if html is None and fetch and page.get("kind", "page") == "page":
        try:
            async with asyncio.timeout(8):
                _, kind, body, encoding = await ingest.fetch_raw(url)
            html = body.decode(encoding or "utf-8", errors="replace") if "html" in kind else ""
        except Exception as exc:  # noqa: BLE001 - an unreadable page leaves its signals unknown
            log.info("credibility fetch failed: %s", type(exc).__name__)
            html = None
    looked = html is not None
    html = html or ""
    signals: list[dict[str, str]] = []

    author = _author(page, html)
    signals.append(
        _signal(
            "author",
            "found" if author is not None else "missing" if looked else "unknown",
            author or "",
        )
    )
    published = _published(page, html)
    signals.append(
        _signal(
            "date",
            "found" if published else "missing" if looked else "unknown",
            dates.fr(dates.parse(published)) if published else "",
        )
    )
    links = _links(html)
    for key in ("about", "contact", "legal", "corrections"):
        hit = any(
            re.search(LINKS[key], href) or re.search(LINK_TEXT[key], label) for href, label in links
        )
        signals.append(_signal(key, "found" if hit else "missing" if looked else "unknown"))
    signals.append(_signal("https", "found" if scheme == "https" else "missing"))

    age = await domain_age(domain)
    if age:
        when = dates.fr(dates.parse(age["registered"]))
        signals.append(
            _signal(
                "domain_age",
                "found",
                f"Domaine enregistré le {when} ({dates.span(age['days'])})"
                + (" : domaine récent" if age["days"] < YOUNG_DAYS else ""),
            )
            | {"days": age["days"]}
        )
    else:
        signals.append(_signal("domain_age", "unknown"))

    checker = fact_checker_name(page.get("final_url") or url)
    official = _matches(host, {h.lower().removeprefix("www.") for h in official_hosts or set()})
    press = _matches(host, PRESS_HOSTS) or (_declares_press(html) and host)
    signals.append(_signal("fact_checker", "found" if checker else "missing", checker or ""))
    signals.append(
        _signal(
            "official",
            "found" if official else "missing",
            "Page officielle déclarée dans l'Annuaire" if official else "",
        )
    )
    signals.append(_signal("press", "found" if press else "missing", page.get("site") or ""))
    known = "fact_checker" if checker else "official" if official else "press" if press else None
    return {
        **out,
        "known": known,
        "name": checker or page.get("site") or domain,
        "signals": signals,
        "checked_at": datetime.now(UTC).isoformat(),
    }
