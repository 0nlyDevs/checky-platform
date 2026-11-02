---
name: FANILO
description: Fact-checking desk for Malagasy newsrooms, set as a radio programme grid.
colors:
  antenna-green: "#0f3b36"
  antenna-green-on: "#ffffff"
  signal-yellow: "#f2c230"
  signal-ink: "#7a5900"
  cool-white-ground: "#f4f6f5"
  card-white: "#ffffff"
  green-black-ink: "#14201d"
  muted-ink: "#4b5a56"
  hairline-rule: "#c9d3d0"
  input-stroke: "#b4c0bc"
  muted-ground: "#e9eeec"
  secondary-ground: "#e4eae8"
  accent-ground: "#e2ebe8"
  destructive: "#b8352b"
  rail-foreground: "#e9f1ef"
  rail-muted: "#a9c2bd"
  rail-accent: "#1a4d47"
  rail-border: "#24564f"
  verdict-true: "#267a42"
  verdict-true-on: "#ffffff"
  verdict-true-soft: "#e2f1e6"
  verdict-true-ink: "#1f6b38"
  verdict-misleading: "#c98a12"
  verdict-misleading-on: "#14201d"
  verdict-misleading-soft: "#f8ecd2"
  verdict-misleading-ink: "#7d5300"
  verdict-false: "#c43d32"
  verdict-false-on: "#ffffff"
  verdict-false-soft: "#f8e1de"
  verdict-false-ink: "#9c2b22"
  verdict-unverifiable: "#66716c"
  verdict-unverifiable-on: "#ffffff"
  verdict-unverifiable-soft: "#e7ebe9"
  verdict-unverifiable-ink: "#4f5a56"
  dossier-manila: "#dcc9a3"
  dossier-manila-deep: "#cfb98f"
  dossier-index: "#efe4c8"
  dossier-index-hover: "#f6eedb"
  dossier-paper: "#fffdf7"
  dossier-photo-white: "#ffffff"
  dossier-ink: "#141210"
  dossier-ink-night: "#0e0d0b"
  dossier-ink-soft: "#4a4033"
  dossier-ink-label: "#c9b993"
  dossier-alarm: "#c42a20"
  dossier-alarm-ink: "#a3231b"
  dossier-paperclip: "#8b8f95"
  piece-whatsapp-ground: "#e7f6d8"
  piece-whatsapp-meta: "#4f5b52"
  piece-facebook-name: "#1b4a9b"
  piece-voice-wave: "#2a7d4f"
typography:
  headline:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    fontFeature: "ss01"
  body-table:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
  meta:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
  grid-title:
    fontFamily: "Barlow Condensed, Public Sans, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    letterSpacing: "0.025em"
  ref:
    fontFamily: "Barlow Condensed, Public Sans, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    letterSpacing: "0.025em"
    fontFeature: "tnum"
  time:
    fontFamily: "Barlow Condensed, Public Sans, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    letterSpacing: "0.025em"
    fontFeature: "tnum"
  now-tag:
    fontFamily: "Barlow Condensed, Public Sans, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.05em"
    fontFeature: "tnum"
  wordmark:
    fontFamily: "Barlow Condensed, Public Sans, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    letterSpacing: "0.025em"
  dossier-display:
    fontFamily: "Anton, Arial Narrow, sans-serif"
    fontSize: "clamp(44px, 5.6vw, 92px)"
    fontWeight: 400
    lineHeight: 0.9
  dossier-tab:
    fontFamily: "Anton, Arial Narrow, sans-serif"
    fontSize: "21px"
    fontWeight: 400
    letterSpacing: "0.06em"
  dossier-label:
    fontFamily: "Special Elite, Courier New, serif"
    fontSize: "14px"
    fontWeight: 400
  dossier-lead:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 400
    lineHeight: 1.5
  dossier-body:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
rounded:
  block: "3px"
  sm: "3px"
  md: "4px"
  lg: "5px"
  full: "9999px"
  assistant-control: "6px"
  assistant-field: "8px"
  assistant-panel: "10px"
spacing:
  lane-gap: "6px"
  cell-y: "10px"
  gutter: "16px"
  section: "20px"
  page-desktop: "32px"
