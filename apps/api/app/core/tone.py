"""How a message is written, read in code so it works without a model (« Mode sans IA »).

Two readings, both lexicon-based (French, Malagasy, English), both returning verbatim quotes:

- `analyse(text)` — the **tone**: shouting capitals, piled-up exclamation marks, urgency
  (« URGENT », « maika », « breaking »), appeals to share (« partagez », « zarao »), emotive
  words, alarm emoji and the classic « ils ne veulent pas que vous sachiez ». Taken from The
  Factual / BiasBreak, which grade a text's wording apart from its truth: a sensational tone is a
  reason to look closer, never a verdict.
- `risk(text)` — the **danger** if the rumour keeps circulating: an accusation against a person,
  panic (disaster, epidemic, shortage, power cut), a fake official order or communiqué, a call to
  violence. The model may suggest more (the Lecteur); the journalist adjusts.

Every quote is a slice of the original text, so it is found verbatim by construction. The
Malagasy words are a first list, to be reviewed by a native speaker.
"""

import re
import unicodedata
from typing import Any

# Shouting is measured on words of 4+ letters written in capitals; acronyms are not shouting.
ACRONYM_MAX = 6
CAPS_RATIO = 0.3  # share of letters in shouted words, past which the whole text shouts

URGENCY = (
    "urgent",
    "urgence",
    "alerte",
    "dernière minute",
    "derniere minute",
    "flash info",
    "immédiatement",
    "tout de suite",
    "avant qu'il ne soit trop tard",
    "maika",
    "vaovao mafana",
    "tandremo",
    "breaking",
    "breaking news",
    "act now",
)
SHARE = (
    "partagez",
    "partager",
    "faites tourner",
    "faites passer",
    "transférez",
    "transferez",
    "diffusez",
    "à tous vos contacts",
    "a tous vos contacts",
    "zarao",
    "zarazarao",
    "ampitao",
    "share",
    "forward",
    "pass it on",
)
EMOTIVE = (
    "choquant",
    "scandale",
    "scandaleux",
    "honte",
    "terrifiant",
    "horrible",
    "incroyable",
    "effrayant",
    "catastrophe",
    "catastrophique",
    "hallucinant",
    "inadmissible",
    "mampatahotra",
    "mahatsiravina",
    "henatra",
    "shocking",
    "outrageous",
    "terrifying",
    "unbelievable",
)
HIDDEN = (
    "ils ne veulent pas que vous sachiez",
    "on vous cache",
    "on nous cache",
    "les médias ne disent pas",
    "les medias ne disent pas",
    "la vérité cachée",
    "avant que ce soit supprimé",
    "avant suppression",
    "censuré",
    "they don't want you to know",
    "they do not want you to know",
    "before it gets deleted",
    "miafina aminareo",
)
ALARM_EMOJI = ("⚠️", "⚠", "🚨", "‼️", "‼", "❗", "🔴", "📢", "🆘")

# Danger lexicon (`risk`). A shortage or a power cut sets off queues and hoarding; an official
# order or communiqué is the most copied form of fake; a call to violence is the gravest.
PANIC = (
    "épidémie",
    "epidemie",
    "peste",
    "choléra",
    "cholera",
    "variole",
    "mpox",
    "cyclone",
    "inondation",
    "séisme",
    "tsunami",
    "pénurie",
    "penurie",
    "rupture de stock",
    "délestage",
    "delestage",
    "coupure de courant",
    "coupures de courant",
    "enlèvement",
    "enlevement",
    "kidnapping",
    "explosion",
    "aretina",
    "areti-mandoza",
    "tsy misy jiro",
    "outbreak",
    "shortage",
    "blackout",
)
ORDER = (
    "communiqué",
    "communique",
    "décret",
    "decret",
    "arrêté ministériel",
    "arrêté préfectoral",
    "arrêté municipal",
    "note de service",
    "circulaire",
    "sur ordre du",
    "ordonnance",
    "fanambarana",
    "didim-pitondrana",
    "official statement",
    "decree",
)
VIOLENCE = (
    "tuez",
    "tuer",
    "brûlez",
    "brulez",
    "lynchez",
    "vengeance",
    "attaquez",
    "chassez",
    "à mort",
    "vonoy",
    "dorao",
    "kill them",
    "burn them",
)
ACCUSATION = (
    "voleur",
    "voleurs",
    "escroc",
    "corrompu",
    "assassin",
    "violeur",
    "sorcier",
    "mpangalatra",
    "mpamosavy",
    "thief",
    "corrupt",
)

