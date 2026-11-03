---
name: Checky
description: Ink and paper. A minimal theme where colour lives only on verdicts, for the newsroom desk and the public site.
colors:
  background: "#f3f2ee"
  foreground: "#0a0a0b"
  card: "#fbfaf7"
  raised: "#e9e8e2"
  active: "#e2e1da"
  muted-foreground: "#55544e"
  border: "rgba(10,10,11,.10)"
  rule: "rgba(10,10,11,.07)"
  input: "rgba(10,10,11,.24)"
  primary: "#0a0a0b"
  primary-foreground: "#f3f2ee"
  destructive: "#b3231a"
  nav: "#0a0a0b"
  nav-foreground: "#b9b8b2"
  nav-hover: "#1f1f22"
  nav-active: "#f3f2ee"
  nav-active-foreground: "#0a0a0b"
  tag-inverted: "#0a0a0b"
  tag-inverted-foreground: "#f3f2ee"
  toast: "#0a0a0b"
  toast-foreground: "#f3f2ee"
  verdict-true: "#0b6b3a"
  verdict-true-on: "#ffffff"
  verdict-true-soft: "#e1f3e8"
  verdict-true-ink: "#0b6b3a"
  verdict-misleading: "#8a5700"
  verdict-misleading-on: "#ffffff"
  verdict-misleading-soft: "#f9ecd2"
  verdict-misleading-ink: "#8a5700"
  verdict-false: "#b3231a"
  verdict-false-on: "#ffffff"
  verdict-false-soft: "#fbe3e0"
  verdict-false-ink: "#b3231a"
  verdict-unverifiable: "#1d58c4"
  verdict-unverifiable-on: "#ffffff"
  verdict-unverifiable-soft: "#e0eafb"
  verdict-unverifiable-ink: "#1d58c4"
  dark-background: "#0a0a0b"
  dark-foreground: "#f3f2ee"
  dark-card: "#111113"
  dark-raised: "#19191c"
  dark-active: "#232327"
  dark-muted-foreground: "#a6a5a0"
  dark-border: "rgba(243,242,238,.10)"
  dark-rule: "rgba(243,242,238,.07)"
  dark-input: "rgba(243,242,238,.26)"
  dark-primary: "#f3f2ee"
  dark-primary-foreground: "#0a0a0b"
  dark-destructive: "#ff6a5f"
  dark-nav: "#1c1c1f"
  dark-nav-foreground: "#b4b3ad"
  dark-nav-hover: "#2a2a2e"
  dark-nav-active: "#f3f2ee"
  dark-nav-active-foreground: "#0a0a0b"
  dark-tag-inverted: "#f3f2ee"
  dark-tag-inverted-foreground: "#0a0a0b"
  dark-toast: "#f3f2ee"
  dark-toast-foreground: "#0a0a0b"
  dark-verdict-true: "#3ddc84"
  dark-verdict-true-on: "#0a0a0b"
  dark-verdict-true-soft: "#0f2219"
  dark-verdict-true-ink: "#3ddc84"
  dark-verdict-misleading: "#ffb224"
  dark-verdict-misleading-on: "#0a0a0b"
  dark-verdict-misleading-soft: "#29200c"
  dark-verdict-misleading-ink: "#ffb224"
  dark-verdict-false: "#ff6a5f"
  dark-verdict-false-on: "#0a0a0b"
  dark-verdict-false-soft: "#2a1311"
  dark-verdict-false-ink: "#ff6a5f"
  dark-verdict-unverifiable: "#6aa8ff"
  dark-verdict-unverifiable-on: "#0a0a0b"
  dark-verdict-unverifiable-soft: "#101a2b"
  dark-verdict-unverifiable-ink: "#6aa8ff"
typography:
  display:
    fontFamily: "Bricolage Grotesque, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(2.5rem, 1.4rem + 3.6vw, 4.6rem)"
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Bricolage Grotesque, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(2rem, 1.5rem + 1.6vw, 2.9rem)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.03em"
  verdict:
    fontFamily: "Bricolage Grotesque, ui-sans-serif, system-ui, sans-serif"
    fontSize: "2.25rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Bricolage Grotesque, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.4
  body:
    fontFamily: "Bricolage Grotesque, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Bricolage Grotesque, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.4
  quote:
    fontFamily: "Cormorant Garamond, Georgia, serif"
    fontSize: "1.125rem"
    fontWeight: 500
    fontStyle: "italic"
    lineHeight: 1.4
rounded:
  tag: "6px"
  menu: "18px"
  card: "20px"
  pill: "999px"