components:
  button-primary:
    backgroundColor: "{colors.antenna-green}"
    textColor: "{colors.antenna-green-on}"
    rounded: "{rounded.lg}"
    padding: "0 10px"
    height: "40px"
  button-outline:
    backgroundColor: "{colors.cool-white-ground}"
    textColor: "{colors.green-black-ink}"
    rounded: "{rounded.lg}"
    padding: "0 10px"
    height: "32px"
  input:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.green-black-ink}"
    rounded: "{rounded.lg}"
    padding: "4px 10px"
    height: "40px"
  verdict-badge:
    backgroundColor: "{colors.verdict-false-soft}"
    textColor: "{colors.verdict-false-ink}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  verdict-badge-suggested:
    textColor: "{colors.verdict-misleading-ink}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  grid-block-confirmed:
    backgroundColor: "{colors.verdict-true}"
    textColor: "{colors.verdict-true-on}"
    rounded: "{rounded.block}"
    height: "32px"
  grid-block-suggested:
    backgroundColor: "{colors.verdict-misleading-soft}"
    textColor: "{colors.verdict-misleading-ink}"
    rounded: "{rounded.block}"
    height: "32px"
  grid-block-unchecked:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.green-black-ink}"
    rounded: "{rounded.block}"
    height: "32px"
  now-tag:
    backgroundColor: "{colors.signal-yellow}"
    textColor: "{colors.green-black-ink}"
    typography: "{typography.now-tag}"
    rounded: "{rounded.sm}"
    padding: "2px 6px"
  nav-rail:
    backgroundColor: "{colors.antenna-green}"
    textColor: "{colors.rail-foreground}"
    width: "248px"
  nav-rail-item-active:
    backgroundColor: "{colors.rail-accent}"
    textColor: "{colors.antenna-green-on}"
    rounded: "{rounded.md}"
    padding: "8px 10px"
---

# Design System: FANILO

## Overview

**Creative North Star: "Grille d'antenne"**

The day's claims are set like a Malagasy radio station's programme grid. Every claim has airtime: a block drawn to scale from the moment it was first seen to "maintenant", on hairline hour rules from 06h to 22h. Time is the organising material; the station's deep antenna green frames the desk, and a single signal yellow marks the present moment.

The density is that of a broadcast schedule: tight 32px lanes, 6px between them, hairline rules rather than boxes, condensed numerals that line up in columns. Colour is reserved for meaning. Verdicts own four hues, status owns none, and the yellow belongs to "now". Surfaces are flat; depth appears only when the journalist focuses a block, which lifts while the rest of the grid dims.

The world explicitly refuses the default dashboard: a grey table with coloured pills and nothing about time. The table still exists, but as the programme listing under the grid, carrying the same rows.

**Key Characteristics:**
- Time drawn to scale: block length is exact circulation time.
- Antenna-green rail, cool white ground, green-black ink, hairline hour rules.
- One signal yellow, for the present moment and the keyboard's position.
- Verdicts always icon plus label; status in ink only.
- Condensed grotesk for every hour, time and FAN reference; a workhorse sans for words.
- Flat at rest; focus lifts.

## Colors

A cool green-neutral system with one warm signal and a fixed four-colour verdict scale; every colour token has a light and a dark value (dark values in the sidecar).

### Primary
- **Antenna Green** (`antenna-green`): the rail, the mobile top bar and bottom nav, the primary button, the logo tile, the light-mode focus ring and text caret. It is the station's frame, never a status.

### Secondary
- **Signal Yellow** (`signal-yellow`): the "maintenant" line and its time tag, the focus ring on grid blocks and in the rail, the keyboard ring in dark mode, text selection, and the faint tint (15%) on the selected table row. **Signal Ink** (`signal-ink`) is its text-safe partner on light grounds.

### Tertiary: the verdict scale
Four verdicts, each a family of four tokens: **fill** (grid block), **on** (text and icon on the fill), **soft** (badge and notice ground), **ink** (text on light grounds).
- **Vrai** (`verdict-true` family): confirmed true.
- **Trompeur** (`verdict-misleading` family): misleading. Its fill carries dark text; the offline notice also borrows its soft/ink pair.
- **Faux** (`verdict-false` family): false. Form errors borrow its soft/ink pair.
- **Invérifiable** (`verdict-unverifiable` family): unverifiable; a green-grey kept distinct from muted UI ink.

