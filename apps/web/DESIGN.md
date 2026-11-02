---
name: FANILO
description: Civic signage for rumours. One world, « Le signal clair », for the newsroom desk and the public site.
colors:
  chalk: "#f1f2ec"
  ink: "#171a18"
  card: "#ffffff"
  secondary: "#e4e6de"
  muted: "#e8eae3"
  muted-foreground: "#565c55"
  accent: "#e6e9df"
  border: "#d3d6cc"
  rule: "#d3d6cc"
  input: "#8a9086"
  destructive: "#9d382e"
  sidebar: "#e9ebe3"
  sidebar-accent: "#dcdfd4"
  citron: "#d7f45b"
  citron-foreground: "#171a18"
  citron-ink: "#4b5c00"
  live: "#171a18"
  live-foreground: "#f1f2ec"
  live-muted: "#b2b8ad"
  live-border: "#30352f"
  verdict-true: "#286044"
  verdict-true-on: "#ffffff"
  verdict-true-soft: "#e0ece3"
  verdict-true-ink: "#1f5238"
  verdict-misleading: "#e0a12a"
  verdict-misleading-on: "#171a18"
  verdict-misleading-soft: "#f8ebcf"
  verdict-misleading-ink: "#6f4600"
  verdict-false: "#9d382e"
  verdict-false-on: "#ffffff"
  verdict-false-soft: "#f4dfda"
  verdict-false-ink: "#872e25"
  verdict-unverifiable: "#656b63"
  verdict-unverifiable-on: "#ffffff"
  verdict-unverifiable-soft: "#e3e5df"
  verdict-unverifiable-ink: "#474c45"
  dark-background: "#121412"
  dark-foreground: "#eceee6"
  dark-card: "#1a1d1a"
  dark-popover: "#1e221e"
  dark-secondary: "#252924"
  dark-muted: "#212520"
  dark-muted-foreground: "#a5ab9f"
  dark-accent: "#272c26"
  dark-border: "#30352f"
  dark-input: "#6c7268"
  dark-destructive: "#e07a6c"
  dark-sidebar: "#161916"
  dark-sidebar-border: "#2a2f29"
  dark-live: "#0b0d0b"
  dark-live-muted: "#a5ab9f"
  dark-live-border: "#2a2f29"
  dark-verdict-true: "#4fa36f"
  dark-verdict-true-on: "#0f1410"
  dark-verdict-true-soft: "#17301f"
  dark-verdict-true-ink: "#8fd3a6"
  dark-verdict-misleading: "#e8b04a"
  dark-verdict-misleading-on: "#121412"
  dark-verdict-misleading-soft: "#33280f"
  dark-verdict-misleading-ink: "#f0c97a"
  dark-verdict-false: "#d96a5c"
  dark-verdict-false-on: "#121412"
  dark-verdict-false-soft: "#3a1a16"
  dark-verdict-false-ink: "#f2a69b"
  dark-verdict-unverifiable: "#959b91"
  dark-verdict-unverifiable-on: "#121412"
  dark-verdict-unverifiable-soft: "#262a25"
  dark-verdict-unverifiable-ink: "#c3c8bf"
typography:
  display:
    fontFamily: "Archivo, Atkinson Hyperlegible Next, sans-serif"
    fontSize: "clamp(2.5rem, 1.4rem + 3.6vw, 4.6rem)"
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Archivo, Atkinson Hyperlegible Next, sans-serif"
    fontSize: "clamp(2rem, 1.5rem + 1.6vw, 2.9rem)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.02em"
  verdict:
    fontFamily: "Archivo, Atkinson Hyperlegible Next, sans-serif"
    fontSize: "2.25rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Archivo, Atkinson Hyperlegible Next, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.4
  body:
    fontFamily: "Atkinson Hyperlegible Next, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  lead:
    fontFamily: "Atkinson Hyperlegible Next, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.625
  label:
    fontFamily: "Atkinson Hyperlegible Next, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 700
    lineHeight: 1.4
  reference:
    fontFamily: "Archivo, Atkinson Hyperlegible Next, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    fontFeature: "tnum"
