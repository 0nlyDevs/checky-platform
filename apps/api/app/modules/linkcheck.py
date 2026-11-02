"""« Analyser un lien »: paste a post, an article or an image link and get, in one pass, what it
claims, the warning signs in it, what fact-checkers and the web already say, and a suggested
verdict with its evidence. The AI suggests; a journalist confirms on the claim, as everywhere.
Dates come from code, not the model: both calls get today's date and the content's publication
date, and the result carries `days_old` so an old post that circulates again is flagged.

`POST /workspaces/{ws}/link-check {url?, text?}` SSE: `step` ({key, status, summary}) for read →
claims → search → verdict, then `result`, then `done`, or `error`. Two model calls in all.
Every quote (warning sign or evidence) must be found in the text it cites, otherwise it is
dropped; with no backed evidence the verdict is `unverifiable`. Nothing is written: "Suivre dans
le desk" in the UI creates the claim and attaches the chosen sources through the copilot route.
"""

import json
import re
import unicodedata
from collections import defaultdict, deque
from collections.abc import AsyncIterable
from typing import Any
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select

from app.core import ai, dates, websearch
from app.core.access import AnyMember
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Item, Source
from app.modules.public import _allow
from app.workers import ingest

router = APIRouter(tags=["link-check"])

TEXT_CHARS = 6000  # of the page sent to the model
_CHECKS: dict[str, deque[float]] = defaultdict(deque)
CHECK_LIMIT, CHECK_WINDOW = 30, 600.0
VERDICTS = ("true", "misleading", "false", "unverifiable")
PLATFORMS = {
    "facebook.com": "facebook",
    "fb.watch": "facebook",
    "whatsapp.com": "whatsapp",
    "tiktok.com": "tiktok",
    "x.com": "x",
    "twitter.com": "x",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "instagram.com": "instagram",
}
SIGNALS = (
    "urgence",
    "sans_source",
    "chiffre_invérifiable",
    "ton_alarmiste",
    "date",
    "émotion",
    "incohérence",
    "titre_trompeur",
)

READ_SYSTEM = """Tu aides une rédaction de Madagascar à vérifier un contenu (publication, article, \
message). Lis-le et réponds en JSON :
{"summary": "ce que dit le contenu, une phrase neutre",
 "claims": ["affirmations factuelles vérifiables, une phrase courte chacune, au plus 3, la plus \
importante d'abord"],
 "signals": [{"type": "urgence|sans_source|chiffre_invérifiable|ton_alarmiste|date|émotion|\
incohérence|titre_trompeur", "quote": "extrait EXACT du contenu", "why": "pourquoi c'est un signe \
d'alerte, une phrase"}],
 "search": "requête de recherche courte pour retrouver ce sujet (mots-clés, lieux, noms)"}
Les signes d'alerte sont des indices de rédaction, pas une preuve. N'invente rien : chaque extrait \
doit être copié tel quel. Écris en français."""

VERDICT_SYSTEM = """Tu proposes un verdict sur une affirmation, pour une rédaction de Madagascar, \
uniquement à partir des résultats de recherche numérotés fournis. Réponds en JSON :
{"verdict": "true|misleading|false|unverifiable",
 "reason": "deux ou trois phrases : ce que montrent les résultats",
 "evidence": [{"result": n, "stance": "supports|contradicts|context", "quote": "extrait EXACT du \
résultat n"}],
 "missing": "ce qu'il faudrait encore vérifier, une phrase"}
Un article de fact-checkeur qui traite déjà cette affirmation compte beaucoup. Si les résultats ne \
permettent pas de conclure, réponds unverifiable. N'invente aucun fait ni extrait. Écris en français.
Les dates fournies (aujourd'hui, publication du contenu, date des résultats) sont exactes : ne les \
devine pas. Un résultat ancien ne prouve pas un fait récent ; un contenu ancien qui recircule \
présenté comme récent est trompeur ou faux."""


