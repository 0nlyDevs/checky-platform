"""The dossier's paper: « Carnet de diligence » and « Attestation de vérification » as real PDFs.

Drawn on the server with fpdf2, in its built-in Helvetica (Windows-1252: French and Malagasy
letters, « », ’, —, … are all there; anything else becomes « ? »), so the file is the same on every
browser and phone, its text can be searched and copied, and the phone app can download it too.
A4 portrait, ink on white, the dossier number in every page footer.
"""

import json
from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.core import dates

INK = (10, 10, 11)
MUTED = (85, 84, 78)
RULE = (190, 189, 183)
# Typographic spaces and marks the core font lacks, mapped before encoding.
_PLAIN = str.maketrans(
    {
        " ": " ",
        " ": " ",
        " ": " ",
        " ": " ",
        " ": " ",
        "−": "-",
        "‐": "-",
        "‑": "-",
        "✓": "v",
        "→": "->",
        "­": "",
    }
)


def plain(text: Any) -> str:
    """The text as the core font can print it."""
    value = str(text or "").translate(_PLAIN)
    return value.encode("cp1252", "replace").decode("cp1252")


def moment(value: Any) -> str:
    when = dates.parse_moment(value)
    return dates.fr_moment(when) if when else "—"


def day(value: Any) -> str:
    when = dates.parse(value)
    return dates.fr(when) if when else "—"


