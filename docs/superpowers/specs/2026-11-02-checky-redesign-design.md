# Checky redesign: web, phone app and extension

Date: 2 Nov 2026. Owner: the team member who does the redesign of all three tools.
Reference mockup: https://claude.ai/artifact/S3XTow6nzQvdSev7FAfDfT (v3). Palette source: `../checky`.

## 1. Intent

The hackathon brief asks for one tool journalists use every day. Today the three clients look like
three products: the web desk and the extension follow « Le signal clair » (chalk, citron, Archivo),
the phone app still follows the older « Grille d'antenne » (signal yellow, manila). The redesign puts
all three in one identity, **Checky**, the name speaker A proposed in the need video, with the
palette, type and tone of the Checky site (`../checky`): a minimal ink-and-paper world where colour
is spent on verdicts only.

The point for the jury is coherence and polish: the same verdict, the same confidence block and the
same gestures on the desk, on the phone and beside a Facebook post.

## 2. Goals, non-goals, anti-goals

Goals
- One token set (colours, type, radius, motion) applied to `fanilo-base/apps/web`, `fanilo-mobile`
  and `fanilo-extension`, in light and dark.
- The product is called **Checky** in every user-facing string, page title, manifest, store name and
  PWA name. Repos, packages, API and database keep their names.
- The web desk gets the new shell from the mockup: ink tab island with priority+ overflow, floating
  corners (preference dock bottom-left, Checky bottom-right), sticky side columns, `Ctrl+K` palette,
  keyboard shortcuts, undo toasts, live-check skeletons.
- The phone app gets the ink bottom bar, the Checky button and the same verdict and step components.
- The extension side panel gets the tokens, fonts, icons and components; its single-column layout stays.

Non-goals
- New brief features (confidence score, directory, figures, monitoring, story angles, keyframes,
  mg/en translations). Those are API and data work done separately. The redesign styles them when
  they exist; it never draws a screen for a feature that does not run (rules art. 2).
- Changing routes, data flow, auth or API calls.
- The pitch deck and demo video (re-shot later on the redesigned app).

Anti-goals (failure even if it "works")
- A mock screen or fake data presented as the app.
- Verdict colours used on chrome, status or decoration; a verdict shown by colour alone.
- Breaking a teammate's in-flight work by mass-rewriting files they are changing.
- Any FANILO organiser logo in the UI (rules art. 6).

## 3. Constraints

- Feature freeze Tue 3 Nov 18:00, code freeze 20:00. The redesign must land in slices that each leave
  the app working and deployable.
- Git: the user's global rules in all three repos. Branch from the default branch, one coherent change
  per commit, `type: message` with no scope, subject only, no AI attribution;
  PR titled the same way; review comment, squash-merge, delete the branch. `fanilo-base`'s default
  branch is `dev`; `fanilo-mobile` and `fanilo-extension` use `main`.
- `fanilo-base/CLAUDE.md` (push to `dev`, `feat(scope):`, "FANILO as the product", citron rules) is
  superseded on these points; the redesign updates it so teammates' agents follow the new rules.
- Next.js 16 rules in `fanilo-base/CLAUDE.md` still apply (cacheComponents, Suspense, `proxy.ts`).
- Expo SDK 58: read the versioned docs before touching an Expo API; `npx expo install` for packages;
  lint + `tsc --noEmit` before done.
- New dependencies go into `THIRD_PARTY.md` (`npm run third-party` in `fanilo-base`), rules art. 6.
- Accessibility floor: text ≥ 4.5:1 in both themes, visible focus, 44 px touch targets, reduced motion.

## 4. Decisions taken with the user

### 4.1 Name
Checky is the product name on screen. Wordmark: « Checky. » in Bricolage Grotesque 800, the dot in
Cormorant Garamond italic. A line « né au hackathon FANILO » may appear in footers and About only.

### 4.2 Tokens
Same token **names** as today in each repo; only values change. Web keeps its shadcn names plus
`--verdict-*`; mobile keeps the keys of `theme.ts`; the extension keeps its CSS variables.