rounded:
  sm: "2px"
  md: "3px"
  lg: "4px"
  xl: "6px"
  sheet: "12px"
  pill: "999px"
spacing:
  page-x-phone: "16px"
  page-x-desk: "32px"
  page-x-site: "40px"
  rail: "240px"
  assistant-dock: "400px"
  site-max: "1408px"
  desk-max: "1440px"
components:
  button-action:
    backgroundColor: "{colors.citron}"
    textColor: "{colors.citron-foreground}"
    rounded: "{rounded.md}"
    height: "48px"
    padding: "0 20px"
  button-action-hover:
    backgroundColor: "color-mix(in oklch, #d7f45b, #171a18 8%)"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.chalk}"
    rounded: "{rounded.md}"
    height: "32px"
    padding: "0 10px"
  button-outline:
    backgroundColor: "{colors.chalk}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "32px"
  check-field:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "16px 16px 8px"
  tab-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.chalk}"
    rounded: "{rounded.md}"
    height: "44px"
  nav-item-active:
    backgroundColor: "{colors.citron}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
  step-disc-active:
    backgroundColor: "{colors.citron}"
    textColor: "{colors.citron-foreground}"
    rounded: "{rounded.pill}"
    size: "40px"
  step-disc-done:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.citron}"
    rounded: "{rounded.pill}"
    size: "40px"
  step-disc-waiting:
    backgroundColor: "{colors.card}"
    textColor: "{colors.muted-foreground}"
    rounded: "{rounded.pill}"
    size: "40px"
  verdict-chip-false:
    backgroundColor: "{colors.verdict-false-soft}"
    textColor: "{colors.verdict-false-ink}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  verdict-block-misleading:
    backgroundColor: "{colors.verdict-misleading-soft}"
    textColor: "{colors.verdict-misleading-ink}"
    typography: "{typography.verdict}"
    rounded: "{rounded.md}"
    padding: "20px"
  live-panel:
    backgroundColor: "{colors.live}"
    textColor: "{colors.live-foreground}"
    rounded: "{rounded.md}"
    padding: "16px"
  assistant-panel:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    width: "400px"
---

# Design System: FANILO

## Overview

**Creative North Star: "Le signal clair"**

FANILO reads like civic signage for rumours: a chalk ground, green-black ink, square-ish edges, heavy Archivo words and one citron that says "here". The same world serves the newsroom desk (`/w/…`) and the public site (`/`, `/verifies`, `/signaler`, `/suivi`, sign-in and sign-up); there is no second identity. A screen is a notice board you can act on: a big field to paste a message, a numbered line that shows how far a dossier has come, and verdicts stated as words with icons, never as colour alone.

The organising device is the **numbered line**: 01 L'affirmation, 02 Les éléments, 03 La conclusion. It explains the method on the home page, runs live on Vérifier, sits mini on each dossier row and runs down the gutter of a claim's page. FANILO's own work shows in an **ink panel** (the live log « Le travail de FANILO », the public answer, the newsroom band), so machine activity is always visually separate from the journalist's page. The AI only suggests: suggestion is drawn dashed, a journalist's confirmation is drawn solid.

Density is calm and legible rather than packed: Atkinson Hyperlegible Next for every word a person reads (a cracked phone in full sun is the reference reader), generous 18px leads, 44–48px touch targets for the main controls. Motion is short and once: highlights sweep in, sources arrive, the verdict lands, the active step breathes; all of it collapses under `prefers-reduced-motion`.

**Key Characteristics:**
- One world for desk and public site; light and dark themes from the same tokens.
- Citron (`#d7f45b`) only for the one action of a screen, the active step and highlights.
- Verdicts always icon + word on their own four-token family; status always ink icons.
- AI suggestion dashed, confirmed solid.
- The numbered line 01/02/03 as the reused signature.
- Ink panels for FANILO's live work; square-ish corners (2–4px); flat, no ambient shadows.

## Colors

A near-neutral chalk-and-ink palette with one acid citron accent and a separate, muted verdict family.