class LinkIn(BaseModel):
    url: str | None = Field(default=None, max_length=2000)
    # The post's text, pasted, when the link cannot be read without an account (Facebook…).
    text: str | None = Field(default=None, max_length=6000)

    @model_validator(mode="after")
    def something(self):
        if not (self.url or "").strip() and not (self.text or "").strip():
            raise ValueError("a link or a text is needed")
        return self


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("’", "'").replace("«", '"').replace("»", '"')
    return re.sub(r"\s+", " ", s).strip()


def _json(content: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", content or "", re.DOTALL)
    if not m:
        raise ValueError("The model did not return JSON")
    return json.loads(m.group(0))


def _platform(url: str) -> str | None:
    host = urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")
    return next((p for d, p in PLATFORMS.items() if host == d or host.endswith("." + d)), None)


def _step(key: str, status: str, summary: str = "") -> ServerSentEvent:
    return ServerSentEvent(data={"key": key, "status": status, "summary": summary}, event="step")


def reverse_search(image_url: str) -> list[dict[str, str]]:
    q = quote(image_url, safe="")
    return [
        {"name": "Google Lens", "url": f"https://lens.google.com/uploadbyurl?url={q}"},
        {"name": "TinEye", "url": f"https://tineye.com/search?url={q}"},
        {"name": "Yandex", "url": f"https://yandex.com/images/search?rpt=imageview&url={q}"},
    ]


# Public oEmbed endpoints (no key) give a video's or post's caption and author, which the pages
# themselves only render with JavaScript.
OEMBED = {
    "tiktok": "https://www.tiktok.com/oembed?url={}",
    "youtube": "https://www.youtube.com/oembed?format=json&url={}",
    "x": "https://publish.twitter.com/oembed?omit_script=true&url={}",
}


async def _oembed(url: str, platform: str) -> dict[str, Any] | None:
    try:
        _, _, body, _ = await ingest.fetch_raw(OEMBED[platform].format(quote(url, safe="")))
        data = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return None
    caption = data.get("title") or ""
    if platform == "x" and data.get("html"):
        caption = re.sub(r"<[^>]+>", " ", data["html"].split("&mdash;")[0])
    caption = re.sub(r"\s+", " ", ingest.html_unescape(caption)).strip()
    if not caption:
        return None
    return {
        "kind": "post",
        "final_url": url,
        "title": caption[:200],
        "site": data.get("provider_name"),
        "author": data.get("author_name"),
        "image_url": data.get("thumbnail_url"),
        "text": caption,
    }


async def read_link(url: str) -> dict[str, Any]:
    """What the link holds: an image (with its AI traces), a post's caption, or a page's text."""
    if (platform := _platform(url)) in OEMBED and (post := await _oembed(url, platform)):
        return post
    final, kind, body, encoding = await ingest.fetch_raw(url)
    if kind.startswith("image/"):
        meta = ingest.image_meta(body)
        return {"kind": "image", "final_url": final, "title": "", "text": "", "image": meta}
    html = body.decode(encoding or "utf-8", errors="replace")
    page = ingest.extract_page(html, final)
    og = ingest.page_meta(html)
    text = page["text"] or og.get("og:description") or og.get("description") or ""
    return {
        "kind": "page",
        "final_url": final,
        "title": page["title"] or og.get("og:title", ""),
        "site": og.get("og:site_name"),
        "published_at": page["published_at"],
        "author": page["author"],
        "image_url": og.get("og:image"),
        "text": text,
    }


async def _tracked(ws, url: str | None, claim: str | None) -> dict[str, Any] | None:
    """A claim the newsroom already follows with this link, or with the same wording."""
    async with SessionLocal() as db:
        if url:
            hit = await db.scalar(
                select(Item)
                .join(Source, Source.item_id == Item.id, isouter=True)
                .where(
                    Item.workspace_id == ws,
                    or_(Source.url == url, Item.data["tip_url"].astext == url),
                )
                .limit(1)
            )
            if hit:
                return {"item_id": str(hit.id), "ref": hit.data.get("ref"), "title": hit.title}
        if claim:
            hit = await db.scalar(
                select(Item).where(Item.workspace_id == ws, Item.title.ilike(claim.strip()[:300]))
            )
            if hit:
                return {"item_id": str(hit.id), "ref": hit.data.get("ref"), "title": hit.title}
    return None


async def _search(query: str, skip: str | None) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for kind, fn, q in (
        ("fact-check", websearch.fact_checks, query),
        ("web", websearch.web, websearch.localised(query)),
    ):
        try:
            for r in await fn(q):
                found.append({**r, "kind": kind})
        except websearch.SearchUnavailable:
            continue
    try:
        found += [{**r, "kind": "wikipedia"} for r in await websearch.wikipedia(query, "fr", 2)]
    except websearch.SearchUnavailable:
        pass
    seen, out = {skip} if skip else set(), []
    for r in found:
        if r["url"] not in seen:
            seen.add(r["url"])
            out.append(r)
    return [{**r, "n": i} for i, r in enumerate(out[:10], 1)]


def clean_signals(raw: list[Any], text: str) -> list[dict[str, str]]:
    body, out = _norm(text), []
    for s in raw or []:
        q = str((s or {}).get("quote") or "").strip().strip('«»"').strip()
        kind = str((s or {}).get("type") or "")
        if q and kind in SIGNALS and _norm(q) in body:
            out.append({"type": kind, "quote": q[:300], "why": str(s.get("why") or "")[:300]})
    return out[:6]


def clean_verdict(raw: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    texts = {r["n"]: _norm(f"{r['title']} {r['snippet']}") for r in results}
    evidence, dropped = [], 0
    for e in raw.get("evidence") or []:
        try:
            n = int(e.get("result"))
        except (TypeError, ValueError):
            dropped += 1
            continue
        q = str(e.get("quote") or "").strip().strip('«»"').strip()
        stance = (
            e.get("stance")
            if e.get("stance") in ("supports", "contradicts", "context")
            else "context"
        )
        if n not in texts or not q or _norm(q) not in texts[n]:
            dropped += 1
            continue
        evidence.append({"result": n, "stance": stance, "quote": q[:400]})
    verdict = raw.get("verdict") if raw.get("verdict") in VERDICTS else "unverifiable"
    if not any(e["stance"] != "context" for e in evidence):
        verdict = "unverifiable"  # nothing found backs a conclusion
    return {
        "verdict": verdict,
        "reason": str(raw.get("reason") or "")[:1200],
        "evidence": evidence,
        "missing": str(raw.get("missing") or "")[:400],
        "dropped": dropped,
    }


def _limited(request: Request) -> None:
    addr = request.client.host if request.client else "unknown"
    if not _allow(_CHECKS, addr, CHECK_LIMIT, CHECK_WINDOW):
        raise ApiError(429, "too_many_checks", "Too many analyses, try again in a few minutes")


@router.post(
    "/workspaces/{ws}/link-check",
    response_class=EventSourceResponse,
    dependencies=[Depends(_limited)],
)
async def link_check(body: LinkIn, member: AnyMember) -> AsyncIterable[ServerSentEvent]:
    url = (body.url or "").strip() or None
    pasted = (body.text or "").strip()
    out: dict[str, Any] = {"url": url, "platform": _platform(url) if url else None}
    try:
        # 1. read
        yield _step("read", "running")
        note = None
        page: dict[str, Any] = {"kind": "text", "text": ""}
        if url:
            try:
                page = await read_link(url)
            except ValueError as e:
                note = str(e)
        text = "\n\n".join(p for p in [page.get("text", ""), pasted] if p).strip()
        out.update({k: v for k, v in page.items() if k != "text"})
        out["excerpt"] = text[:600]
        published = dates.parse(page.get("published_at"))
        out["published_at"] = published.isoformat() if published else None
        out["days_old"] = max(0, (dates.today() - published).days) if published else None
        when = (
            f"Contenu publié le {dates.fr(published)}, il y a {dates.span(out['days_old'])}."
            if published and out["days_old"]
            else f"Contenu publié aujourd'hui, le {dates.fr(published)}."
            if published
            else "Date de publication du contenu inconnue."
        )
        # In the instructions, not beside the content, so the model does not read it as the post's.
        dated = (
            f"\n\nDates, calculées par FANILO (elles ne font pas partie du contenu) : "
            f"{dates.today_line()} {when}"
        )
        if page.get("kind") == "image":
            out["reverse_search"] = reverse_search(page["final_url"])
        elif page.get("image_url"):
            out["reverse_search"] = reverse_search(page["image_url"])
        if not text and page.get("kind") != "image":
            out["read_error"] = note or "empty"
            yield _step("read", "failed", note or "aucun texte")
            yield ServerSentEvent(data={**out, "needs_text": True}, event="result")
            yield ServerSentEvent(data={"steps": 1}, event="done")
            return
        summary = page.get("title") or (text[:80] + "…" if len(text) > 80 else text) or "image"
        yield _step("read", "done", summary)

        # 2. claims and warning signs
        claims: list[str] = []
        if text:
            yield _step("claims", "running")
            reply = await ai.complete(
                [
                    {"role": "system", "content": READ_SYSTEM + dated},
                    {
                        "role": "user",
                        "content": f"Titre : {page.get('title') or '—'}\n\n{text[:TEXT_CHARS]}",
                    },
                ],
                workspace_id=member.workspace_id,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            read = _json(reply.content)
            claims = [str(c).strip()[:300] for c in read.get("claims") or [] if str(c).strip()][:3]
            out["summary"] = str(read.get("summary") or "")[:500]
            out["claims"] = claims
            out["signals"] = clean_signals(read.get("signals"), text)
            query = str(read.get("search") or (claims[0] if claims else ""))[:200]
            yield _step(
                "claims",
                "done",
                f"{len(claims)} affirmations, {len(out['signals'])} signes d'alerte",
            )
        else:
            query = ""
            out.update({"claims": [], "signals": [], "summary": ""})
        out["tracked"] = await _tracked(member.workspace_id, url, claims[0] if claims else None)

        # 3. what the web and fact-checkers already say
        results: list[dict[str, Any]] = []
        if query:
            yield _step("search", "running", query)
            results = await _search(query, url)
            n_fc = sum(r["kind"] == "fact-check" for r in results)
            yield _step(
                "search", "done", f"{len(results)} résultats, dont {n_fc} de fact-checkeurs"
            )
        out["results"] = results

        # 4. a suggested verdict on the main claim, from those results only
        if claims and results:
            yield _step("verdict", "running")
            listing = "\n\n".join(
                f"[{r['n']}] ({r['kind']}{', ' + dates.published_line(r['date']) if r.get('date') else ''})"
                f" {r['title']}\n{r['url']}\n{r['snippet'][:700]}"
                for r in results
            )
            reply = await ai.complete(
                [
                    {"role": "system", "content": VERDICT_SYSTEM + dated},
                    {
                        "role": "user",
                        "content": f"Affirmation : {claims[0]}\n\nSource du contenu : "
                        f"{out.get('site') or out.get('platform') or url or 'texte collé'}"
                        f"\n\nRésultats :\n\n{listing}",
                    },
                ],
                workspace_id=member.workspace_id,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            out["analysis"] = {**clean_verdict(_json(reply.content), results), "model": reply.model}
            yield _step("verdict", "done", out["analysis"]["verdict"])
        yield ServerSentEvent(data=out, event="result")
        yield ServerSentEvent(data={"steps": 4}, event="done")
    except ai.AiUnavailable as e:
        yield ServerSentEvent(
            data={"code": "ai_unavailable", "message": str(e)[:300]}, event="error"
        )
    except Exception as e:  # noqa: BLE001 - never end the stream without telling the client
        yield ServerSentEvent(
            data={"code": "link_check_failed", "message": type(e).__name__}, event="error"
        )