### Neutral
- **Cool White Ground** (`cool-white-ground`): page background.
- **Card White** (`card-white`): grid panel, table, inputs and filters, unchecked blocks.
- **Green-Black Ink** (`green-black-ink`): body text; also the fixed text colour on signal yellow in both themes.
- **Muted Ink** (`muted-ink`): metadata, hour labels, durations, table headers.
- **Hairline Rule** (`hairline-rule`): hour rules and all borders.
- **Input Stroke** (`input-stroke`): field outlines and scrollbar thumb.
- **Muted Ground** (`muted-ground`): the not-yet-aired remainder of the day (at 60%), skeletons.
- **Rail tones** (`rail-foreground`, `rail-muted`, `rail-accent`, `rail-border`): text, secondary text, active item and hover, divider on the antenna-green rail.

### Named Rules
**The One Signal Rule.** Signal yellow means "now" or "you are here": the maintenant line, focus, selection. It never decorates, never fills a button, never marks a verdict or status.

**The Four-Token Verdict Rule.** Every verdict colour ships as fill / on / soft / ink, and text on a fill always uses its own "on" token, so every pairing holds at least 4.5:1 in both themes. A new verdict surface picks from these four; it does not invent a fifth tint.

**The Status Is Not Truth Rule.** Workflow status (À vérifier, En cours, Vérifié, Publié) is drawn with ink icons only (CircleDashed muted, Timer, ShieldCheck, Radio in foreground). Status never borrows a verdict colour.

## Typography

**Display Font:** Barlow Condensed 500/600 (fallback Public Sans), loaded via next/font as `--font-display`.
**Body Font:** Public Sans (fallback ui-sans-serif, system-ui), with stylistic set `ss01` on.

**Character:** Barlow Condensed is the programme-grid voice, the face on a station schedule board: narrow, upright, numerals that stack. Public Sans is the plain civic workhorse for everything a journalist reads as language.

### Hierarchy
- **Headline** (Public Sans 600, 1.75rem, tight leading and tracking): the page title ("Affirmations").
- **Title** (Public Sans 600, 1.5rem): auth and onboarding titles; sheet titles step down to 1.125rem.
- **Body** (Public Sans 400, 1rem): claim titles (500 weight), form text, leads.
- **Body-table** (Public Sans 400, 0.9375rem): the programme listing and rail items.
- **Meta** (Public Sans 400, 0.875rem): origin and tags, legend, status labels, verdict badges, hints.
- **Grid title** (Barlow Condensed 600, 1rem, uppercase, 0.025em): the grid's heading ("Circulation du jour"), the only uppercase heading in the system.
- **Ref** (Barlow Condensed 600, 1rem, 0.025em, tabular): FAN references in the table, blocks and tooltip.
- **Time** (Barlow Condensed 500, 0.875–1rem, 0.025em, tabular): hour ruler, seen-at times, durations.
- **Now tag** (Barlow Condensed 600, 0.75rem, uppercase, 0.05em): "MAINTENANT 18:43" on signal yellow.
- **Wordmark** (Barlow Condensed 600, 1.25rem, 0.025em): the product name beside the logo mark.

### Named Rules
**The Airtime Face Rule.** Hours, times, durations, counts in the grid and FAN references are set in Barlow Condensed with tabular numerals; so are the wordmark, the grid title and avatar initials. Everything else, including headings, is Public Sans.

**The Tabular Rule.** Every `time` element and every number that sits in a column uses tabular figures so values align down the listing.

## Layout

Desktop (lg, 1024px and up): a fixed 248px antenna-green rail on the left, the workspace in a container up to 90rem with 32px side padding. Page header (title, date line, primary action) sits 32px from the top; filters below (search grows, two 176px selects); then the day grid and the claims table stacked 20px apart.

The day grid spans 06h to 22h (extending if now falls outside), one 32px lane per claim sorted by first seen, 6px between lanes, hairline hour rules running the full height, and the not-yet-aired remainder shaded in muted ground. Durations sit just right of the "maintenant" line.