spacing:
  page-x-phone: "16px"
  page-x-desk: "32px"
  site-max: "1408px"
  desk-max: "1440px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.pill}"
    height: "40px"
  button-secondary:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.pill}"
    height: "40px"
  nav-island:
    backgroundColor: "{colors.nav}"
    textColor: "{colors.nav-foreground}"
    rounded: "{rounded.pill}"
  nav-tab-active:
    backgroundColor: "{colors.nav-active}"
    textColor: "{colors.nav-active-foreground}"
    rounded: "{rounded.pill}"
  tag-inverted:
    backgroundColor: "{colors.tag-inverted}"
    textColor: "{colors.tag-inverted-foreground}"
    rounded: "{rounded.tag}"
  verdict-chip-false:
    backgroundColor: "{colors.verdict-false-soft}"
    textColor: "{colors.verdict-false-ink}"
    rounded: "{rounded.pill}"
  toast:
    backgroundColor: "{colors.toast}"
    textColor: "{colors.toast-foreground}"
    rounded: "{rounded.pill}"
---

# Design System: Checky

## Overview

**Creative North Star: "Ink and paper"**

Checky is a paper ground and one ink. Nothing on a screen is coloured unless it is a verdict: the action is ink, the navigation is an ink island with a paper pill, the live work is ink plus motion. The same world serves the newsroom desk (`/w/…`) and the public site (`/home`, `/verdicts`, `/report`, `/track`, sign-in and sign-up), in light and dark from the same token names.

The organising device is the **numbered line**: 1 L'affirmation, 2 Les éléments, 3 La conclusion (`components/flow/step-line.tsx`). Quotations (the verdict quote, source quotes) are set in Cormorant Garamond italic against the Bricolage Grotesque of everything else.

**Key Characteristics:**
- Colour only on verdicts; everything else is ink, paper and their tints.
- One typeface for everything (Bricolage Grotesque), one italic serif for verbatim quotations.
- Generous radius: cards 20, controls and chips fully round, menus 18, small tags 6.
- Verdicts always icon + word on their own four-token family; AI suggestion dashed, confirmed solid.
- Shadows only on what floats (menus, dialogs, toasts); depth elsewhere is tone and hairline.

### Shared public footer

The landing and every public page use `components/site/site-footer.tsx`; sign-in and sign-up
have none.
Its escaped markup lives in `lib/public-footer.ts`, shared with the script-free `/flashes`
bulletin. `public/site/public-footer.css` is the single scoped stylesheet. The footer
keeps the landing's ink background in both themes; its full-width white wordmark is
the last element, slightly cropped with a lower bloom and progressive blur. Section
links point to `/home#…` so they also work away from the landing. It is hidden in print.

## Colors

### Neutrals (light / dark)
- **Ground** (`background`): `#f3f2ee` / `#0a0a0b`. **Text** (`foreground`): `#0a0a0b` / `#f3f2ee`.
- **Surface** (`card`, `popover`): `#fbfaf7` / `#111113`. **Raised** (`raised`, also `secondary` and `muted`): `#e9e8e2` / `#19191c`. **Active** (`active`, also `accent`): `#e2e1da` / `#232327`; hover and selected fills.
- **Secondary text** (`muted-foreground`): `#55544e` / `#a6a5a0`.
- **Border / rule / control border** (`border`, `rule`, `input`) are the text colour at 10 % / 7 % / 24-26 %. They are strokes, never text.
- **Primary** (`primary` / `primary-foreground`): the one action of a screen, ink on paper in light and paper on ink in dark. `--action` and `--action-foreground` alias it.
- **Nav island** (`nav`, `nav-foreground`, `nav-hover`, `nav-active`, `nav-active-foreground`): `#0a0a0b` with `#b9b8b2` labels in light, `#1c1c1f` with `#b4b3ad` in dark; the active pill is paper `#f3f2ee` in both and its label is the fixed ink `#0a0a0b`. `--sidebar-*` is the same set.
- **Live panel** (`live*`): ink in light, `raised` in dark; where Checky's work shows.
- **Inverted tag** (`tag-inverted*`) for `Officielle` and `Public`; **toast** (`toast*`) for the ink pill with undo.

### Verdicts
Four families, each with **fill** (solid blocks, the downloadable card), **on** (text on fill), **soft** (wash) and **ink** (verdict text on soft, background or card). On/fill is `#ffffff` in light and `#0a0a0b` in dark for all four.