### Primary
- **Citron** (`citron`): the one action of a screen (`Button variant="action"`), the active step disc, the active nav item (`--sidebar-primary`), text selection and the `.signal-mark` highlighter on flagged phrases. Text on it is always ink (`citron-foreground`). On light grounds where citron must be read as text, use **Citron Ink** (`citron-ink`); in dark mode citron itself is readable (14.97:1 on the dark ground) and is also the focus ring.

### Neutral
- **Chalk** (`chalk`): page ground in light mode; also the text colour on ink.
- **Ink** (`ink`): text, `--primary` buttons, active tabs, done step discs, the rule above the dossier list, active link underlines.
- **Card White** (`card`): fields, cards, dossier rows on hover, the specimen, the assistant panel.
- **Muted Chalk** (`muted`) and **Secondary** (`secondary`), **Accent** (`accent`): quiet grounds (quoted messages, answer bubbles, hovers).
- **Muted Ink** (`muted-foreground`): secondary text, placeholders, meta under titles.
- **Hairline** (`border`, `rule`): dividers and card edges. **Field Edge** (`input`): field and waiting-disc strokes (non-text, ≥ 3:1).
- **Rail** (`sidebar`, `sidebar-accent`): the desk's light rail and phone bars.
- **Live Ink** (`live`, `live-foreground`, `live-muted`, `live-border`): the ink panel where FANILO's work shows (live log, public answer, assistant header and voice stage, the newsroom band, the user's own question bubble).
- **Destructive** (`destructive`): destructive buttons only, never a verdict.

### Verdicts
Four families, each with **fill** (solid blocks such as the downloadable card), **on** (text on fill), **soft** (badge and block ground) and **ink** (verdict text on soft, chalk or card): `verdict-true` (Vrai, CircleCheck), `verdict-misleading` (Trompeur, TriangleAlert), `verdict-false` (Faux, CircleX), `verdict-unverifiable` (Invérifiable, CircleHelp). Dark mode values are the `dark-verdict-*` keys.

### Dark theme
`.dark` swaps every token (`dark-*` keys). The citron stays `#d7f45b`; the ring becomes citron; `.signal-mark` forces ink text on citron. The live panel goes a step darker than the ground (`dark-live`).

### Measured contrast (WCAG, text pairs)
Light: ink/chalk 15.58, ink/card 17.54, muted-foreground on chalk 6.10 / card 6.87 / muted 5.66 / sidebar 5.71, ink on citron 14.18, citron-ink on chalk 6.59, live-foreground/live 15.58, live-muted/live 8.65, destructive on chalk 6.14. Verdicts: on/fill 7.38, 7.77, 6.91, 5.47; ink/soft 7.44, 6.97, 6.71, 6.93; ink on chalk ≥ 7.31.
Dark: foreground/background 15.81, foreground/card 14.53, muted-foreground on background 7.87 / card 7.23 / muted 6.61, citron on background 14.97, live-foreground/live 16.66, live-muted/live 8.29, destructive 6.32 / 5.81. Verdicts: on/fill 6.03, 9.47, 5.44, 6.50; ink/soft 8.14, 9.19, 7.99, 8.56.
`input` (2.91 light, 3.74 dark on the ground) is a stroke colour only; never set text in it.

### Named Rules
**The One Citron Rule.** Citron marks the one action of a screen, the active step, the active nav item and highlighted phrases. Never a verdict, a status, a decoration or a second competing button.

**The Word-and-Icon Rule.** A verdict is always its lucide icon plus its word in the verdict's ink. Colour alone never carries a verdict.

**The Status-Is-Not-Truth Rule.** Workflow status (À vérifier CircleDashed, En cours Timer, Vérifié ShieldCheck, Publié Radio) uses ink icons, muted only for « À vérifier »; never a verdict colour.

**The 4.5 Rule.** Every text pair is ≥ 4.5:1 in both themes, measured against its real ground. No opacity on text; placeholders use `muted-foreground`; disabled controls sit at 60 %.

## Typography