Tablet (md, 768px): the table stays tabular; the rail gives way to a top bar and bottom nav below lg.

Phone (from 360px): a sticky antenna-green top bar (wordmark, workspace switcher, avatar), a fixed four-item bottom nav respecting the safe-area inset, edge-to-edge grid and list with 16px gutters. The grid becomes a horizontally scrolled six-hour window that opens on "maintenant"; block labels stay pinned in view as it scrolls. The table becomes stacked rows: ref and time on one baseline, title, then status, verdict and sources.

Sign-in splits the screen on desktop: the rail colour carries a quiet, aria-hidden miniature of the grid on the left, the form (max 24rem) on the right.

## Elevation & Depth

Flat by default. Depth comes from tone (antenna-green rail against cool white, card white on the ground, muted ground for the future part of the day) and from hairline rules. Shadows appear only as a response to focus.

### Shadow Vocabulary
- **Block lift** (`box-shadow: 0 6px 16px -6px rgb(15 59 54 / 0.45)`, with a 1px upward shift and a signal ring): the focused grid block.
- **Tooltip** (`box-shadow: 0 10px 28px -10px rgb(15 59 54 / 0.4)`): the block's detail card.

### Named Rules
**The Spotlight Rule.** Focusing a block (hover, keyboard, or a hovered table row) lifts it and dims every other lane to 40% opacity; Escape or leaving releases it. Nothing else in the system casts a shadow at rest.

## Shapes

Square-ish and tight. The base radius is 5px (`--radius: 0.3125rem`), with a derived 4px and 3px; grid blocks and verdict badges use 3px, legend swatches 2px. A block that started before the grid's first hour loses its left corners and carries a chevron with its real start time, so length stays honest. Only avatars are round. Borders are 1px hairlines; dashed strokes are reserved for AI suggestions and empty states.

## Components

### Buttons
Calm and solid, sized for the field.
- **Shape:** gently squared (5px).
- **Primary:** antenna green with white text; hover drops to 80% opacity; pressed shifts down 1px. Primary actions in the app use the 40–44px height overrides, not the 32px default.
- **Focus:** ring colour at 50% with a 3px ring, plus the global 2px outline offset 2px.
- **Outline:** ground-coloured with a hairline border; hover to muted ground. Used for retry and clear filters.

### Chips: verdict badge
- **Confirmed:** soft verdict ground, verdict ink text, icon (CircleCheck, TriangleAlert, CircleX, CircleHelp) plus label, 3px radius.
- **AI suggestion:** transparent ground, 1px dashed outline in the verdict ink, icon plus label plus "· suggéré".
- **None:** plain muted text "Sans verdict".

### Cards / Containers
- **Corner Style:** 5px on desktop; grid and list go edge-to-edge (top and bottom borders only) on phones.
- **Background:** card white on the cool ground.
- **Shadow Strategy:** none at rest (see Elevation).
- **Border:** 1px hairline.
- **Internal Padding:** 16px on phones, 20px on desktop for the grid; table cells 16px by 10px.

### Inputs / Fields
- **Style:** 1px input-stroke outline, card-white ground in the filter bar, 5px radius, 40–44px tall in use.
- **Focus:** border turns to the ring colour with a soft ring.
- **Error:** an inline alert on the false soft/ink pair, never red text alone.

### Navigation
- **Rail:** antenna green, 15px items with 18px lucide icons, 4px radius; active item on the rail accent with white text and medium weight; hover at 60% of the accent; unbuilt items in rail-muted at 70% with a small "Bientôt" tag. Workspace switcher and user menu sit in the rail.
- **Bottom bar (phones):** four items, icon over 12px label; active shown by a 2px inset top bar in rail foreground.

### Day grid (signature)
The programme grid of the day. Hour ruler in the condensed face; hairline rules; one lane per claim; block from first seen to now.
- **Confirmed verdict:** solid verdict fill, "on" text, icon + ref + title.
- **AI suggestion:** dashed outline in verdict ink on the verdict soft ground.
- **Unchecked:** solid outline (foreground at 60%) on card white.
- **Maintenant:** a 2px signal-yellow line through the full height, topped by the now tag.
- **Legend:** confirmed is a neutral ink swatch (foreground at 70%), since confirmation is a state shared by all four verdict hues; suggestion and unchecked swatches mirror their block treatments.
- **Motion:** each block grows from its first-seen point toward now on load (`grid-extend`, 640ms, expo-out, 35ms stagger); the grid ticks every 30s. Reduced motion collapses all animation.