| Role | Light | Dark |
| --- | --- | --- |
| ground (`--background`) | `#f3f2ee` | `#0a0a0b` |
| surface (`--card`, `--popover`) | `#fbfaf7` | `#111113` |
| raised (`--secondary`, `--muted`) | `#e9e8e2` | `#19191c` |
| active / hover fill | `#e2e1da` | `#232327` |
| text (`--foreground`) | `#0a0a0b` | `#f3f2ee` |
| secondary text (`--muted-foreground`) | `#55544e` | `#a6a5a0` |
| border | `rgba(10,10,11,.10)` | `rgba(243,242,238,.10)` |
| rule | `rgba(10,10,11,.07)` | `rgba(243,242,238,.07)` |
| control border (`--input`) | `rgba(10,10,11,.24)` | `rgba(243,242,238,.26)` |
| primary (one action) | `#0a0a0b` on `#f3f2ee` text | `#f3f2ee` on `#0a0a0b` text |
| nav island | `#0a0a0b`, text `#b9b8b2`, active pill `#f3f2ee` | `#1c1c1f`, text `#b4b3ad`, active pill `#f3f2ee` |

Verdicts (word/icon ink, soft wash; the Checky brand tone is the dot/fill):

| Verdict | Ink light | Wash light | Ink dark | Wash dark | Brand tone |
| --- | --- | --- | --- | --- | --- |
| vrai (`true`) | `#0b6b3a` | `#e1f3e8` | `#3ddc84` | `#0f2219` | `#3ddc84` |
| faux (`false`) | `#b3231a` | `#fbe3e0` | `#ff6a5f` | `#2a1311` | `#ff4a3d` |
| trompeur (`misleading`) | `#8a5700` | `#f9ecd2` | `#ffb224` | `#29200c` | `#ffb224` |
| invérifiable (`unverifiable`) | `#1d58c4` | `#e0eafb` | `#6aa8ff` | `#101a2b` | `#3b8cff` |

The citron `--action` and the `--live` set disappear as colours: the one action per screen is the
ink primary; "live" and the active step use ink plus motion. Where code references `--action`,
it maps to `--primary`.

Radius: cards 20, controls and chips fully round (999), menus 18, small tags 6. Shadows only on what
floats (menus, dialogs, corners, toasts): light `0 1px 2px rgba(10,10,11,.10), 0 10px 30px -12px rgba(10,10,11,.30)`.

### 4.3 Type
- Bricolage Grotesque (variable, opsz 12–96, 400–800): everything, titles at 700–800 with −0.02 to
  −0.04 em tracking. Tabular figures on every number in tables and scores.
- Cormorant Garamond italic 500: only verbatim quotations (the verdict quote, source quotes) and the
  wordmark dot.
- No third face. Monospace only for `kbd` hints and IDs if needed.
- Web: `next/font/google` (Bricolage_Grotesque, Cormorant_Garamond) replaces Archivo/Atkinson.
  Mobile: `@expo-google-fonts/bricolage-grotesque` and `@expo-google-fonts/cormorant-garamond`
  replace Anton, Barlow Condensed and Public Sans. Extension: `@fontsource-variable/bricolage-grotesque`
  and `@fontsource/cormorant-garamond` bundled locally (no font network calls, as today).

### 4.4 Icons
Phosphor, duotone weight (MIT): `@phosphor-icons/react` on the web, `phosphor-react-native` on the
phone (check SDK 58 compatibility with `npx expo install`; it needs `react-native-svg`, already
present), inline SVG symbols from the same set in the extension. They replace lucide one file at a
time; one icon map per repo keeps names consistent (verdicts: Check / X / Warning / Question;
statuses: Question / MagnifyingGlass / SealCheck / Broadcast).

### 4.5 Components (all three repos)
- Verdict: icon + word, never colour alone. AI suggestion = dashed 2 px border in the verdict ink on
  its wash, label « Lecture de Checky, à signer par un journaliste »; signed = solid border, label
  « Signé par <name> à <time> ».
- Steps: the numbered line 1 L'affirmation · 2 Les éléments · 3 La conclusion, states waiting
  (outlined disc), active (ink disc, gentle pulse), done (ink disc).
- Buttons: fully round, 40 px (44 on touch). Primary = ink. Secondary = control border. Quiet = text.
  Ripple on press (web and extension); pressed scale .97 on the phone.