class Sheet(FPDF):
    def __init__(self, footer_text: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.core_fonts_encoding = "windows-1252"
        self.footer_text = plain(footer_text)
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(True, margin=18)
        self.set_text_color(*INK)
        self.set_draw_color(*RULE)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, self.footer_text, align="L")
        self.set_x(self.l_margin)
        self.cell(0, 5, f"{self.page_no()} / {{nb}}", align="R")
        self.set_text_color(*INK)

    # -- blocks -------------------------------------------------------------------------------

    def line_text(self, text: str, size: float = 10, style: str = "", h: float | None = None):
        self.set_font("Helvetica", style, size)
        self.multi_cell(0, h or size * 0.5, plain(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def muted(self, text: str, size: float = 9):
        self.set_text_color(*MUTED)
        self.line_text(text, size)
        self.set_text_color(*INK)

    def heading(self, text: str, size: float = 13):
        self.ln(4)
        self.line_text(text, size, "B", h=size * 0.55)
        self.rule()
        self.ln(1.5)

    def rule(self, heavy: bool = False):
        self.set_draw_color(*(INK if heavy else RULE))
        self.set_line_width(0.6 if heavy else 0.2)
        y = self.get_y() + 1
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.set_y(y + 1)

    def row(self, left: str, right: str, left_w: float = 42, size: float = 9.5):
        """A dated line: the moment on the left, what happened on the right (wrapping)."""
        self.set_font("Helvetica", "", size)
        y = self.get_y()
        if y > self.page_break_trigger - 10:
            self.add_page()
            y = self.get_y()
        self.set_text_color(*MUTED)
        self.multi_cell(left_w, size * 0.5, plain(left), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_text_color(*INK)
        self.set_xy(self.l_margin + left_w, y)
        self.multi_cell(0, size * 0.5, plain(right), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)


def _title_block(pdf: Sheet, kind: str, newsroom: str, ref: str | None, title: str) -> None:
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, plain(newsroom), new_x=XPos.LMARGIN, new_y=YPos.TOP)
    if ref:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*INK)
        pdf.cell(0, 5, plain(ref), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.ln(5)
    pdf.set_text_color(*INK)
    pdf.ln(1)
    pdf.line_text(kind, 20, "B", h=9)
    pdf.line_text(f"« {title} »", 12.5, h=6)


def carnet_pdf(book: Any, verdict_word: str | None) -> bytes:
    """The whole carnet of one dossier (`signing.CarnetOut`), dated line by line."""
    ref = book.ref or ""
    pdf = Sheet(f"Carnet de diligence · {book.newsroom}{f' · {ref}' if ref else ''}")
    pdf.set_title(plain(f"Carnet de diligence {ref}".strip()))
    pdf.set_author(plain(book.newsroom))
    pdf.set_creator("Checky")
    pdf.add_page()
    _title_block(pdf, "Carnet de diligence", book.newsroom, book.ref, book.title)
    n_e, n_s, n_q = len(book.entries), len(book.sources), len(book.questions)
    pdf.muted(
        f"Établi le {moment(book.generated_at)} (heure de Madagascar) · "
        f"{n_e} étape{'s' if n_e > 1 else ''} · {n_s} source{'s' if n_s > 1 else ''} · "
        f"{n_q} question{'s' if n_q > 1 else ''}"
        + (f" · rumeur vue le {day(book.first_seen_at)}" if book.first_seen_at else "")
    )
    pdf.ln(1)
    pdf.rule(heavy=True)
    if verdict_word:
        byline = book.byline or {}
        who = byline.get("journalist")
        when = byline.get("signed_at")
        pdf.ln(1)
        pdf.line_text(
            f"Verdict signé : {verdict_word}"
            + (f", par {who}" if who else "")
            + (f", le {moment(when)}" if when else ""),
            11,
            "B",
        )
        if book.reason:
            pdf.line_text(book.reason, 10)
    else:
        pdf.ln(1)
        pdf.muted(
            "Aucun verdict signé à ce jour : ce carnet dit ce qui a été fait, pas ce qui est vrai."
        )

    pdf.heading("Chronologie")
    if not book.entries:
        pdf.muted("Rien n'a encore été fait sur ce dossier.")
    for e in book.entries:
        pdf.row(moment(e.at), f"{e.actor} · {e.text}")

    pdf.heading("Sources au dossier")
    if not book.sources:
        pdf.muted("Aucune source.")
    for i, s in enumerate(book.sources, 1):
        when = (
            f"publiée le {day(s.published_at)}"
            if s.published_at
            else f"ajoutée le {moment(s.added_at)}"
        )
        pdf.line_text(f"{i}. {s.title}", 10, "B")
        if s.url:
            pdf.muted(s.url, 8.5)
        pdf.muted(f"{when} · {s.added_by}")
        pdf.ln(1)

    pdf.heading("Questions envoyées")
    if not book.questions:
        pdf.muted("Aucune question envoyée.")
    for q in book.questions:
        who = ", ".join(x for x in (q.contact, q.institution) if x) or "—"
        answer = (
            f"réponse le {moment(q.answered_at)} : {q.stance or 'réponse'}"
            if q.answered_at
            else "sans réponse"
        )
        sent = f"envoyée le {moment(q.sent_at)}" if q.sent_at else "préparée"
        pdf.row(who, f"{q.channel} · {sent} · {answer}", left_w=60)

    pdf.ln(4)
    pdf.rule()
    pdf.muted(
        "Ce carnet consigne ce que la rédaction a fait sur ce dossier et quand. Il ne dit pas que "
        "l'affirmation est vraie ou fausse : seul le verdict signé engage la rédaction.",
        8.5,
    )
    return bytes(pdf.output())


def attestation_pdf(att: Any) -> bytes:
    """One page: what was checked and when, signed with Checky's server key. The exact payload
    that was signed rides inside the PDF as `attestation.json`, so anyone can verify it."""
    p = att.payload
    ref = p.get("ref") or ""
    pdf = Sheet(f"Attestation de vérification · {p.get('newsroom')}{f' · {ref}' if ref else ''}")
    pdf.set_title(plain(f"Attestation de vérification {ref}".strip()))
    pdf.set_author(plain(p.get("newsroom")))
    pdf.set_creator("Checky")
    pdf.add_page()
    _title_block(pdf, "Attestation de vérification", p.get("newsroom") or "", ref, p["title"])
    pdf.muted(f"Émise le {moment(att.issued_at)} (heure de Madagascar)")
    pdf.ln(1)
    pdf.rule(heavy=True)
    pdf.ln(2)
    pdf.line_text(att.summary, 11, h=5.6)
    pdf.ln(2)

    pdf.heading("Ce qui a été vérifié, et quand", 11.5)
    if p.get("first_seen_at"):
        pdf.row("Rumeur vue", day(p["first_seen_at"]))
    sources = p.get("sources") or []
    shown = sources[:8]
    for i, s in enumerate(shown, 1):
        when = f" (publiée le {day(s.get('published_at'))})" if s.get("published_at") else ""
        pdf.row(f"Source {i}", f"{s.get('title')}{when}")
    if len(sources) > len(shown):
        pdf.row("", f"et {len(sources) - len(shown)} autre(s), dans le fichier joint")
    q = p.get("questions") or {}
    pdf.row(
        "Offices interrogés", f"{q.get('sent', 0)} question(s), {q.get('answered', 0)} réponse(s)"
    )
    pdf.row("Lectures de Checky", str(p.get("checks", 0)))
    if p.get("signed_at"):
        pdf.row("Verdict signé", f"{moment(p['signed_at'])} par {p.get('signed_by') or '—'}")
    if p.get("published_at"):
        pdf.row("Publié", moment(p["published_at"]))

    pdf.heading("Sceau", 11.5)
    pdf.set_font("Courier", "", 7.5)
    for label, value in (
        ("SHA-256 ", att.sha256),
        ("Clé     ", f"{att.key_id} · Ed25519 {att.public_key}"),
        ("Signature", att.signature),
    ):
        pdf.multi_cell(0, 3.6, plain(f"{label} {value}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(0.6)
    pdf.ln(1.5)
    pdf.muted(
        "Le texte signé est joint à ce PDF (attestation.json). Toute modification invalide la "
        "signature. Vérifiable par tous, sans compte : POST /api/v1/public/attestations/verify "
        "avec ce fichier.",
        8.5,
    )
    pdf.ln(2)
    pdf.rule()
    pdf.line_text(
        "Cette attestation prouve ce qui a été vérifié et quand. Elle n'affirme jamais que "
        "l'affirmation est vraie.",
        9.5,
        "B",
    )
    signed = json.dumps(
        {"payload": p, "signature": att.signature, "key_id": att.key_id},
        ensure_ascii=False,
        indent=2,
    ).encode()
    pdf.embed_file(
        bytes=signed,
        basename="attestation.json",
        desc="Texte signé et signature Ed25519",
        modification_date=datetime.now(UTC),
    )
    return bytes(pdf.output())


def file_name(kind: str, ref: str | None) -> str:
    """`carnet-FAN-0142.pdf`, `attestation-FAN-0142.pdf`."""
    safe = "".join(c for c in (ref or "dossier") if c.isalnum() or c in "-_") or "dossier"
    return f"{kind}-{safe}.pdf"