## Public pages: "Le dossier"

The landing, sign-in, sign-up and the public pages (`/verifies`, `/signaler`, `/suivi`) live in a second world: **the case file**. A rumour is treated as an affair under investigation: manila folders, index cards, typed labels, photographs pinned as pieces, and a red stamp that lands once. Contract: `.impeccable/surfaces/app-site-accueil-page-tsx.md`. CSS under `.site` and `.dossier-*` / `.pub-*` in `app/globals.css`, tokens `--site-*`.

### Colors
- **Manila** (`dossier-manila`, deeper `dossier-manila-deep`): the ground. **Index card** (`dossier-index`, hover `dossier-index-hover`): cards, files, the case card. **Paper** (`dossier-paper`): inputs on the card. Pieces sit on **photo white**.
- **Ink** (`dossier-ink`; `dossier-ink-night` for the dark theme colour): text, folder tabs, the footer and the answer block. **Soft ink** (`dossier-ink-soft`): typed labels and secondary text on manila. **Label on ink** (`dossier-ink-label`): typed text on ink grounds.
- **Alarm** (`dossier-alarm`): stamps, the current step, piece numbers. **Alarm ink** (`dossier-alarm-ink`): red text (the desk's notes), focus outline and hover of tabs.
- Piece colours (`piece-*`) belong only to the fake WhatsApp, Facebook and voice-note fragments of the affair: they imitate the platforms, never the product.
- Published verdict stamps reuse the desk's verdict **ink** tokens, so a verdict reads the same on both sides.

### Typography
- **Anton** (`--font-anton`): headlines, folder tabs, divider tabs, stamps, uppercase only (`dossier-display`, `dossier-tab`).
- **Special Elite** (`--font-typed`): the file's labels only (`dossier-label`): dates, refs, captions, field names. Never a sentence a visitor must read.
- **Public Sans**: everything a visitor reads (`dossier-lead`, `dossier-body`).

### Components
- **Folder tab** (`.tab-btn`): the one action shape; ink tab, manila text, lifts 3px and turns alarm ink on hover.
- **Stamp** (`.stamp`, text from `data-label`): lands once at an angle (scale 1.5 → 1, 280ms expo-out), then stays at 85%.
- **Index card / file** (`.dossier-fiche`, `.pub-file`): square corners, a 2px ink rule under the typed header.

### Shared with the desk
The app shell borrows the ink rail, the manila marker, Anton page titles (`.page-title`) and the folder logo. The floating assistant is the only component drawn in both worlds: an ink button (manila on the dark desk), an ink header, a body in the desk's own card colours, and rounder corners (6 / 8 / 10px) than the desk's 5px, as it floats above either world.

### Named Rules
**The One Red Rule.** Alarm red is the stamp's colour. It marks a verdict landing, the current step and the desk's notes; it never fills a button at rest.

**The Typed Label Rule.** The typewriter face labels the file; it never carries content.

## Do's and Don'ts

### Do:
- **Do** pair every verdict with its icon and French label, in badges, blocks, tooltips and filter menus.
- **Do** put text on a verdict fill only in that verdict's "on" token, and on light grounds only in its "ink" token.
- **Do** set hours, times, durations and FAN references in Barlow Condensed with tabular figures.
- **Do** draw an AI suggestion as a dashed outline on soft ground, and an unchecked claim as a plain outline on card white.
- **Do** keep every UI string in `lib/i18n/fr.ts` and the product name and logo in `lib/brand.ts` / the brand component.
- **Do** keep corners at 5px or tighter (3px for blocks and badges).

### Don't:
- **Don't** use signal yellow for anything but now, focus and selection.
- **Don't** colour a status with a verdict hue; status is ink icons only.
- **Don't** show a verdict by colour alone on a functional surface.
- **Don't** add shadows to surfaces at rest; depth is for the focused block and its tooltip.
- **Don't** fall back to a time-blind grey table with coloured pills as the main view of claims.
