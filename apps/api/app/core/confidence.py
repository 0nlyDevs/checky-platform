"""How solid a reading is, computed from its evidence. Never the model's own confidence.

`compute(evidence, sources, first_seen, attached_ids)` returns a score from 0 to 100, a level
(élevé, moyen, faible), the reasons in plain French, what is missing, and the breakdown shown under
« Comment c'est calculé ». It measures how well the reading is backed, not the probability that
a claim is true: a perfect score on a false rumour means the evidence against it is strong.

Six components, 100 points (taken from The Factual's source-diversity grading, adapted to a
newsroom that holds its own registry, figures and archives):

- agreement (30): do the backing sources point the same way, and are there enough of them;
- official (25): the most official backing source (registry original, an official site or one
  declared in the Annuaire, an official figure, a known fact-checker…);
- dates (15): backing sources dated, and not older than `dates.STALE_DAYS` before the rumour;
- outside (10): at least one backing source from outside the newsroom (web, fact-checker, another
  newsroom's signed verdict);
- attached (10): backing sources the newsroom joined or keeps itself (dossier, registry, figures,
  archives);
- hosts (10): distinct origins (different sites can still repeat one dispatch).

The Contradicteur's quoted concerns each take 5 points off (15 at most). Pure function.
"""

from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

from app.core import dates

VERSION = "confidence-v1"
MAXIMA = {"agreement": 30, "official": 25, "dates": 15, "outside": 10, "attached": 10, "hosts": 10}
CONCERN_PENALTY, CONCERN_MAX = 5, 15
HIGH, MEDIUM = 70, 40

# Hosts official by their suffix, anywhere (a newsroom's Annuaire adds its own).
OFFICIAL_SUFFIXES = (".gov.mg", ".gouv.mg", ".gov", ".gouv.fr", ".gov.uk", ".gob.es", ".int")
OFFICIAL_HOSTS = {"instat.mg", "banque-centrale.mg", "presidence.gov.mg", "who.int", "un.org"}
# What each kind of source is worth as authority, and how it is named in the reasons.
AUTHORITY = {
    "registry": (25, "le communiqué original déposé au registre"),
    "official": (25, "un site officiel"),
    "figure": (20, "un chiffre officiel sourcé"),
    "fact_checker": (20, "un fact-checkeur reconnu"),
    "newsroom": (15, "le verdict signé d'une rédaction"),
    "archive": (10, "les archives de la rédaction"),
    "press": (8, "un média"),
    "web": (5, "une page web"),
}
OUTSIDE_KINDS = {"web", "fact-check", "wikipedia", "published", "recheck"}


