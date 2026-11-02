// Build the pitch deck (fanilo-pitch.pptx) and the timed script (../script.md) from content.js.
//
//   node docs/pitch/deck/build.js
//
// The deck is drawn in the "dossier" world of the public pages (manila, ink, one alarm red, Anton
// for headlines, Special Elite for the file's typed labels, Public Sans for reading). All three
// fonts are on Google Fonts, so Google Slides renders them as drawn: File → Import slides, then
// edit the text. PowerPoint without the fonts falls back to Arial Narrow / Courier / Arial.
//
// Layout rules: 0.75 in margins, the chapter tab and the title always in the same place, content
// starts at 2.3 in, one idea per slide. Type scale: title 40 pt, key statement 26–28 pt, card
// titles 22–24 pt, reading text 16–20 pt, typed labels 13–14 pt. Nothing smaller than 13 pt except
// the photo credits on the last slide.
//
// Needs pptxgenjs (root devDependency). Everything else is in this folder.

const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require("./apply_theme.js");
const content = require("./content.js");

const OUT = path.join(__dirname, "fanilo-pitch.pptx");
const SCRIPT = path.join(__dirname, "..", "script.md");
const PIECES = path.join(__dirname, "..", "..", "..", "apps", "web", "public", "site", "dossier");

// The dossier palette (apps/web/.impeccable/surfaces/app-site-accueil-page-tsx.md).
const THEME = {
  name: "FANILO dossier",
  headFontFace: "Anton",
  bodyFontFace: "Public Sans",
  colors: {
    dk1: "141210", // ink
    lt1: "DCC9A3", // manila ground
    dk2: "A3231B", // red for text
    lt2: "EFE4C8", // index card
    accent1: "C42A20", // alarm red, stamps only
    accent2: "CFB98F", // deeper manila
    accent3: "5B544A", // soft ink
    accent4: "0F3B36", // the app's antenna green
    accent5: "F2C230", // the app's signal yellow
    accent6: "8A7F6B",
    hlink: "A3231B",
    folHlink: "5B544A",
  },
};
const TYPED = "Special Elite";
const ANTON = THEME.headFontFace;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 × 7.5 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = content.team.name;
pres.title = `${content.product.name} · pitch`;
pres.subject = content.event.name;
const C = pres.SchemeColor;

const M = 0.75; // side margin
const CW = 13.333 - 2 * M; // content width
const TOP = 2.3; // where content starts under the title

const up = (s) => String(s).toUpperCase();

// ---- layouts -------------------------------------------------------------------------------

pres.defineSlideMaster({ title: "DOSSIER_COVER", background: { color: THEME.colors.lt1 } });

pres.defineSlideMaster({
  title: "DOSSIER_CONTENT",
  background: { color: THEME.colors.lt1 },
  margin: [0.5, M, 0.6, M],
  objects: [
    {
      placeholder: {
        options: { name: "title", type: "title", x: M, y: 1.0, w: CW, h: 0.85, fontSize: 40, color: C.text1, margin: 0, valign: "top", align: "left", fit: "shrink" },
        text: "",
      },
    },
  ],
  slideNumber: { x: 12.0, y: 6.95, w: 0.6, h: 0.3, fontFace: TYPED, fontSize: 11, color: C.accent3, align: "right" },
});

pres.defineSlideMaster({ title: "DOSSIER_INK", background: { color: THEME.colors.dk1 } });

// ---- the file's furniture -----------------------------------------------------------------

function typed(slide, text, opts) {
  slide.addText(text, { fontFace: TYPED, fontSize: 13, color: C.text1, margin: 0, isTextBox: true, objectName: "typed label", ...opts });
}

function body(slide, text, opts) {
  slide.addText(text, { fontSize: 18, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "text", ...opts });
}

function anton(slide, text, opts) {
  slide.addText(up(text), { fontFace: ANTON, color: C.text1, margin: 0, isTextBox: true, objectName: "headline", ...opts });
}

// A folder tab: the chapter, in ink, above the title.
function tab(slide, text) {
  const w = Math.max(1.6, text.length * 0.13 + 0.7);
  slide.addShape(pres.ShapeType.trapezoid, { x: M, y: 0.5, w, h: 0.34, fill: { color: C.text1 }, objectName: "chapter tab" });
  slide.addText(up(text), {
    x: M, y: 0.5, w, h: 0.34, fontFace: ANTON, fontSize: 12, color: C.background1, align: "center", valign: "middle", charSpacing: 2, margin: 0, isTextBox: true, objectName: "chapter",
  });
}