**Display Font:** Archivo (500–800, `--font-archivo`, fallback Atkinson Hyperlegible Next)
**Body Font:** Atkinson Hyperlegible Next (`--font-atkinson`, fallback ui-sans-serif, system-ui)

**Character:** Archivo is the signage voice: heavy, tight, for titles, numbers, references and verdict words. Atkinson Hyperlegible Next is for everything a person reads, chosen for legibility on poor screens.

### Hierarchy
- **Display** (800, clamp(2.5rem…4.6rem), 0.95, −0.03em): the public home headline only, with its second line lit by `.signal-mark`.
- **Headline / page title** (`.page-title`: 800, clamp(2rem…2.9rem), 1, −0.02em): every page's H1 on desk and site. Meta (date, counts, demo marker) goes under it in muted text.
- **Section headline** (Archivo 800, 1.875–2.25rem, tracking-tight): public section titles (« Comment … », the newsroom band).
- **Verdict** (Archivo 800, 1.875–2.25rem in a block, up to 3rem on the Vérifier result): the verdict word next to its icon.
- **Title** (Archivo 700, 1.125–1.25rem): section H2s in pages and panels; step labels at 1.05rem.
- **Body** (Atkinson 400, 1rem/1.5): reading text, dossier titles in bold. **Lead** (1.125–1.25rem, relaxed, max ~50–62ch): the line under a page title and the text in the check field.
- **Label** (Atkinson 700, 0.875rem, sentence case): field labels, small section heads, verdict chips.
- **Reference** (Archivo 700, tabular): FAN refs, times, counts, step numbers 01/02/03. `time` and `.tabular` always use tabular figures.

### Named Rules
**The Sentence-Case Rule.** Labels and headings are sentence case. No uppercase tracked eyebrow or kicker above a heading; meta sits under the title.

**The Two-Voices Rule.** Archivo speaks (titles, numbers, verdicts); Atkinson is read. Do not set paragraphs in Archivo or verdict words in Atkinson.

## Layout

- **Desk:** a 240px light rail (`lg` and up) with the wordmark, workspace switcher, nav (Vérifier, Dossiers, Sources; Équipe and Paramètres at the foot), the assistant launcher (ink) and the user menu. Content max 1440px, `lg:px-8`. Under `lg`: a top bar (wordmark, workspace, avatar) and a fixed four-slot bottom bar (three places + Assistant), with `pb-24` on main.
- **Public site:** sticky header on chalk (wordmark, three links, Assistant, « Espace rédaction » ink button), max 1408px, `px-4 lg:px-10`; on phone the three links drop to a second row of three equal tabs. Footer in three columns.
- **Assistant:** docked right at 400px from `lg`, and the page is padded `lg:pr-[25rem]` while it is open, so it never covers what is read. Under `lg` it is a bottom sheet (min(64dvh, 36rem)).
- **Vérifier (desk home):** title, lead, the big field; once run, a two-column result (the message with highlights and warning signs | the full numbered line over the ink live log), then the sources wall; open dossiers and recent verdicts in a right column on wide screens. A fixed bottom bar carries « Suivre dans le desk ».
- **Dossiers:** title + meta, tabs with counts, search and filters, then a ruled list (ink top rule, hairline between rows). Row grid: ref and age | title with status/origin/sources | mini line | verdict | assignee; the mini line appears from the `@4xl` container width.
- **Claim page:** content and a 320px side column on `lg`; the main column is the numbered line run down a gutter (24px phone, 40px from `md`), each part of the dossier hanging from its disc.
- **Public home:** hero split 1.1 : 1 (headline, lead, check field, three recent verdicts | the fictional specimen), then « how it works » as three numbered cells on card, then the ink newsroom band.
- **Rhythm:** 4px base; 16px gutters on phone; sections 56–80px apart on the public site; touch targets 44px (tabs, verdict radios, assistant controls) and 48px for the action button.

## Elevation & Depth

Flat. Depth comes from tone (chalk ground, white cards, ink panels) and hairlines, not shadows. The only shadows are functional.

