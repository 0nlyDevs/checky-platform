---
version: 1
slug: "app-app"
primary_target: "app/(app)"
related_targets: ["app/(auth)"]
---

# Surface: app shell and claims workspace

Scope: authenticated app shell (nav rail, workspace switcher, mobile bottom nav), sign-in and sign-up, and the claims list ("Affirmations"). Mode: Operate.
Audience and job: journalists and desk editors triaging the day's claims, on a phone in the field or a laptop at the desk. Task: see what is circulating, what is checked, and open one to work on it.
Constraints: French UI; verdict never shown by colour alone; 360 px minimum width; light and dark; live updates over Socket.IO.

## Direction contract

THESIS: The day's claims set like a radio station's programme grid: each claim has its airtime, a block from first seen to now, drawn to scale. It refuses the default dashboard of a grey table with coloured pills and nothing about time.

OWN-WORLD: Deep antenna green rail (#0f3b36) with white type; cool white ground (#f4f6f5), green-black ink (#14201d), hairline hour rules (#c9d3d0); one signal yellow (#f2c230) reserved for "maintenant" and focus. Verdicts green #2f8f4e, amber #c98a12, red #c43d32, grey #7a8580, always with icon and label. Condensed grotesk for hours, times and FAN refs; workhorse sans for everything else. Dense programme-grid rhythm, square-ish 4 px corners.

STORY: The journalist sees at once what has been circulating longest unchecked, what was settled, and what just arrived live; opens one claim; the desk shares one picture of the day.

FIRST VIEWPORT: Desktop: green rail left (wordmark, workspace switcher, nav). Main: header "Affirmations" with date, filters and the primary "Nouvelle affirmation". Then the day grid: hour ruler 06h to 22h, one lane per claim, block from first-seen to now tinted by verdict (unchecked = outlined), yellow "maintenant" line. Below, the claims table with the same rows. Mobile: grid collapses to a 6-hour window scrolled to now, table becomes stacked rows, bottom nav replaces the rail.

FORM: Grille d'antenne, position 6 of 7 on the ordered list (front page, banknote security print, lamba hoany, fokontany register, taxi-brousse livery, radio programme grid, Antemoro paper). seed:a7010e8bb9ebe340. Raises: stable FAN-0142 references in the time face (from catalog sleeve); block length is exact circulation time (from dance score); focusing a block lifts it and dims the rest (from title-card wall).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

- Claims need a first-seen time (`data.first_seen_at`); without one they sit in the table only.
- Malagasy UI strings later.