// A stamp: alarm red, Anton, landed at an angle.
function stamp(slide, text, x, y, size = 44, rot = -11) {
  const w = text.length * size * 0.0085 + 0.6;
  const h = (size / 72) * 1.35;
  slide.addText(up(text), {
    x, y, w, h, rotate: rot, fontFace: ANTON, fontSize: size, color: C.accent1, align: "center", valign: "middle",
    line: { color: C.accent1, width: Math.max(2, size / 14) }, margin: 0.05, charSpacing: 2, isTextBox: true, objectName: `stamp ${text}`,
  });
}

// An index card, tilted under one degree.
function card(slide, x, y, w, h, rot = -0.4) {
  slide.addShape(pres.ShapeType.rect, {
    x, y, w, h, rotate: rot, fill: { color: C.background2 },
    shadow: { type: "outer", blur: 8, offset: 3, angle: 60, color: THEME.colors.dk1, opacity: 0.2 }, objectName: "index card",
  });
}

// A halftoned surveillance frame: the picture in an ink frame with its time code and caption.
function piece(slide, p, x, y, w) {
  const h = w / 1.5;
  const pad = 0.08;
  const capH = 0.4;
  slide.addShape(pres.ShapeType.rect, { x, y, w: w + 2 * pad, h: h + pad + capH, fill: { color: C.text1 }, objectName: "frame" });
  slide.addImage({ path: path.join(PIECES, p.file), x: x + pad, y: y + pad, w, h, objectName: p.caption });
  typed(slide, p.time, { x: x + pad + 0.12, y: y + pad + 0.1, w: 1.1, h: 0.28, color: C.background1, fill: { color: C.text1 }, fontSize: 11, align: "center", valign: "middle" });
  typed(slide, p.caption, { x: x + pad, y: y + pad + h + 0.06, w, h: capH - 0.12, color: C.background1, fontSize: 12, valign: "middle" });
}

function notes(slide, s) {
  slide.addNotes([`[${s.t}] ${s.serves}`, "", ...(s.notes || [])].join("\n"));
}

function contentSlide(s, section) {
  const slide = pres.addSlide({ masterName: "DOSSIER_CONTENT", sectionTitle: section });
  tab(slide, s.tab);
  slide.addText(up(s.title), { placeholder: "title" });
  notes(slide, s);
  return slide;
}

// ---- slides --------------------------------------------------------------------------------

const PITCH = "Pitch · 3 minutes";
const RESERVE = "Réserve · si le jury demande";