### Shadow Vocabulary
- **Sheet lift** (`box-shadow: 0 -18px 40px -24px rgb(23 26 24 / 0.45)`): the assistant as a phone bottom sheet; removed when docked.
- **Step breathe** (`box-shadow: 0 0 0 7px color-mix(in srgb, var(--action) 35%, transparent)`, pulsing): the active step disc.
- **Recording pulse** (`0 0 0 6px rgb(157 56 46 / 0.2)`): the microphone while listening.
- **Drag lift**: only the card being dragged on the board lifts, tilted 1.5°. Its shadow is tinted with ink: `0 14px 32px -12px rgb(23 26 24 / 0.45)`.

### Named Rules
**The Flat-Ground Rule.** Cards and panels sit flat on a hairline or a tonal change. A shadow means "this is moving or live", never "this is important".

## Shapes

Square-ish: `--radius` is 4px, so `rounded-sm` 2px (chips, highlights), `rounded-md` 3px (buttons, fields, cards, verdict blocks), `rounded-lg` 4px. Full rounds are reserved for step discs, avatars, the voice button and small count pills. The phone sheet takes 12px top corners; chat bubbles 10px with one 2px corner pointing at the speaker. Borders are 1px hairlines; 2px for emphasis (verdict block, chosen verdict radio, the « à confirmer » banner), dashed when the thing is an AI suggestion.

## Components

### Buttons
- **Shape:** gently squared (3px).
- **Action** (`variant="action"`, usually `size="xl"`: 48px, 20px side padding, 16px bold, 20px icon): citron with ink text, hover mixes 8% ink in. One per screen: check / verify submit, auth submit, report submit, « Suivre dans le desk », « Nouvelle affirmation », « Revoir la suggestion ».
- **Primary** (default): ink with chalk text, for confirmations inside a flow (« Confirmer … »).
- **Outline / Ghost / Secondary:** chalk or transparent with muted hover; dictation, retry, cancel.
- **Focus:** 2px ring outline offset 2px (ink in light, citron in dark). Disabled at 60 %.

### Verdict chip and badge
- **VerdictChip** (confirmed): soft ground, ink text, icon 14px + word, bold, 2px radius.
- **VerdictBadge**: confirmed = soft fill; AI suggestion = 1px dashed outline in the verdict ink on transparent ground, with « · suggéré » (kept for screen readers in `compact`). No verdict = muted « Pas de verdict ».

### Verdict block
The conclusion stated: 2px border in the verdict ink on its soft ground, icon + word in Archivo 800 (30–36px), then « Suggéré par FANILO » with a Sparkles icon (dashed border) or the confirmation line (solid). It lands once (`.verdict-land`, 0.5s). The verdict radios below it are four 44px buttons in each verdict's ink; the chosen one gets a 2px border on soft ground. Choosing never commits: a recap card says what changes and warns when it goes against the AI suggestion.

### Inputs / Fields
- **Check field:** white card, 1px `input` stroke, 3px radius; an 18px relaxed textarea, then a hairline toolbar with dictation on the left and the action button on the right. Focus: border to ink plus a 2px ink ring at 15 %.
- **Small inputs** (search, selects): 40px, white card, shadcn defaults.

### Navigation
- **Desk rail:** items 40px, 20px icons; active = citron fill, ink bold text; others ink with `sidebar-accent` hover. Phone bar: icon in a 48×24 pill, citron when active, label under it.
- **Public header:** active link = bold with a 2px ink underline offset 7px; others hover to accent. Phone: tabs with a 2px ink bottom border when active.
- **Tabs (Dossiers):** 44px; active = ink fill, chalk text; counts in a 2px-radius pill, citron only on « À confirmer » when it has items.

### Live panel
Ink ground, 3px radius, 16px padding; Archivo 14px bold header with a status dot (citron pulsing while running, muted when done); lines arrive one by one with a tabular muted timestamp. Used for « Le travail de FANILO », the public assistant answer and, full width, the newsroom band.