| Verdict | Ink light | Wash light | Ink dark | Wash dark |
| --- | --- | --- | --- | --- |
| vrai (`true`) | `#0b6b3a` | `#e1f3e8` | `#3ddc84` | `#0f2219` |
| faux (`false`) | `#b3231a` | `#fbe3e0` | `#ff6a5f` | `#2a1311` |
| trompeur (`misleading`) | `#8a5700` | `#f9ecd2` | `#ffb224` | `#29200c` |
| invérifiable (`unverifiable`) | `#1d58c4` | `#e0eafb` | `#6aa8ff` | `#101a2b` |

### Measured contrast
`lib/tokens.ts` holds the pairs and `npm test` fails when one drops under 4.5:1 in either theme (ink on paper is 17.67:1). Every filled background below has its own foreground token and they are used together.

### Named Rules
**The Colour-Is-Verdict Rule.** No hue outside the four verdict families. The citron of the previous identity is gone.

**The Word-and-Icon Rule.** A verdict is always its icon (from `lib/icons.ts`, Phosphor duotone wrapped as `Icon*`) plus its word in the verdict's ink. Colour alone never carries a verdict.

**The Paired-Token Rule.** Every filled background is used with its own foreground: `primary` / `primary-foreground`, `nav` / `nav-foreground`, `nav-active` / `nav-active-foreground` (ink in both themes: theme text on the paper pill is 1:1 in dark), `verdict-*-soft` / `verdict-*-ink`, `verdict-*` / `verdict-*-on`, `tag-inverted` / `tag-inverted-foreground`, `toast` / `toast-foreground`. A class that sets one without the other (`hover:bg-primary` with no `hover:text-primary-foreground`) is a bug.

**The Status-Is-Not-Truth Rule.** Workflow status uses ink icons, never a verdict colour.

**The 4.5 Rule.** Every text pair is at least 4.5:1 in both themes, against its real ground. No opacity on text; placeholders and disabled labels use `muted-foreground`.

## Typography

**One face:** Bricolage Grotesque (variable, optical size, 400-800), `--font-bricolage`, exposed as `font-sans`, `font-display` and `font-heading`.
**Quotations:** Cormorant Garamond italic 500, `--font-cormorant` / `--font-quote`, the `.quote` utility. Only verbatim quotations and the wordmark dot.
No third face. Monospace only for `kbd` hints and IDs.

### Hierarchy
- **Display** (800, clamp(2.5rem…4.6rem), 0.95, −0.04em): the public home headline.
- **Page title** (`.page-title`: 800, clamp(2rem…2.9rem), 1, −0.03em): every H1. Meta goes under it.
- **Lead section** (800, 1.5rem on phones, 1.875rem from `sm`): the one section a page exists for (`Section tone="lead"`, « Ce qui circule ce matin »). At most one per page.
- **Verdict** (800, 1.875-2.25rem, up to 3rem on the Vérifier result).
- **Title** (700, 1.125-1.25rem); **Body** (400, 1rem/1.5); **Label** (600, 0.875rem, sentence case).
- Numbers in tables and scores use tabular figures (`time` and `.tabular`).
- **Bold is for titles.** Refs (FAN-0142), times, units and links in a row's meta are regular or medium; a row has one bold line, its title.

### Named Rules
**The Sentence-Case Rule.** No uppercase tracked eyebrow or kicker above a heading.

