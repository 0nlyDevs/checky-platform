---
version: 1
slug: "app-site-accueil-page-tsx"
primary_target: "app/(site)/accueil/page.tsx"
related_targets: ["app/(auth)"]
---

# Surface: public landing and the doors into the app

Scope: the public landing (`/accueil`, served at `/` to signed-out visitors) and the sign-in and sign-up frame. Mode: Persuade (the forms inside stay Operate).
Audience and job: the FANILO hackathon jury (IFM, French Embassy press service, media professionals) on a projector during a 3-minute pitch, and newsroom journalists on a phone. They must grasp the need, the method and the value in one viewport, then open a workspace.
Constraints: French UI; the jury criteria; Malagasy mobile data is expensive, so no 3D and only three small client components; reduced motion and no script both show the finished page; every rumour shown is fictional and labelled; no organiser logos; product name from `lib/brand.ts`.

## Direction contract

THESIS: Every rumour gets a case file. The page is the file of one night: surveillance frames, pieces of evidence, a redacted report that clears as it is read, and a stamp. It refuses the fact-check default (white page, shield or magnifier, AI slogan, laptop mockup, three feature cards) and the dropped directions (3D city, torch, engraving, newspaper front page).

OWN-WORLD: Manila #dcc9a3 ground, deeper #cfb98f, index card #efe4c8, ink #141210, one alarm red #c42a20 for stamps only. Anton for headlines in capitals, Special Elite only for the file's typed labels, Public Sans for everything read. Halftoned surveillance frames in ink on manila, folder-tab buttons, angled stamps that land once, papers tilted under one degree. App fragments (data-ui) keep their own lines and verdict colours.

STORY: 23:47, the reticle follows the night across four frames and the stamp lands; the affair in four pieces with the desk's notes; the method as a redacted report; what leaves at 7 behind folder tabs; the opening card that takes its stamp before sign-up.

FIRST VIEWPORT: Desktop, exactly one screen: four frames in a row, then « Chaque rumeur a son dossier. » on two lines with one sentence, the action and a secondary link, the case card on the right. Phone: a viewfinder (piece 1 recording, three thumbnails), the title, the sentence, the action.

SIGNATURE: the reticle sequence and the redacted report whose bars lift as it is read.

RISK: costume. Kept serious by Public Sans for reading, one red, small tilts, one paperclip.

FORM: seed:e2fb42e42ae75ec0 (impeccable concept-seed, persuade); direction chosen by the user: "Le dossier" (spy-dossier challenger, toned down).
