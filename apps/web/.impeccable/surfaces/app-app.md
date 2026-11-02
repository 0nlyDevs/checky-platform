---
version: 1
slug: "app-app"
primary_target: "app/(app)"
related_targets: []
---

# Surface: the desk (app shell, Vérifier, Dossiers, a dossier, sources, team)

Scope: everything inside a workspace. Mode: Operate.
Audience and job: journalists and editors in Madagascar, on a cheap Android phone in the field or a laptop at the desk; also people who are not at ease with digital tools. Task: paste what was received and see what FANILO finds; follow each rumour to a confirmed verdict; see where every dossier stands.
Constraints: French UI (strings in lib/i18n/fr.ts); verdict never by colour alone; 360 px minimum; light and dark; live updates; the assistant must never cover the page.

## Direction contract

THESIS: Civic signage for rumours: every rumour travels one numbered line, 01 L'affirmation, 02 Les éléments, 03 La conclusion, lit live while FANILO works. It refuses the tile dashboard and the old programme grid and case-file props.

OWN-WORLD: Chalk ground #F1F2EC, white working cards, green-black ink #171A18, hairlines #D5D8CF, one citron #D7F45B for the action and the active step (never a verdict); an ink panel for « Le travail de FANILO ». Verdicts rust #9D382E, ochre, forest #286044, grey, always icon plus word. Archivo for titles, numbers and verdict words; Atkinson Hyperlegible Next for everything read. Square corners, 1 px rules, a 2 px ink border on the verdict block.

STORY: Anyone pastes a message or link, watches FANILO read it, light the suspicious phrases, bring sources one by one and suggest a conclusion; a journalist confirms; the desk sees every dossier's step at a glance.

FIRST VIEWPORT: Left rail (Vérifier, Dossiers, Sources, Équipe) with the citron active item; Vérifier: « Un doute ? Faisons le point. », one large field with microphone and the citron button, the 01/02/03 line explained beside it, recently checked dossiers on the right. During a check: the message with citron highlights, the live line, the ink live log, the sources wall. The assistant is an ink bar that opens as a docked panel which pushes the page (a 60 % sheet on phones).

FORM: user-pinned direction from a ChatGPT and Gemini brainstorm (« Le signal clair » / « Civique & Tranchée »), overriding the roll seed:64f79adacea003db.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

- Malagasy UI strings later.
