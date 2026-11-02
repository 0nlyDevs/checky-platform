# Checky redesign: web desk and public site — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle `apps/web` (desk + public site) to the Checky identity and give the desk the new shell (tab island, floating corners, sticky columns, palette, undo toasts), with real data and no display bug.

**Architecture:** Keep every CSS variable name in `app/globals.css`; change values, add the paired tokens the spec requires, and retire citron by mapping `--action` to the ink primary. Pure logic (tab folding, sticky offset, contrast, dates, plurals) lives in small `lib/` modules with `node --test` tests; components consume them. Each task below is one branch and one squash-merged PR on `dev`.

**Tech Stack:** Next.js 16.4 (App Router, cacheComponents), Tailwind v4, shadcn/ui, next-themes, `@phosphor-icons/react`, `next/font/google` (Bricolage_Grotesque, Cormorant_Garamond), Node 26 `node --test` (TypeScript type stripping).

**Spec:** `docs/superpowers/specs/2026-11-02-checky-redesign-design.md` (read §4.2–4.6, §4.9, §4.10 and the verification gate before any task). Visual reference: https://claude.ai/artifact/S3XTow6nzQvdSev7FAfDfT.

## Global Constraints

- Token values: exactly the tables in spec §4.2 (light and dark). Nav active pill label is the fixed ink `#0a0a0b` in both themes.
- Every filled background is used with its paired foreground (spec §4.10). No `hover:bg-*` without the matching `hover:text-*` when the fill changes contrast.
- Fonts: Bricolage Grotesque for everything; Cormorant Garamond italic 500 only for verbatim quotes and the wordmark dot. No Archivo, no Atkinson left.
- Icons: Phosphor, `weight="duotone"`, through one map `lib/icons.ts`; no direct `lucide-react` import left after Task 3.
- Product name on screen: « Checky ». Package names, routes, API stay.
- Text ≥ 4.5:1 in both themes; focus ring 2 px `--foreground`, offset 3 px; touch targets ≥ 44 px under 640 px; `prefers-reduced-motion` honoured.
- Next.js 16 rules from `CLAUDE.md` (no `await params` outside Suspense; `useSearchParams` inside Suspense; run `npx next typegen` after route changes).
- Git (user's global rules): branch from up-to-date `dev`; commits `type: message`, no scope, subject only, author Mathieu-bot, no AI attribution; PR title same format; PR body short plain text, no AI footer; `gh pr review --comment -b "looks good to me"` then `gh pr merge --squash --delete-branch` with the squash body = list of squashed commit subjects; then `git switch dev && git pull`.
- Checks before every PR: `cd apps/web && npm test && npx next typegen && npx tsc --noEmit && npx eslint .`; plus the screenshot gate (Task 0 script) with 0 axe contrast violations.

## Review Focus

1. Dark mode on inverted fills: the active nav pill, the primary button, the toast and inverted tags must keep a readable label (the `#f3f2ee` pill with theme text = 1:1). Pinned by `lib/tokens.test.ts` pairs in Task 1 and the dark screenshots of Task 4.
2. Long real data: a 140-character claim title, a 300-character URL, a source with no date, a claim with no verdict. Pinned by the gate script's fixture claim created in Task 0 and inspected in every task.
3. Narrow widths with many tabs: 1100 px and 390 px with `NAV` + future items must fold into « Plus » and keep the active tab reachable. Pinned by `lib/priority-nav.test.ts` in Task 4.
4. Hover on rows and ink controls must not change the label colour to one that fails on the hover fill. Pinned by the `hover` screenshots in the gate and by the paired-token lint grep in Task 1.
5. The assistant moved into the corner keeps every existing behaviour (copilot, voice mode, actions, public guide on the site). Pinned by the manual flow in Task 4 step 6.

---

### Task 0: Verification harness (no app change, no PR)

**Files:**
- Create (outside the repo): `$SCRATCH/gate.py` where `$SCRATCH=/tmp/claude-1000/-home-jiu-ifm-fanilo-mobile/60fd7c3c-663b-485d-b6e9-5bb44b9fb663/scratchpad/web-gate`

- [ ] **Step 1:** Start the stack as in `CLAUDE.md` (API `uv run uvicorn app.main:app --port 8000`, web `npx next dev -p 3000`), sign up a throwaway `*@fanilo.test` user, create a workspace with demo data, and through the API add one fixture claim with a 140-character title and a 300-character source URL and no date.
- [ ] **Step 2:** Write `gate.py` (Playwright with the cached Chromium, `uv run --with playwright --with axe-playwright-python python -I gate.py <path>...`): for each given path, at 1440×900, 1100×800 and 390×844, light and dark (`next-themes` class), save a screenshot, hover the first row, button and tab and save again, run axe with the `color-contrast` rule, and print `path width theme violations`.
- [ ] **Step 3:** Run it on `/w/<ws>/verifier`, `/w/<ws>/affirmations`, one dossier, `/w/<ws>/sources`, `/`, `/verifies`. Expected: it runs; record today's violations as the baseline.

### Task 1: Checky tokens, fonts and design docs

**Files:**
- Create: `apps/web/lib/tokens.ts`, `apps/web/lib/tokens.test.ts`
- Modify: `apps/web/app/globals.css` (`:root` 83–141, `.dark` 142–198, `@theme inline` 10–82, `.signal-mark` rules), `apps/web/app/layout.tsx` (fonts), `apps/web/package.json` (`"test": "node --test lib/*.test.ts"`), `apps/web/DESIGN.md`, `apps/web/PRODUCT.md`, `CLAUDE.md` (working agreements + design system + git rules), `apps/web/.impeccable/design.json` (values only)

**Interfaces:**
- Produces: `export const light: Record<TokenName, string>`, `export const dark: Record<TokenName, string>`, `export const PAIRS: ReadonlyArray<[fg: TokenName, bg: TokenName]>`, `export function contrast(a: string, b: string): number` (WCAG 2.1 ratio, hex `#rrggbb` only; rgba tokens are excluded from `PAIRS`). New CSS variables: `--nav`, `--nav-foreground`, `--nav-hover`, `--nav-active`, `--nav-active-foreground`, `--raised`, `--active`, `--tag-inverted`, `--tag-inverted-foreground`, `--toast`, `--toast-foreground`, `--shadow-float`, `--ease-out: cubic-bezier(.22,1,.36,1)`, `--ease-theme: cubic-bezier(.65,0,.35,1)`; Tailwind colours `nav`, `nav-foreground`, `nav-active`, `nav-active-foreground`, `raised`, `tag-inverted`, `tag-inverted-foreground` via `@theme inline`.

- [ ] **Step 1: Write the failing test** `lib/tokens.test.ts`:
  - `contrast("#0a0a0b", "#f3f2ee")` ≈ 17.67 (±0.05); `contrast("#f3f2ee", "#f3f2ee") === 1`.
  - for theme in `[light, dark]`, for each `[fg, bg]` of `PAIRS`: `contrast(theme[fg], theme[bg]) >= 4.5`. `PAIRS` includes at least: foreground/background, foreground/card, foreground/raised, foreground/active, muted-foreground on background/card/raised/active, primary-foreground/primary, nav-foreground/nav, nav-active-foreground/nav-active, each `verdict-*-ink` on its `verdict-*-soft` and on background/card, tag-inverted-foreground/tag-inverted, toast-foreground/toast.
  - `dark["nav-active-foreground"] === "#0a0a0b"`.
- [ ] **Step 2:** `npm test` → FAIL (module missing).
- [ ] **Step 3:** Implement `lib/tokens.ts` with the spec §4.2 values (verdict `*-soft` = wash, `*-ink` = ink, `verdict-*` fill = ink, `verdict-*-on` = `#ffffff` in light (6.1–6.6:1) and `#0a0a0b` in dark for all four (7.0–11.1:1); add these four pairs to `PAIRS`).
- [ ] **Step 4:** `npm test` → PASS.
- [ ] **Step 5:** Write the same values into `globals.css` `:root` / `.dark`; map `--action: var(--primary)`, `--action-foreground: var(--primary-foreground)`, `--action-ink: var(--foreground)`, `--live*` to ink/raised; `--radius: 1.25rem`; sidebar tokens = nav tokens. `.signal-mark` becomes a hand-drawn-free underline in `--foreground` (2 px, 3 px offset).
- [ ] **Step 6:** Fonts in `layout.tsx`: `Bricolage_Grotesque({ subsets:["latin"], variable:"--font-bricolage", axes:["opsz"] })`, `Cormorant_Garamond({ subsets:["latin"], weight:"500", style:"italic", variable:"--font-cormorant" })`; `--font-sans`, `--font-display`, `--font-heading` → bricolage; new `--font-quote` → cormorant; remove Archivo/Atkinson imports. Add a `.quote` utility (`font-family: var(--font-quote); font-style: italic;`) and apply it to verdict and source quotation elements (`components/claims/verdict.tsx`, `analysis-panel.tsx`, `components/verify/*` quote nodes).
- [ ] **Step 7:** Paired-token lint: `grep -rnE "hover:bg-(primary|foreground|nav)" components app | grep -v "hover:text-"` → no output; fix any hit.
- [ ] **Step 8:** Rewrite `DESIGN.md` (Checky world: spec §4.2–4.6, §4.10 rules), `PRODUCT.md` (name Checky), `CLAUDE.md` sections « Working agreements » (Checky is the product name; git = branch + PR + squash, `type: message` without scope) and « Design system ».
- [ ] **Step 9:** Checks + gate. Expected: tests pass, typecheck/lint clean, axe 0 contrast violations, screenshots show ink/paper, no citron.
- [ ] **Step 10:** Commit on branch `style/checky-tokens` (also add the spec and this plan under `docs/superpowers/` in their own commit `docs: record the checky redesign spec and web plan`): `style: apply checky colour tokens and fonts across the web app` (+ separate commit `docs: describe the checky design system and team git rules`), PR, review comment, squash-merge.

### Task 2: Product name and wordmark

**Files:**
- Modify: `apps/web/components/brand/logo.tsx`, `apps/web/lib/i18n/fr.ts`, `apps/web/app/layout.tsx` (metadata), `apps/web/app/manifest.*` or `public/manifest*`, page `metadata` exports that say FANILO, `components/site/site-chrome.tsx` (footer line « né au hackathon FANILO »)

- [ ] **Step 1:** `grep -rn "FANILO\|Fanilo" apps/web/app apps/web/components apps/web/lib apps/web/public --include=*.ts --include=*.tsx --include=*.json --include=*.webmanifest` → list every user-facing hit.
- [ ] **Step 2:** `logo.tsx` renders « Checky » in Bricolage 800, tracking −0.04 em, plus `<em>.</em>` in `--font-quote`; same props as today.
- [ ] **Step 3:** Replace user-facing strings; keep code identifiers, storage keys (`fanilo:*`), cookies and API names unchanged (renaming them would log users out and lose their tips).
- [ ] **Step 4:** Re-run the grep: only identifiers, keys and the footer origin line remain.
- [ ] **Step 5:** Checks + gate on `/`, `/connexion`, `/w/<ws>/verifier`; PR `feat: rename the product to checky on every web screen`, squash-merge.

### Task 3: Phosphor duotone icons

**Files:**
- Create: `apps/web/lib/icons.ts`
- Modify: every file importing `lucide-react` (32 imports; `grep -rln lucide-react components app lib`), `components/shell/nav.ts` (`icon` type)

**Interfaces:**
- Produces: `export type Icon = React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>` and named exports wrapping Phosphor with `weight="duotone"` (e.g. `export const IconCheck`, `IconX`, `IconWarning`, `IconQuestion`, `IconSealCheck`, `IconFolderOpen`, `IconFileText`, `IconMicrophone`, `IconUsers`, `IconGear`, `IconMagnifyingGlass`, `IconSparkle`, `IconSun`, `IconMoon`, `IconTranslate`, `IconCaretDown`, `IconArrowRight`, `IconCopy`, `IconArrowCounterClockwise`, `IconInfo`, `IconWifiSlash`, `IconLightning`, `IconBell`, `IconDotsThree`, `IconLink`, `IconShieldCheck`, `IconBroadcast`, …). Verdict map: true→Check, false→X, misleading→Warning, unverifiable→Question. Status map: to_check→Question, in_progress→MagnifyingGlass, verified→SealCheck, published→Broadcast.

- [ ] **Step 1:** `npm i @phosphor-icons/react@2.1.10` in `apps/web`.
- [ ] **Step 2:** Implement `lib/icons.ts`; each wrapper passes `className`, `aria-hidden` and `weight="duotone"`; size from `className` (`size-4` etc.) via `size="1em"` + CSS, so existing `size-*` classes keep working.
- [ ] **Step 3:** Replace imports file by file; keep each icon's meaning.
- [ ] **Step 4:** `grep -rn "lucide-react" apps/web/components apps/web/app apps/web/lib` → no output; remove `lucide-react` from `package.json` only if no `components/ui/*` (shadcn) file still needs it, otherwise map those too.
- [ ] **Step 5:** `npm run third-party` at repo root; checks + gate; PR `refactor: switch web icons to phosphor duotone`, squash-merge.

### Task 4: Desk shell — tab island, priority+, corners, assistant from the corner, theme reveal

**Files:**
- Create: `apps/web/lib/priority-nav.ts`, `apps/web/lib/priority-nav.test.ts`, `apps/web/components/shell/tab-island.tsx`, `apps/web/components/shell/preference-dock.tsx`, `apps/web/components/shell/checky-button.tsx`, `apps/web/lib/theme-reveal.ts`
- Modify: `apps/web/components/shell/app-shell.tsx`, `apps/web/components/assistant/assistant-context.tsx`, `apps/web/components/assistant/assistant-widget.tsx`, `apps/web/app/globals.css` (view-transition rules), `apps/web/components/site/site-chrome.tsx` (theme button uses the reveal; public assistant launcher becomes the corner button)

**Interfaces:**
- Produces: `foldTabs(widths: number[], room: number, moreWidth: number, active: number): { visible: number; activeFolded: boolean }` — keeps the first `visible` tabs; folds from the end; never folds index 0; `activeFolded = active >= visible`. `toggleThemeWithReveal(next: "light" | "dark", setTheme: (t: string) => void): void` — View Transition with the diagonal polygon keyframes `POINT → D(0.5) → D(1.2) → D(110)` at offsets `[0, .4, .5, 1]`, 1500 ms, `--ease-theme`, on `::view-transition-new(root)`; plain `setTheme` without the API or under reduced motion; cancels a running transition (`skipTransition`).

- [ ] **Step 1: Write the failing tests** `lib/priority-nav.test.ts`:
  - all fit: `foldTabs([100,100,100], 400, 80, 1)` → `{ visible: 3, activeFolded: false }`
  - fold from the end with « Plus »: `foldTabs([100,100,100,100], 330, 80, 0)` → `{ visible: 2, activeFolded: false }`
  - active folded: `foldTabs([100,100,100,100], 330, 80, 3)` → `{ visible: 2, activeFolded: true }`
  - never below one: `foldTabs([300,300], 100, 80, 1)` → `{ visible: 1, activeFolded: true }`
- [ ] **Step 2:** `npm test` → FAIL. **Step 3:** implement. **Step 4:** `npm test` → PASS.
- [ ] **Step 5:** Build the shell per spec §4.6: top bar (wordmark + workspace switcher left, `TabIsland` centred, search/notifications/avatar right; inset 24 px), `TabIsland` = `NAV` items as links with `aria-current="page"`, a sliding `--nav-active` indicator (transform + width, 500 ms `--ease-out`), measured with a `ResizeObserver` feeding `foldTabs`, « Plus » as a shadcn `DropdownMenu` listing folded items; `WORKSPACE_NAV` moves into the avatar menu. `PreferenceDock` bottom-left (theme now; settings link; language only when translations exist), label flags on hover and `:focus-visible`. `CheckyButton` bottom-right (60 px, label expands left, icon centred in a fixed 60 px box) toggles the assistant, which now renders as a panel growing from that corner (`transform-origin: bottom right`) instead of the docked 25 rem column; remove the page padding the dock used. Canvas gutters `calc(24px + 84px)` from 901 px up; under 900 px the corners overlay and `main` gets `padding-bottom: 112px`. Under 640 px the tab island becomes a fixed ink bottom bar (same items, paper pill on the active one) and the Checky button sits above it.
- [ ] **Step 5b:** Ripple on press for `components/ui/button.tsx`, tabs, dock and Checky button (one `pointerdown` listener in the shell, WAAPI scale 0→1 / opacity .24→0, 650 ms, `currentColor`, skipped under reduced motion). First-visit hand-drawn arrow pointing at the Checky button with « Une question ? Demandez à Checky » in `--font-quote`, shown once (localStorage `checky:hint-seen`), hidden under 900 px, gone on first scroll or first open.
- [ ] **Step 6:** Manual flow, light and dark: open the assistant from the corner on a dossier, ask a question, confirm a proposed action, switch to voice mode and back, close with Escape (focus returns to the button); on `/` the public guide opens from the same corner.
- [ ] **Step 7:** Checks + gate at 1440/1100/390 with hover on tabs, dock and Checky button; dark active-tab label readable. PR `feat: give the desk a tab island with floating corners and a corner assistant`, squash-merge.

### Task 5: Working comfort — sticky columns, palette, shortcuts, undo toasts, live skeletons, dates

**Files:**
- Create: `apps/web/lib/sticky.ts`, `apps/web/lib/sticky.test.ts`, `apps/web/lib/when.ts`, `apps/web/lib/when.test.ts`, `apps/web/components/shell/command-palette.tsx`, `apps/web/components/shell/shortcuts.tsx`
- Modify: `components/verify/verify-view.tsx` (side column sticky, step skeletons), `components/claims/claim-detail.tsx` (side column sticky), `components/claims/verdict-decision.tsx` (confirmation dialog → undo toast where the action is reversible), `components/ui/sonner.tsx` (toast tokens), row components showing dates

**Interfaces:**
- Produces: `stickyTop(offset: number, viewport: number, column: number, margin = 24): number` = `Math.min(offset + 16, viewport - column - margin)`. `relative(iso: string, now: Date): string` (« à l'instant », « il y a 5 min », « il y a 6 h », « hier », « 28/10 », « 14/03/2023 »; Madagascar time UTC+3 as `app/core/dates.py` does) and `exact(iso: string): string` (« 02/11/2026 à 00:41 »). `plural(n: number, one: string, many: string): string` (« 1 source », « 0 source », « 2 sources »).

- [ ] **Step 1: Write the failing tests:** `stickyTop(84, 900, 400) === 100`; `stickyTop(84, 900, 1100) === -224`. `relative("2026-11-02T03:41:00Z", new Date("2026-11-02T09:41:00Z")) === "il y a 6 h"`; `relative` of a date the previous calendar day in UTC+3 → « hier »; `exact("2026-11-01T21:41:00Z") === "02/11/2026 à 00:41"`; `plural(0,"source","sources") === "0 source"`, `plural(2,…) === "2 sources"`.
- [ ] **Step 2–4:** run (FAIL), implement, run (PASS).
- [ ] **Step 5:** Sticky side columns from 1101 px on Vérifier and the dossier page (`position: sticky; align-self: start; top: stickyTop(...)` recomputed on resize and content change via `ResizeObserver`).
- [ ] **Step 6:** `CommandPalette` (`Ctrl/⌘+K`, `/`): groups Espaces (`NAV` + `WORKSPACE_NAV`), Dossiers (searched through the existing `GET …/items?q=`), Actions (Vérifier un contenu, Demander à Checky, Changer de thème, Raccourcis); accent-insensitive filter; arrow keys + Enter; `role="combobox"` + `listbox`; Escape closes and restores focus. `Shortcuts`: `?` help dialog, `V` Vérifier, `G` then `D`/`S`/`E`(Équipe)/`P`(Paramètres), ignored while typing.
- [ ] **Step 7:** Live check: while `link-check` streams, each block not yet arrived shows a flat skeleton at its final size (`bg-raised`, no shimmer), steps waiting/active/done per spec §4.5; no layout shift when results land.
- [ ] **Step 8:** Undo toasts: reversible acts (status change, attaching a source, publishing to the public archive where an unpublish exists) show « Annuler » for 6 s; keep the confirmation dialog only where no undo exists (verdict confirmation per CLAUDE.md « a journalist always confirms »).
- [ ] **Step 9:** Dates via `relative` with `title={exact(...)}` and `<time dateTime>`; counts via `plural`.
- [ ] **Step 10:** Checks + gate; keyboard-only pass of the palette and shortcuts. PR `feat: add sticky side columns, command palette, shortcuts and undo toasts to the desk`, squash-merge.

### Task 6: Final pass

- [ ] **Step 1:** Gate on every desk and public route in both themes at three widths; fix each finding in its own small PR (`fix: …`).
- [ ] **Step 2:** `npm run third-party`; `npm run gen:api` unchanged; PR if `THIRD_PARTY.md` changed: `chore: list the checky redesign dependencies in third party`.