const render = {
  cover(s) {
    const slide = pres.addSlide({ masterName: "DOSSIER_COVER", sectionTitle: PITCH });
    typed(slide, s.label, { x: M, y: 0.6, w: 6, h: 0.3, fontSize: 14 });
    anton(slide, s.title, { x: M, y: 1.6, w: 6.9, h: 3.0, fontSize: 72, lineSpacingMultiple: 0.92, valign: "bottom", objectName: "title" });
    body(slide, s.sub, { x: M, y: 4.85, w: 6.4, h: 0.9, fontSize: 22 });
    typed(slide, content.team.name, { x: M, y: 6.7, w: 4, h: 0.3, fontSize: 14 });
    piece(slide, s.piece, 8.25, 1.6, 4.25);
    stamp(slide, s.stamp, 8.15, 2.95, 60);
    typed(slide, s.fictional, { x: 8.33, y: 5.1, w: 4, h: 0.3, fontSize: 12, color: C.accent3 });
    notes(slide, s);
  },

  need(s) {
    const slide = contentSlide(s, PITCH);
    slide.addText(`« ${s.quote} »`, { x: M, y: TOP + 0.15, w: 6.1, h: 2.6, fontSize: 28, italic: true, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "quote" });
    typed(slide, `— ${s.quoteBy}`, { x: M, y: TOP + 2.9, w: 6.1, h: 0.35, fontSize: 14 });
    const cx = 7.55, cw = 5.03;
    card(slide, cx, TOP, cw, 4.2);
    typed(slide, s.timeline.label, { x: cx + 0.4, y: TOP + 0.3, w: cw - 0.8, h: 0.3, color: C.accent3 });
    s.timeline.rows.forEach(([time, text], i) => {
      const y = TOP + 0.8 + i * 0.66;
      const last = i === s.timeline.rows.length - 1;
      anton(slide, time, { x: cx + 0.4, y, w: 1.0, h: 0.45, fontSize: 22, valign: "middle", objectName: `time ${time}` });
      body(slide, text, { x: cx + 1.55, y, w: cw - 1.95, h: 0.45, fontSize: 16, bold: last, valign: "middle" });
    });
  },

  refusal(s) {
    const slide = contentSlide(s, PITCH);
    anton(slide, s.stat.value, { x: M, y: TOP, w: 6.6, h: 1.9, fontSize: 110, valign: "bottom", objectName: "stat" });
    body(slide, s.stat.text, { x: M, y: TOP + 2.1, w: 6.2, h: 0.9, fontSize: 22 });
    typed(slide, s.stat.source, { x: M, y: TOP + 3.2, w: 6.2, h: 0.3, color: C.accent3 });
    stamp(slide, s.stamp, 8.3, TOP + 0.9, 96);
  },

  method(s) {
    const slide = contentSlide(s, PITCH);
    card(slide, M, TOP, CW, 4.1, 0.25);
    const ix = M + 0.45, iw = CW - 0.9, gap = 0.35;
    typed(slide, s.report, { x: ix, y: TOP + 0.35, w: 8, h: 0.3, color: C.accent3 });
    const colW = (iw - gap * (s.steps.length - 1)) / s.steps.length;
    s.steps.forEach(([time, head], i) => {
      const x = ix + i * (colW + gap);
      anton(slide, time, { x, y: TOP + 0.95, w: colW, h: 0.75, fontSize: 40, objectName: `time ${time}` });
      body(slide, head, { x, y: TOP + 1.85, w: colW, h: 0.9, fontSize: 20, bold: true });
    });
    typed(slide, s.signature, { x: ix, y: TOP + 3.4, w: 6, h: 0.3 });
    stamp(slide, "Vérifié", 9.9, TOP + 3.1, 30, -9);
  },

  demo(s) {
    const slide = contentSlide(s, PITCH);
    const fh = 3.2;
    slide.addShape(pres.ShapeType.rect, { x: M, y: TOP, w: CW, h: fh, fill: { color: C.text1 }, objectName: "demo frame" });
    typed(slide, "● REC", { x: M + 0.3, y: TOP + 0.25, w: 1, h: 0.3, color: C.background1 });
    anton(slide, "Démo", { x: M, y: TOP, w: CW, h: fh, fontSize: 60, color: C.background1, align: "center", valign: "middle", charSpacing: 6, objectName: "demo title" });
    const colW = (CW - 2 * 0.35) / 3;
    s.chapters.forEach((c, i) => {
      const x = M + i * (colW + 0.35);
      typed(slide, `Chapitre ${i + 1}`, { x, y: TOP + fh + 0.35, w: colW, h: 0.3, color: C.accent3 });
      body(slide, c, { x, y: TOP + fh + 0.7, w: colW, h: 0.5, fontSize: 18 });
    });
  },

  value(s) {
    const slide = contentSlide(s, PITCH);
    const gap = 0.35, cw = (CW - gap * 2) / 3, rot = [-0.5, 0.35, -0.25];
    s.cards.forEach(([head, text], i) => {
      const x = M + i * (cw + gap);
      card(slide, x, TOP + 0.1, cw, 3.7, rot[i]);
      body(slide, head, { x: x + 0.4, y: TOP + 0.55, w: cw - 0.8, h: 1.0, fontSize: 24, bold: true });
      body(slide, text, { x: x + 0.4, y: TOP + 1.75, w: cw - 0.8, h: 1.7, fontSize: 18 });
    });
  },

  next(s) {
    const slide = contentSlide(s, PITCH);
    const rot = [-0.3, 0.25, -0.2];
    s.items.forEach(([head, text], i) => {
      const y = TOP + 0.1 + i * 1.35;
      card(slide, M, y, CW, 1.05, rot[i]);
      anton(slide, head, { x: M + 0.45, y, w: 3.4, h: 1.05, fontSize: 26, valign: "middle", objectName: head });
      body(slide, text, { x: M + 4.0, y, w: CW - 4.45, h: 1.05, fontSize: 20, valign: "middle" });
    });
  },

  end(s) {
    const slide = pres.addSlide({ masterName: "DOSSIER_INK", sectionTitle: PITCH });
    anton(slide, s.title, { x: M, y: 1.6, w: CW, h: 1.9, fontSize: 120, color: C.background1, align: "center", valign: "middle", charSpacing: 4, objectName: "title" });
    body(slide, s.sub, { x: M, y: 3.6, w: CW, h: 0.7, fontSize: 30, color: C.background1, align: "center" });
    typed(slide, s.url, { x: M, y: 4.55, w: CW, h: 0.4, fontSize: 20, color: C.background1, align: "center" });
    typed(slide, [content.team.name, ...content.team.members].join(" · "), { x: M, y: 5.45, w: CW, h: 0.35, fontSize: 15, color: C.background2, align: "center" });
    typed(slide, s.credits, { x: M, y: 6.85, w: CW, h: 0.3, fontSize: 10, color: C.accent6, align: "center" });
    stamp(slide, s.stamp, 9.4, 0.75, 44, -12);
    notes(slide, s);
  },

  arch(s) {
    const slide = contentSlide({ ...s, t: "réserve", serves: "Article 5 · qualité technique", notes: ["Si le jury demande comment c'est fait."] }, RESERVE);
    const gap = 0.35, cw = (CW - gap * 2) / 3, rot = [-0.4, 0.3, -0.2];
    s.columns.forEach(([head, items], i) => {
      const x = M + i * (cw + gap);
      card(slide, x, TOP + 0.1, cw, 3.4, rot[i]);
      body(slide, head, { x: x + 0.4, y: TOP + 0.5, w: cw - 0.8, h: 0.5, fontSize: 22, bold: true });
      slide.addText(
        items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })),
        { x: x + 0.4, y: TOP + 1.25, w: cw - 0.8, h: 2.0, fontSize: 17, color: C.text1, valign: "top", paraSpaceAfter: 10, isTextBox: true, objectName: head },
      );
    });
    typed(slide, s.footer, { x: M, y: TOP + 3.95, w: CW, h: 0.3, color: C.accent3 });
  },

  team(s) {
    const slide = contentSlide({ ...s, t: "réserve", serves: "Article 3 · l'équipe de quatre", notes: ["Si le jury demande qui a fait quoi."] }, RESERVE);
    const gap = 0.3, cw = (CW - gap * 3) / 4, rot = [-0.5, 0.35, -0.25, 0.4];
    s.members.forEach(([name, role], i) => {
      const x = M + i * (cw + gap);
      card(slide, x, TOP + 0.1, cw, 3.0, rot[i]);
      anton(slide, name, { x: x + 0.3, y: TOP + 0.5, w: cw - 0.6, h: 1.2, fontSize: 24, valign: "top", objectName: name });
      typed(slide, role, { x: x + 0.3, y: TOP + 2.1, w: cw - 0.6, h: 0.6, fontSize: 14 });
    });
  },
};