LANG_WORDS = {
    "mg": {"ny", "sy", "amin", "izay", "dia", "fa", "ary", "tsy", "ho", "nanao", "olona", "manao"},
    "en": {"the", "and", "is", "are", "with", "this", "that", "from", "will", "have"},
    "fr": {"le", "la", "les", "des", "est", "une", "dans", "pour", "avec", "sur", "qui", "que"},
}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _find(text: str, phrases: tuple[str, ...]) -> list[str]:
    """Each phrase found in `text` (whole words, case and accents ignored), as written there."""
    found: list[str] = []
    for phrase in phrases:
        pattern = rf"(?<![\w]){re.escape(phrase)}(?![\w])"
        # Search the original text first (keeps accents and case), then an accent-free fold.
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            # « delestage » typed without accents still finds « délestage », and the reverse.
            folded = _fold(text)
            if len(folded) == len(text):
                m = re.search(rf"(?<![\w]){re.escape(_fold(phrase))}(?![\w])", folded)
        if m:
            quote = text[m.start() : m.end()]
            if quote.lower() not in {q.lower() for q in found}:
                found.append(quote)
    return found


def _shouted(text: str) -> tuple[float, list[str]]:
    """Share of letters inside words written in capitals, and those words. A short word alone in
    capitals is taken for an acronym (JIRAMA, INSTAT); in a run of capitals it is shouting."""
    letters = sum(c.isalpha() for c in text)
    tokens = re.findall(r"[^\W\d_]+", text)
    caps = [len(w) >= 2 and w.isupper() for w in tokens]
    shouted = []
    for i, w in enumerate(tokens):
        if len(w) < 4 or not caps[i]:
            continue
        in_run = (i > 0 and caps[i - 1]) or (i + 1 < len(tokens) and caps[i + 1])
        if len(w) > ACRONYM_MAX or in_run or not _looks_like_acronym(w):
            shouted.append(w)
    return (sum(len(w) for w in shouted) / letters if letters else 0.0), shouted


def _looks_like_acronym(word: str) -> bool:
    # JIRAMA, INSTAT, BNGRC: not a word of the lexicon. URGENT, ALERTE are shouting.
    return _fold(word) not in {_fold(p) for p in (*URGENCY, *SHARE, *EMOTIVE)}


def analyse(text: str) -> dict[str, Any]:
    """{level: sensationnaliste|marqué|neutre, signals: [{kind, quote}], caps_ratio, exclamations}.

    Kinds: caps, exclamations, urgency, share, emotive, hidden, emoji. Each quote is copied from
    the text. Sensational = three kinds or more, or urgency with an appeal to share."""
    text = text or ""
    signals: list[dict[str, str]] = []
    ratio, shouted = _shouted(text)
    for quote in _find(text, URGENCY):
        signals.append({"kind": "urgency", "quote": quote})
    for quote in _find(text, SHARE):
        signals.append({"kind": "share", "quote": quote})
    for quote in _find(text, EMOTIVE):
        signals.append({"kind": "emotive", "quote": quote})
    for quote in _find(text, HIDDEN):
        signals.append({"kind": "hidden", "quote": quote})
    if ratio >= CAPS_RATIO and shouted:
        signals.append({"kind": "caps", "quote": max(shouted, key=len)})
    bangs = re.findall(r"[!！]{2,}|[?!]{3,}", text)
    if bangs:
        signals.append({"kind": "exclamations", "quote": max(bangs, key=len)})
    emoji = [e for e in ALARM_EMOJI if e in text]
    if emoji:
        signals.append({"kind": "emoji", "quote": emoji[0]})
    kinds = {s["kind"] for s in signals}
    level = (
        "sensationnaliste"
        if len(kinds) >= 3 or {"urgency", "share"} <= kinds
        else "marqué"
        if kinds
        else "neutre"
    )
    return {
        "level": level,
        "signals": signals[:10],
        "caps_ratio": round(ratio, 2),
        "exclamations": text.count("!"),
    }


def risk(text: str) -> dict[str, Any]:
    """{level: high|medium|low, reasons: [{kind, quote}], by: "code"} from the danger lexicon.

    High: a call to violence, an accusation, or panic presented as an official order or
    communiqué. Medium: one kind. Low: none. A heuristic the journalist adjusts, never a verdict."""
    text = text or ""
    reasons: list[dict[str, str]] = []
    for kind, words in (
        ("violence", VIOLENCE),
        ("accusation", ACCUSATION),
        ("panic", PANIC),
        ("fake_order", ORDER),
    ):
        for quote in _find(text, words)[:2]:
            reasons.append({"kind": kind, "quote": quote})
    kinds = {r["kind"] for r in reasons}
    level = (
        "high"
        if kinds & {"violence", "accusation"} or {"panic", "fake_order"} <= kinds
        else "medium"
        if kinds
        else "low"
    )
    return {"level": level, "reasons": reasons[:6], "by": "code"}


def language(text: str) -> str:
    """fr, mg, en or "other", by counting common short words."""
    seen = re.findall(r"[a-z']+", _fold(text or ""))
    counts = {lang: sum(w in words for w in seen) for lang, words in LANG_WORDS.items()}
    best = max(counts, key=lambda lang: counts[lang])
    return best if counts[best] >= 2 else "other"
