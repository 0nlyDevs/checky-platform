# Pitch kit

Everything for the 3 minutes in front of the jury on **Wednesday 4 November 2026, 8:00–13:00, IFM Analakely**: the deck, the timed script, the demo video and the checklist, with `{{holes}}` where the real story goes.

The rules that shape it ([règlement, PDF](https://homemade.mg/media/img/reglement_hackathon_fanilo.pdf)):

- **3 minutes maximum** (article 4). The script is timed slide by slide; rehearse with a stopwatch.
- The pitch must let the jury understand **the need, the solution and how it works, its value for media professionals, and its potential** (article 4). Each slide names which of these it serves.
- The jury scores **relevance, usability, contribution to information resilience, technical quality, potential, and the pitch itself** (article 5).
- The pitch follows **one rumour from start to end**: it arrives at 23:47 (cover, no introduction), the need in the jury's own words, the stance (« Une machine ne signe pas un verdict »), the demo of that same rumour from arrival to the public, what it changes, what comes next, and the close back on the rumour (« 23 h 47, une rumeur. 6 h 41, vérifié. »). The team introduces itself at the very end.
- Every third-party component is listed with version and licence in `THIRD_PARTY.md` (article 6): regenerate it on Tuesday evening (`npm run third-party`).

## What is in here

| File | What it is | Edit it |
| --- | --- | --- |
| `deck/content.js` | Every word of the deck and of the speaker notes, with `{{holes}}` | **yes, this is the one file to fill** |
| `deck/build.js` | Draws `deck/fanilo-pitch.pptx` and writes `script.md` from the content | only to change the design |
| `deck/fanilo-pitch.pptx` | The deck (7 slides + 2 in reserve), in the « dossier » world | no, regenerate it |
| `script.md` | The timed script, generated from the speaker notes | no, regenerate it |
| `storyboard.md` | What the demo video shows, scene by scene, and the rules for filming | yes |
| `video/scenes.json` | The scenes the camera script plays in the real app | yes |
| `video/out/demo.mp4` | The filmed demo (gitignored, regenerate it) | no |
| `checklist.md` | Tuesday evening and Wednesday morning, step by step | yes |

## Make the deck

```bash
node docs/pitch/deck/build.js
```

It writes `deck/fanilo-pitch.pptx` and `script.md`, then lists the `{{holes}}` still open. The deck is drawn with Anton, Special Elite and Public Sans, all on Google Fonts, so **Google Slides renders it as designed**: in Slides, *File → Import slides → Upload*, pick all slides, keep the original theme. From there anyone on the team edits text on a phone. PowerPoint or Keynote without those fonts fall back to Arial Narrow / Courier / Arial: still readable, less pretty.

Two ways to change the text on the day: edit `content.js` and rebuild (keeps the design, the script and the notes in sync), or edit in Google Slides after the import (fast, but the script and notes drift). Rebuild until Tuesday evening, then switch to Slides.

Design: one idea per slide; the screen holds a title and a few words, the speaker's words live in the notes (and in `script.md`). The palette is the public pages' « dossier » (manila `#dcc9a3`, index card `#efe4c8`, ink `#141210`, one alarm red `#c42a20` for stamps). The red is for stamps only; verdicts on screenshots keep the app's own colours. Big type: the hall is large and the projector is unknown.

## Film the demo video

```bash
# web on :3000 and API on :8000, with AI keys in apps/api/.env
uv run --with playwright python -I scripts/pitch_video.py
```

The script signs up a throwaway account with the demo data and prepares the story through the API (`setup` and per-scene `before` in `video/scenes.json`: find the rumour's claim, reopen it, run the AI analysis, publish it after the journalist signs). It opens every page once off camera, then for each scene draws a chapter card and films the real app with a visible cursor that moves, clicks and types like a person. Captions never name the AI's verdict: the video shows what the model really suggests. The result is `video/out/demo.mp4` (1080p, 30 fps, **silent**: the speaker comments it live, which is how it survives a dead network) plus one mp4 per scene in `video/out/scenes/`.

- `--only dossier verdict` re-shoots those scenes and keeps the others.
- `--base-url https://…` films the deployed app (do it once on Tuesday evening: that is the backup if the venue's network dies).
- `--email … --password …` uses an existing account instead of a throwaway; `--headed` shows the browser while it films.
- Want narration? Open `demo.mp4` in any editor (CapCut, DaVinci Resolve, Kdenlive) and record the voice over it; the chapter cards give the cuts. The WebCup video's recipe (a drawn presenter, one label per chapter, a subtitle under every shot) works on top of this: the cards are the labels, the captions are the subtitles.

Rules for anything on screen: demo data only (the reset seeds fictional, labelled claims), no real person's name or phone, no API key or URL with a token, French UI.

## On the day

See `checklist.md`. The short version: Tuesday before the 20:00 deadline → regenerate `THIRD_PARTY.md`, film the backup video on the deployed app, fill the deck, import it into Google Slides, rehearse three times with a stopwatch. Wednesday: wake Render and Neon, reset the demo, open the tabs, play.