pres.addSection({ title: PITCH });
for (const s of content.slides) render[s.kind](s);
pres.addSection({ title: RESERVE });
for (const s of content.backup) render[s.kind](s);

// ---- the timed script ----------------------------------------------------------------------

function writeScript() {
  const lines = [
    "# Script du pitch · 3 minutes",
    "",
    "Généré par `node docs/pitch/deck/build.js` à partir de `docs/pitch/deck/content.js` : modifiez le fichier de contenu, pas celui-ci.",
    "",
    `Qui parle : ${content.team.speaker}. Qui tient le clavier : ${content.team.driver}.`,
    "Limite : **3 minutes**, aucune seconde de plus (règlement, article 4). Les répétitions se chronomètrent slide par slide avec la colonne « Temps ».",
    "",
    "Le jury doit comprendre le besoin, la solution et son fonctionnement, l'intérêt pour les médias, et le potentiel (article 4). Il note la pertinence, l'utilité, la contribution à la résilience informationnelle, la qualité technique, le potentiel et le pitch lui-même (article 5).",
    "",
    "| Temps | Slide | Ce qu'elle sert |",
    "| --- | --- | --- |",
    ...content.slides.map((s, i) => `| ${s.t} | ${i + 1} · ${s.tab || s.kind} | ${s.serves} |`),
    "",
  ];
  content.slides.forEach((s, i) => {
    lines.push(`## ${i + 1} · ${s.title}`, "", `**${s.t}** · ${s.tab || s.kind}`, "");
    for (const n of s.notes || []) lines.push(`- ${n}`);
    lines.push("");
  });
  lines.push("## Réserve", "", "Après les 3 minutes, seulement si le jury demande :", "");
  for (const s of content.backup) lines.push(`- ${s.title}`);
  lines.push("");
  fs.writeFileSync(SCRIPT, lines.join("\n"));
}

function holes() {
  return [...new Set(JSON.stringify(content).match(/\{\{[^}]*\}\}/g) || [])];
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  writeScript();
  const h = holes();
  console.log(`wrote ${path.relative(process.cwd(), OUT)} (${content.slides.length} + ${content.backup.length} slides) and ${path.relative(process.cwd(), SCRIPT)}`);
  console.log(h.length ? `${h.length} holes left to fill:\n  ${h.join("\n  ")}` : "no holes left: the deck is ready");
})();