- Chips and tags: pale wash + ink of the same hue; `Officielle` / `Public` tags are inverted ink.
- Skeletons: flat bars at the final size, no shimmer gradient; content never shifts when data lands.
- Toast with undo: ink pill, 6 s bar, « Annuler »; replaces confirmation dialogs for reversible acts.
- Hand-drawn marks (SVG strokes that draw in once): only (a) the first-visit arrow to Checky,
  (b) the underline under a screen's key figure, (c) the circle around an official figure.

### 4.6 Web desk shell (from the mockup)
- Top bar: wordmark + workspace left; ink tab island centred with a sliding paper indicator
  (0.5 s, ease `cubic-bezier(.22,1,.36,1)`); search (`Ctrl+K`), notifications, avatar right.
  Inset 24 px. Priority+: tabs that do not fit fold into « Plus » from the end; an active tab that is
  folded gives « Plus » its name and the indicator.
- Corners, aligned on the bar's inset: bottom-left preference dock (language, theme, settings; label
  flags slide out on hover and focus); bottom-right the Checky button (60 px, label expands to the
  left), which opens the existing assistant as a panel growing out of the corner. This replaces the
  docked 25 rem assistant panel; its behaviour (copilot, voice, actions) is unchanged.
- Canvas gutters of inset + 84 px so the corners never cover content; below 900 px the corners
  overlay and the page gets bottom padding.
- Sticky side columns on screens with two columns: top-stick when they fit, bottom-stick when taller
  than the viewport.
- Theme switch: View Transition; a diagonal slit through the centre draws across, holds, then opens to
  full screen; 1.5 s, `cubic-bezier(.65,0,.35,1)`; instant under reduced motion or without the API.
- `Ctrl+K` palette (spaces, dossiers, actions), shortcuts (`?`, `V`, `S`, `G` then a letter),
  per-tab scroll memory, relative dates with the exact one in `title`.
- The public site (`app/(site)/`) takes the tokens, fonts, icons and components, and keeps its layout.

### 4.7 Phone app
- `(tabs)` bar becomes the ink bar with a paper pill on the active tab (4 tabs + « Plus » sheet when
  there are more than five destinations).
- The Checky button floats above the bar at the right and opens the assistant/check flow.
- On a check result, « Signer et publier » sits in a fixed bar above the tab bar.
- Dark mode follows the system, with the same tokens.

### 4.8 Extension
Single reading column (360–480 px) stays. Tokens, fonts, icons, verdict and step components change;
the one action per screen becomes the ink primary instead of citron.

### 4.9 Real data, not the mockup's placeholders

The mockup's content is placeholder. Every component is laid out for the data the app has today
and for its extremes:

- **Destinations are the existing routes**, not the mockup's list. Desk tabs come from
  `components/shell/nav.ts`: `NAV` = Vérifier, Dossiers, Sources in the tab island; `WORKSPACE_NAV`
  = Équipe, Paramètres go to the avatar menu (they are the newsroom's pages, not daily work), and
  settings also sits in the bottom-left dock. Ma rubrique, Veille, Annuaire and Chiffres join `NAV`
  only when their features run; priority+ then handles the extra width.
- **Long text**: claim titles wrap (max 3 lines in lists, full on the dossier); row titles clamp to
  2 lines; URLs truncate in the middle with the full URL in `title`; names and tags never wrap
  (`nowrap`, `flex: none`), the text beside them shrinks (`min-width: 0`).
- **Counts**: real French plurals (1 source, 2 sources); lists cap at 5 rows with « Voir les N »;
  counts follow the current filter.
- **Missing values**: a grey dash, never « undefined », « null », « NaN » or an empty badge. A real zero
  is printed. No verdict yet = no verdict block, the step line says where the dossier stands.
- **Source kinds** differ: text, link, image, video, audio, PDF. Image-only blocks (EXIF, AI traces,
  reverse search) and video-only blocks (transcript, frames when they exist) render only for that kind.
- **States per block**: loading (skeleton at final size), empty (one sentence in the frame + the next
  action), error (one sentence, last good time, « Réessayer »), offline (cached data + notice).
- **Dates** come from the API in ISO; shown relative (« il y a 6 h ») with the exact date in `title`.

### 4.10 Colour pairs and interaction states (no invisible text)

Measured: every text/background pair below is ≥ 4.5:1 in both themes, **except one trap**: in dark,
the active nav pill is paper (`#f3f2ee`), so its label must be the fixed ink `#0a0a0b`, never the
theme's text colour (1:1, invisible). Rules that prevent this class of bug everywhere:

- **Every filled background has its own foreground token**, used together, in both themes:
  `primary / primary-foreground`, `nav / nav-foreground`, `nav-active / nav-active-foreground`
  (ink in both themes), `verdict-*-soft / verdict-*-ink`, `tag-inverted / tag-inverted-foreground`,
  `toast / toast-foreground`. A class that sets one without the other is a bug (e.g. `hover:bg-primary`
  without `hover:text-primary-foreground`).
- **Each interactive component lists its states with both colours**: rest, hover, focus-visible,
  pressed, selected/current, disabled. Hover on a light row = `raised` bg with unchanged `text`;
  hover on an ink control = slightly lighter ink `#1f1f22` with unchanged label; in dark the primary
  is a paper fill, so its hover is a slightly darker paper `#e2e1da` (`--primary-hover`), label still ink;
  the nav island's own hover stays `#1f1f22` / dark `#2a2a2e`.
- **Icons inherit `currentColor`** (Phosphor duotone included: its 20 % layer follows the label), so a
  state that changes the label changes the icon.
- **Disabled** keeps 4.5:1 on its text (uses `muted-foreground`, no opacity on text).
- **Focus** is a 2 px ring in `text` colour with 3 px offset, visible on every fill.

## 5. Order of work (each slice is one PR, app working after each)

1. `fanilo-base` web: tokens + fonts + `DESIGN.md`/`PRODUCT.md`/`CLAUDE.md` rewritten to Checky.
2. `fanilo-base` web: product name strings to Checky (UI, metadata, manifest).
3. `fanilo-base` web: icons lucide → Phosphor duotone.
4. `fanilo-base` web: new shell (tab island, priority+, corners, assistant from the corner, theme reveal).
5. `fanilo-base` web: sticky columns, palette, shortcuts, undo toast, skeletons, scroll memory.
6. `fanilo-mobile`: tokens + fonts + name; then icons; then tab bar + Checky button + sign bar.
7. `fanilo-extension`: tokens + fonts + name + icons + components.
8. `THIRD_PARTY.md` regenerated.

Slices 6 and 7 do not depend on 4 and 5 and can run in parallel.

### Verification gate for every slice

Before a PR: the repo's own checks (web: `ruff`/`pytest` untouched, `next typegen`, `tsc --noEmit`,
`eslint`; mobile: `npx expo lint`, `npx tsc --noEmit`; extension: its `npm test`/build). Then, on the
real app with real data (demo reset seeds 8 claims and 7 sources): screenshots in light and dark at
1440, 1100 and 390 px of every changed screen; hover, focus and selected states of every changed
control; an axe contrast pass with no violations. A slice with a visible display bug does not merge.

## 6. Left to the builder

- Exact component file splits, class names and Tailwind utilities.
- Which existing screens get sticky columns beyond Vérifier, a dossier and the home.
- How the priority+ measurement is wired in React (ResizeObserver or equivalent).
- Copy for new microcopy (toasts, empty states), in the voice of the mockup: short, French, concrete.

## 7. Calls made without the user (check while reading)

- Token names stay; only values change (cheapest, least conflict with teammates).
- Citron `--action` is retired; `--action` maps to the ink primary until references are cleaned.
- Phosphor replaces lucide everywhere, not only in the desk shell.
- The public site keeps its layout and only changes its look.
- The wordmark dot in Cormorant; « né au hackathon FANILO » allowed in footers only.
- The language button in the dock is left out until mg/en translations run; a control that does
  nothing would break rules art. 2. It appears in the same slot when slice "mg/en" ships.
- On the phone, the Checky button opens a new check (the Analyser flow), since the app has no
  docked copilot; the phone's « Vérifier » tab (ask the sources) keeps its place in the tab bar.
- The phone keeps its current four tabs, so no « Plus » sheet is needed there yet.