### The numbered line (signature)
`StepLine` from `components/flow/step-line.tsx`, driven by `claimSteps(claim)`.
- **Discs:** done = ink disc with a citron check (background-coloured check in dark); active = citron disc that breathes (`.step-active`); suggested = 2px dashed ink ring on card; waiting = 1px `input` ring with muted number; failed = 2px `verdict-false` ring with an X. Numbers are 01/02/03 in Archivo tabular.
- **Rule:** 1px vertical (full) or horizontal (mini) rule, ink once the next step has started, hairline while it waits.
- **`full`:** 40px discs, Archivo label, state word and a muted note per step; `explain` shows the method with no state.
- **`mini`:** 24px discs, 68px per step, short labels; on each dossier row and the open-dossier cards.
- **In the claim page:** `StepDisc` alone hangs each part of the dossier in the gutter.

### Highlighter
`.signal-mark`: a citron sweep (0.9s, staggered 220ms by `--i`) behind phrases FANILO flagged in a message, and behind the home headline's second line. Text stays its own colour (ink in dark).

### Assistant
The site agent on every page. Ink header (Archivo 18px title, 40px icon buttons, the « VOIX » pill toggle: outline at rest, citron fill with a red dot while on), a log of bubbles (question = ink, answer = muted), proposals as hairline cards (ink border while pending) with a citron « Confirmer » and an outline « Annuler », and a form with a 44px textarea, mic and citron send. In voice mode the keyboard gives way to the ink **voice stage**: Archivo 22px phase word (JE VOUS ÉCOUTE, JE TRANSCRIS, JE CHERCHE, JE RÉPONDS, EN PAUSE), a hint, five level bars (citron while listening), a 56px round button (red and pulsing while listening) and « Écrire plutôt ».

### Sources wall and specimen
Sources arrive as hairline cards (`.arrive`, 0.45s rise, 90ms stagger). The public specimen is a white card labelled « Exemple fictif » in a 1px ink box: the message on muted ground with highlights, a done full line, then a verdict block.

## Do's and Don'ts

### Do:
- **Do** build every new screen from these tokens and components: `.page-title` H1 with meta under it, the check field, `StepLine`/`StepDisc` for progress, `VerdictChip`/`VerdictBadge`/the verdict block for verdicts, the live panel for anything FANILO is doing.
- **Do** give each screen exactly one `variant="action"` button; everything else is primary, outline or ghost.
- **Do** draw an AI suggestion dashed and a journalist's confirmation solid, and leave the final verdict to a journalist's explicit click.
- **Do** pair every verdict with its icon and word, and every status with its ink lucide icon.
- **Do** measure every new text pair in light and dark against its real ground (≥ 4.5:1); use `*-ink` tokens for coloured text on light grounds.
- **Do** keep corners at 2–4px and edges as 1px hairlines; reserve full rounds for discs, avatars and pills.
- **Do** pad the page when the assistant opens on desktop (`lg:pr-[25rem]`) and use the bottom sheet on phone.
- **Do** keep motion single-shot (`.arrive`, `.verdict-land`, `.signal-mark`) except the active step and recording indicators, and respect `prefers-reduced-motion`.
- **Do** use the shared neutral quote rule (1px hairline on the left of a quoted passage) for verbatim quotes; it is a quotation mark, not an accent.

### Don't:
- **Don't** use citron for a verdict, a status, an icon bullet, a badge that is not the active step or a second action on the same screen.
- **Don't** carry a verdict by colour alone, or colour a status with a verdict family.
- **Don't** put an uppercase tracked eyebrow or kicker above a heading.
- **Don't** add coloured border-left accents to cards, callouts or rows.
- **Don't** let the assistant float over the page on desktop.
- **Don't** set text in opacity or in the `input` stroke colour.
- **Don't** add ambient shadows to cards; depth is tone and hairline.
- **Don't** bring back the retired worlds (« Grille d'antenne » green rail and signal yellow, « Le dossier » manila, Anton, Special Elite, halftoned photographs) in the app. The pitch kit (`docs/pitch/`, `scripts/pitch_video.py`) still uses Anton, Special Elite and the photographs in `public/site/`; they belong to the pitch kit only and are not part of the app's system.