def _host(url: str | None) -> str | None:
    try:
        host = (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return None
    return host.removeprefix("www.") or None


def is_official(url: str | None, official_hosts: set[str] | None = None) -> bool:
    host = _host(url)
    if not host:
        return False
    declared = {h.lower().removeprefix("www.") for h in (official_hosts or set())}
    return (
        host in declared
        or any(host.endswith("." + h) for h in declared)
        or host in OFFICIAL_HOSTS
        or host.endswith(OFFICIAL_SUFFIXES)
    )


def authority(source: dict[str, Any], official_hosts: set[str] | None = None) -> str:
    """The kind of authority a source carries (a key of AUTHORITY)."""
    from app.core.websearch import _fact_checker_url

    kind = source.get("kind") or "web"
    if kind == "registry":
        return "registry"
    if is_official(source.get("url"), official_hosts) or source.get("official"):
        return "official"
    if kind == "figure":
        return "figure"
    if kind == "fact-check" or _fact_checker_url(source.get("url") or ""):
        return "fact_checker"
    if kind == "published":
        return "newsroom"
    if kind == "archive":
        return "archive"
    if source.get("press"):
        return "press"
    return "web"


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return dates.parse_moment(value).date()
    return dates.parse(value)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def compute(
    evidence: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    first_seen: Any = None,
    attached_ids: Any = None,
    *,
    official_hosts: set[str] | None = None,
    concerns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """`evidence`: [{n (or result), stance: supports|contradicts|context}] citing `sources`
    [{n, kind, url, date, title}]; `first_seen`: when the rumour surfaced (today if unknown);
    `attached_ids`: the `n` of sources joined to the dossier or kept by the newsroom."""
    by_n = {s.get("n"): s for s in sources}
    attached = set(attached_ids or ())
    rumour = _day(first_seen) or dates.today()

    # One stance per source: a source that both supports and contradicts only nuances.
    stances: dict[Any, set[str]] = {}
    for e in evidence:
        ref = e.get("n", e.get("result"))
        if ref in by_n and e.get("stance") in ("supports", "contradicts", "context"):
            stances.setdefault(ref, set()).add(e["stance"])
    backing = {
        ref: next(iter(s - {"context"})) for ref, s in stances.items() if len(s - {"context"}) == 1
    }
    sup = sum(stance == "supports" for stance in backing.values())
    con = len(backing) - sup
    total = len(backing)
    reasons: list[str] = []
    missing: list[str] = []
    components: list[dict[str, Any]] = []

    def add(key: str, points: float, detail: str) -> None:
        components.append(
            {
                "key": key,
                "points": round(points),
                "maximum": MAXIMA.get(key, 0),
                "detail": detail,
            }
        )

    # agreement
    if total:
        ratio = max(sup, con) / total
        volume = min(1.0, (total + 1) / 4)
        direction = "mixed" if sup and con else "supports" if sup else "contradicts"
        detail = f"{_plural(con, 'source contredit', 'sources contredisent')}, {_plural(sup, 'confirme', 'confirment')}"
        add("agreement", MAXIMA["agreement"] * ratio * volume, detail)
        if direction == "mixed":
            missing.append("Les sources se contredisent : à départager.")
        else:
            against = direction == "contradicts"
            reasons.append(
                f"{total} sources {'contredisent' if against else 'confirment'} l'affirmation, "
                "aucune ne dit l'inverse."
                if total > 1
                else f"Une source {'contredit' if against else 'confirme'} l'affirmation."
            )
        if total < 3:
            missing.append(
                "Peu de sources tranchent : une confirmation de plus renforcerait la lecture."
            )
    else:
        direction = "none"
        add("agreement", 0, "Aucune source ne confirme ni ne contredit directement")
        missing.append("Aucun passage ne confirme ni ne contredit directement l'affirmation.")

    # official
    kinds = {ref: authority(by_n[ref], official_hosts) for ref in backing}
    if kinds:
        best = max(kinds.values(), key=lambda k: AUTHORITY[k][0])
        points, label = AUTHORITY[best]
        add("official", points, f"Source la plus officielle : {label}")
        if points >= 20:
            reasons.append(f"Appuyée sur {label}.")
        else:
            missing.append(
                "Aucune source officielle : le communiqué, le chiffre ou l'institution concernée."
            )
    else:
        add("official", 0, "Aucune source qui tranche")

    # dates
    if total:
        dated = timely = 0.0
        stale_support = 0
        for ref, stance in backing.items():
            day = _day(by_n[ref].get("date"))
            if not day:
                continue
            dated += 1
            if (rumour - day).days <= dates.STALE_DAYS:
                timely += 1
            elif stance == "contradicts":
                timely += 0.5  # an old source can still show the content is old
            else:
                stale_support += 1
        points = MAXIMA["dates"] * (dated / total + timely / total) / 2
        add(
            "dates",
            points,
            f"{int(dated)} sur {total} datées, {_plural(stale_support, 'confirmation ancienne', 'confirmations anciennes')}",
        )
        if dated == total:
            reasons.append("Toutes les sources qui tranchent sont datées.")
        else:
            missing.append(
                f"{_plural(total - int(dated), 'source sans date', 'sources sans date')} : à dater."
            )
        if stale_support:
            missing.append(
                f"Une confirmation de plus de {dates.STALE_DAYS} jours avant la rumeur ne prouve pas un fait récent."
            )
    else:
        add("dates", 0, "Rien à dater")

    # outside
    outside = [ref for ref in backing if (by_n[ref].get("kind") or "web") in OUTSIDE_KINDS]
    add(
        "outside",
        MAXIMA["outside"] if outside else 0,
        _plural(
            len(outside), "source extérieure à la rédaction", "sources extérieures à la rédaction"
        ),
    )
    if total and not outside:
        missing.append(
            "Aucune source extérieure à la rédaction (fact-checkeur, presse, site officiel en ligne)."
        )

    # attached
    joined = [ref for ref in backing if ref in attached]
    add(
        "attached",
        MAXIMA["attached"] * len(joined) / total if total else 0,
        f"{len(joined)} sur {total} jointes au dossier ou tenues par la rédaction",
    )

    # hosts
    origins = {_host(by_n[ref].get("url")) or by_n[ref].get("kind") or "?" for ref in backing}
    add(
        "hosts",
        {0: 0, 1: 4, 2: 7}.get(len(origins), 10),
        f"{_plural(len(origins), 'origine distincte', 'origines distinctes')} (des sites différents peuvent reprendre une même dépêche)",
    )
    if len(origins) >= 2:
        reasons.append(f"{len(origins)} origines distinctes.")

    # the Contradicteur's quoted concerns
    raised = [c for c in concerns or [] if c.get("quote")]
    if raised:
        penalty = min(CONCERN_MAX, CONCERN_PENALTY * len(raised))
        add(
            "critique",
            -penalty,
            _plural(len(raised), "limite citée", "limites citées") + " par le Contradicteur",
        )
        missing.extend(f"Le Contradicteur relève : {c['why']}" for c in raised if c.get("why"))

    score = max(0, min(100, sum(c["points"] for c in components)))
    return {
        "version": VERSION,
        "meaning": "evidence_strength_not_truth_probability",
        "score": score,
        "level": "eleve" if score >= HIGH else "moyen" if score >= MEDIUM else "faible",
        "direction": direction,
        "reasons": reasons[:5],
        "missing": missing[:5],
        "components": components,
        "computed_at": dates.now().isoformat(),
    }