**The Quote Rule.** `.quote` is for verbatim words (the verdict quote, a source's phrase, a transcript line), nothing else.

**The Landing Word.** On the public pages and the sign-in doors a big title may set one word in Cormorant italic, as the landing does (`.pub-display`, `.pub-title`, `.pub-h2` with an `<em>`; the word is marked `*like this*` in `lib/i18n/*/look.ts` and drawn by `Em` in `components/site/public/kit.tsx`). One word per title, never on the desk.

## Shapes, depth and motion

- `--radius` is 1.25rem (20 px): cards use `rounded-xl`-scale radii built from it, controls and chips are fully round, menus 18 px, small tags 6 px.
- `--shadow-float` (`0 1px 2px rgba(10,10,11,.10), 0 10px 30px -12px rgba(10,10,11,.30)`) only on what floats; darker in dark.
- Easing: `--ease-out` `cubic-bezier(.22,1,.36,1)` for things that arrive and slide, `--ease-theme` `cubic-bezier(.65,0,.35,1)` for the theme change.
- Motion is single-shot (`.arrive`, `.verdict-land`) except the active step and recording indicator; `prefers-reduced-motion` is honoured.

## Components

- **Buttons:** fully round, 40 px (44 on touch). Primary = ink; secondary = control border; quiet = text. One primary per screen. Hover on ink = slightly lighter ink with the label unchanged.
- **Dropdown** (`components/ui/select.tsx`, `ThemedSelect` from an options list): one for the desk and the public site. A round button on `card` with a control border, the caret right after the label (it turns while open), 48 px on public pages and 40 px (`size="sm"`) in the desk; hover and open = ink border; disabled = `muted-foreground` on `card`. The menu floats (18 px, `--shadow-float`) from the button with 44 px options: highlighted = `raised`, chosen = `active`, bold, with a check. Never a native `<select>`.
- **Verdict chip / badge:** wash + ink, icon + word. AI suggestion = dashed 2 px border in the verdict ink on its wash; signed = solid.
- **Numbered line:** waiting = outlined disc, active = ink disc with a gentle pulse, done = ink disc with a paper check. Suggested = dashed ring, failed = verdict-false ring. In `mini`, only the step that needs someone (active, suggested) has a bold name; a list that already explains the steps passes `labels={false}`.
- **Sections** (`components/rubrique/bits.tsx`): `tone` `lead` (large heading, no rule), `main` (heading on the ink rule, the default) and `aside` (smaller heading on a hairline, for a context column). Separate groups with space (40 px on phones, 56 px from `sm`) before reaching for a rule or a card; one ink rule under the page header, never two in a row.
- **Page frame:** every desk page is `mx-auto max-w-[90rem] px-4 lg:px-8`, so the title stays put across section tabs; a page that reads narrower limits its children (`*:max-w-4xl`), left-aligned, never its frame. A long settings-like page gets a sticky index (Réglages).
- **Highlighter** (`.signal-mark`): a phrase Checky flagged, underlined 2 px in the text colour, 3 px below.
- **Chips and tags:** pale wash + ink of the same hue; `Officielle` / `Public` are inverted ink.
- **Live panel / assistant:** the `live` set (ink in light, raised in dark); the voice toggle and send button invert to `live-foreground` on `live`.
- **Skeletons:** flat bars at final size, no shimmer; content never shifts when data lands.
- **Toast with undo:** ink pill, 6 s bar, « Annuler »; replaces confirmation dialogs for reversible acts.

### Interaction states
Each interactive component lists rest, hover, focus-visible, pressed, selected/current and disabled with both colours. Hover on a light row = `raised` with unchanged text; hover on an ink control = `#1f1f22` with unchanged label; in dark the primary is a paper fill and its hover is `#e2e1da` (`primary-hover`), label still ink; the nav island's hover is `#1f1f22` / dark `#2a2a2e`. Icons inherit `currentColor`. Disabled keeps 4.5:1 (`muted-foreground`, no opacity on text). Focus is a 2 px ring in the text colour with 3 px offset.

## Do's and Don'ts

### Do:
- **Do** build every screen from these tokens: `.page-title` H1 with meta under it, the check field, `StepLine`/`StepDisc`, the verdict components, the live panel.
- **Do** use exactly one primary button per screen.
- **Do** draw an AI suggestion dashed and a journalist's confirmation solid; the final verdict is a journalist's click.
- **Do** pair every verdict with its icon and word, and every status with an ink icon from `lib/icons.ts`.
- **Do** measure a new text pair in light and dark (`lib/tokens.ts`, `npm test`).
- **Do** keep the canvas gutters (inset 24 px + 84 px from 901 px up) so the floating corners (preference dock bottom-left, Checky bottom-right) never cover content; the assistant opens as a panel growing out of the Checky corner.
- **Do** handle real data: long titles wrap, URLs truncate in the middle with the full URL in `title`, a missing value is a grey dash, plurals are French.

### Don't:
- **Don't** add a colour that is not a verdict; no gradient, no accent.
- **Don't** carry a verdict by colour alone, or colour a status with a verdict family.
- **Don't** set a filled background without its own foreground token.
- **Don't** put an uppercase tracked eyebrow above a heading, or coloured border-left accents.
- **Don't** set text in opacity or in the `input` stroke colour.
- **Don't** add ambient shadows to cards; shadows mean "this floats".
- **Don't** set verbatim quotations in the sans, or other text in Cormorant.
- **Don't** bring back the retired worlds (« Le signal clair » citron and chalk, Archivo, Atkinson, « Grille d'antenne », « Le dossier »). The pitch kit (`docs/pitch/`, `scripts/pitch_video.py`) still draws an older world.
