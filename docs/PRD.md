# Checky – PRD (FANILO until 2 Nov 2026)

@coco

## Overview

Checky (named FANILO until 2 Nov 2026; the repos keep the old name) is a verification tool for newsrooms, Madagascar first and world-ready. Every rumour gets a dossier, from its first appearance to a signed verdict: the desk tracks claims live, gathers the sources, a crew of checks states the facts at once and an AI reading whose quotes are checked against the sources is suggested, and a journalist signs the verdict before anything leaves the newsroom under its name. Published verdicts are open to the public, and Checky sends them back down the road the rumour took (WhatsApp, Facebook, radio, SMS, a printed poster).

**Checky, the product rules (2 Nov).** Knowing is not publishing: facts (a video's first appearance, a registry diff against the original communiqué, an official figure, a fact-checker's published review) show at once and solid; the AI reading « Lecture de Checky » is dashed and reserved to the newsroom; « Signer et publier » is a byline, the public never sees the reading or a percentage. A check runs as a crew: Lecteur (one model call), then Provenance, Registre, Chiffres, Fact-checkers, Web, Archives, Fiabilité and Ton in parallel without a model, then Synthèse and Contradicteur (one call each), then a confidence score computed in code; « Mode sans IA » keeps the facts when the model is off. One kind of account: every journalist of a newsroom may do everything; partners and citizens use token links and SMS. Everyone can check; only newsrooms verified by the Checky team publish. Any country, tuned for Madagascar. Madagascar first, world-ready: structured places geocoded by OpenStreetMap, beats per newsroom, worldwide fact-checkers through Google Fact Check Tools, figures per country. Assembled from the best existing tools (NewsGuard's transparency grid, The Factual's source diversity and tone, Aletheia's cited explanations, FauxLens' per-signal image breakdown, Logically's AI plus humans, Check-It's multi-signal pipeline, Snopes/PolitiFact/FactCheck.org/AFP Factuel relayed as theirs), then one step further: the road (Le trajet), the signed and attested verdict, the registry of originals with an offline seal, the radio and SMS return path. The full product thinking is in the Claude Doc « FANILO Hackathon — The brief, decoded, and how we win » (tabs Winning idea, Functionality, Stack, Pitch).

**The event.** The FANILO Hackathon is organized by the Institut français de Madagascar (IFM) and the press service of the French Embassy, hosted at 42 Antananarivo in Andraharo. Teams of 4 build a working web or mobile app that meets a real need of journalists and media professionals around information resilience: verifying information, misinformation and AI-generated content.

**The need.** The need the app answers is presented by video at the kickoff on Monday 2 November at 8:00.

**The product.** A web app (Next.js, installable as a PWA) and an API (FastAPI) with authentication, newsroom workspaces, file handling, realtime updates, background jobs and an AI layer: a model gateway with fallback, search over the sources with citations, speech-to-text and a tool-using agent. Everything runs on free tiers.

## Goals and success criteria

FANILO succeeds if a newsroom can take a rumour from its first appearance to a sourced, signed verdict in one shared tool, from a phone, and if the demo never fails in front of the jury.

**Goals**

1. Give a newsroom one shared place to track claims, gather sources and confirm verdicts, live.
2. Provide AI help that always cites its sources: questions over documents with citations, audio transcription, an agent with tools. The AI only suggests.
3. Cover the journalist's main tasks end to end (see Features).
4. Ship a polished, consistent UI that looks like a finished product, not a hackathon prototype (see UI and design).
5. Make the demo reliable: hosted URL, fallback between AI providers, seed data, no dependency on one free tier.
6. Stay compliant with the hackathon rules: every third-party component listed with version and license.
7. Cost nothing: free tiers only.

**Non-goals**

- No native mobile app. The PWA covers phones; Expo may come later on the same API.
- No production hardening beyond what a 3-minute demo needs (no SSO, no multi-region, no audit compliance).
- No conversational voice agent until the core features work end to end.

**Success criteria**

- [ ] A user can sign up, log in and land in a workspace on the hosted URL, from a phone on mobile data.
- [ ] A PDF and a web URL can be ingested, and a question returns an answer citing source and passage.
- [ ] A 5-minute French audio file returns a timestamped transcript.
- [ ] Job progress and new items appear live in a second browser without refresh.
- [ ] Turning off the primary AI provider key does not break the app (fallback works).
- [ ] The claim checker and the verification board work end to end on seed data.
- [ ] Every main screen passes the UI polish checklist on a phone and a laptop.

## Users

FANILO serves the newsroom that verifies information, and the public that wants to know whether a rumour is already checked.

| Persona | Who | What they need |
| --- | --- | --- |
| Journalist | Reporter in the field, often on a phone with a slow or unstable connection | Fast mobile pages, upload a photo, record audio, paste a link from Facebook or WhatsApp, work in French and Malagasy |
| Checky team | The people who run Checky (`PLATFORM_ADMINS`), not a role inside a newsroom | Review newsroom requests: call the number on the outlet's official page, then approve or refuse with a reason |
| Public | Anyone who received a rumour, no account | Ask whether it is already verified, read published verdicts, report a rumour and follow it |
| Jury | Evaluates a 3-minute pitch on 4 November | A live demo that loads instantly and never fails |

**One kind of account.** Every member of a newsroom is one of its journalists and may do everything the newsroom can do: invite, sign and publish, edit the Annuaire, reset the demo. **Tout le monde peut vérifier ; seules les rédactions vérifiées publient:** a new newsroom works at once, privately, and sends a verification request (outlet, kind, city, region, country, official page, the person's full name, job title, phone, professional email, optional press card). The Checky team calls the number shown on the outlet's official page and approves or refuses with a reason. Until it is approved nothing of the newsroom reaches the public (archive, tips, SMS, partner radios, « Vérifié par »); its personal data is only seen by the Checky team.

## Constraints

The hard limits come from the hackathon rules, the free tiers we rely on, and the network conditions in Antananarivo.

**From the hackathon rules**

- Every third-party component (libraries, runtimes, algorithms, APIs) must be listed with its version and license (Article 6). We keep `THIRD_PARTY.md` updated as we go.
- Hard deadline Tuesday 3 November at 20:00; no extension (Article 4).
- Pitch of 3 minutes maximum on Wednesday 4 November, 8:00 to 13:00 at IFM Analakely. It must let the jury understand the need, the solution and how it works, the value for media professionals, and the potential (Article 4).
- The jury scores relevance to the need, usability, contribution to information resilience, technical quality and functionality, development potential, and the quality of the pitch (Article 5). Its decisions are final; prizes are announced before the event.
- Teams of exactly four; registration through the form by **28 October 2026** (Article 3). The rules end with a team sheet (team name, four names, date, acceptance).
- Questions about the rules go to Christelle Ramanandraitsiory at the IFM (christelle.ramanandraitsiory@institutfrancais-madagascar.com).
- We keep ownership of our code; organizers may publicize screenshots and slides with our names (Article 6).
- Participants are responsible for their own equipment and data (Article 8).

**From free tiers**

- Neon free: 1 GB database and 5 GB object storage per project, compute scales to zero when idle and wakes on the next query (a few seconds), 10 branches per project. Database and files live in one Neon project.
- Vercel Hobby: non-commercial use only; no persistent WebSocket connections.
- Render free: service spins down after 15 minutes idle (about 1 minute to wake), ephemeral filesystem, no free background workers.
- AI free tiers have per-minute and per-day rate limits that change without notice; free-tier data may be used by providers.

**From the environment**

- Connection at the venue and on mobile data may be slow or drop. Pages must stay light; the app must handle reconnection.
- Content arrives in French and Malagasy, often as Facebook posts, WhatsApp forwards, screenshots and voice notes.
- Paying online in USD from Madagascar can be hard, which is one more reason to stay on free tiers.

## Architecture and stack

Two services share one Neon project: Next.js owns the UI and authentication, FastAPI owns business logic, AI and realtime, and every call to FastAPI carries a Better Auth JWT.

&#91;embedded content: architecture · 2 services, Neon database and storage, AI providers\]

The browser talks to both services; files go straight from the browser to Neon Object Storage through a presigned URL that FastAPI issues, so large uploads never pass through the API.

| Layer | Choice | Notes |
| --- | --- | --- |
| Web app | Next.js (App Router), TypeScript | Deployed on Vercel Hobby |
| UI | Tailwind CSS + shadcn/ui | Mobile-first; PWA manifest and icon |
| Auth | Better Auth in Next.js, JWT plugin | FastAPI verifies tokens with the JWKS endpoint |
| API | FastAPI (Python), Pydantic, SQLAlchemy + Alembic | OpenAPI schema generates the TypeScript client |
| Realtime | python-socketio on FastAPI; socket.io-client in the browser | SSE for streaming AI answers |
| Database | Postgres 18 + pgvector (Neon free, project `fanilo` in the 0nlydevs org, Frankfurt) | Better Auth tables and app tables in one database, separate schemas. Chosen over Supabase Postgres: wakes automatically instead of pausing, free branching |
| File storage | Neon Object Storage (S3-compatible, private buckets `uploads` and `uploads-dev`, same Neon project) | Never on the API server's disk; boto3 presigned URLs; branches with the database |
| Background jobs | Postgres job table, worker loop in the API process | No extra service to host; queued jobs survive restarts |
| Language models | Groq `openai/gpt-oss-120b` (primary), Gemini `gemini-3.5-flash-lite` (fallback), NVIDIA NIM (third) | All called through one OpenAI-compatible gateway; models change often on free tiers, so they are set by env |
| Embeddings | Gemini `gemini-embedding-2`, 768 dimensions (chosen after an 18/18 top-3 test in French, Malagasy and across the two) | Model name stored with every vector |
| Speech-to-text | Groq Whisper; local faster-whisper as backup | Test French and Malagasy first |
| Parsing | pypdf (PDF, BSD), trafilatura (web pages), Pillow (EXIF) | pypdf rather than PyMuPDF, which is AGPL |
| API hosting | Render free (or Railway trial), Frankfurt | Wake it up before the pitch |
| Monorepo | npm workspaces + Turborepo | `apps/web`, `apps/api`, `packages/shared` |

## Functional requirements

The requirements below describe how FANILO handles newsroom access, claims, sources and verification.

### M1. Authentication

- Sign up and log in with email and password through Better Auth; optional Google OAuth.
- Session cookie on the web; JWT issued by the Better Auth JWT plugin for calls to FastAPI.
- FastAPI dependency `current_user` verifies the JWT signature against the cached JWKS, checks expiry, and loads the user.
- Workspace membership checked by one FastAPI dependency (`AnyMember`); no roles.
- Acceptance: an unauthenticated call to any `/api` route returns 401; an outsider gets 404 on a workspace.

### M2. Workspaces and members

- Create a workspace; then send its verification request (or later, from Réglages).
- Invite by link (token, no email sending required: any member copies the link).
- List members; any member removes a colleague or leaves, never the last one.
- Every domain record belongs to one workspace; every query filters by workspace.

### M3. Claims and newsroom records

One flexible model, `item`, for the domain objects (a claim, a story, a rumor, a source).

- Fields: title, body, `type`, `status`, `tags`, `data` (JSONB for anything problem-specific), author, timestamps.
- Full CRUD with pagination, filter by status, type and tag, text search.
- Comments on items, and an activity log (who changed what, when).
- Acceptance: adding a new field needs only a JSONB key and a UI field, no migration.

### M4. Files and sources

- Upload images, PDFs and audio (max 25 MB) through a presigned upload URL straight to Neon Object Storage.
- Attach files to items. Store type, size, hash and metadata.
- Add a web source by URL: fetch, extract the main text with trafilatura, store title, author, date and text.
- Images: read EXIF metadata and offer a reverse image search link.

### M5. Realtime

- Socket.IO server on FastAPI, authenticated with the same JWT at handshake; connection rejected without a valid token.
- One room per workspace; joining checks membership.
- Events: `item.created`, `item.updated`, `comment.created`, `job.progress`, `job.done`, `job.failed`, `presence`.
- Client reconnects automatically and re-fetches the list after a reconnection.

### M6. Background jobs

- Queue stored in the Postgres job table and claimed with SELECT … FOR UPDATE SKIP LOCKED by a worker loop in the API process; jobs: `ingest_document`, `ingest_url`, `transcribe_audio`, `embed_chunks`.
- Each job has status (`queued`, `running`, `done`, `failed`), progress 0 to 100, error message, result.
- Progress pushed over Socket.IO; failed jobs can be retried from the UI.

### M7. AI gateway

- One function `complete(messages, tools?, stream?)` over an OpenAI-compatible client.
- Provider order from config: Groq, then Gemini, then NVIDIA. On 429, 5xx or timeout, retry with backoff, then move to the next provider.
- Streaming to the browser over SSE.
- Logs per call: provider, model, latency, tokens, success. A cache keyed on the request avoids burning quota during development.
- Acceptance: with the Groq key removed, calls still succeed through Gemini.

### M8. RAG pipeline

- Ingest: PDF, URL, text and transcripts → clean → split into chunks of about 800 tokens with 100 overlap → embed in batches → store in pgvector with source id, page or timestamp, and model name.
- Search: embed the question, top-k by cosine similarity filtered by workspace, optional keyword boost.
- Answer: the model answers only from the retrieved passages and cites each claim as `[n]`; every citation links to the source and passage.
- When no passage is relevant, the answer says so instead of guessing.
- A `reembed_all` script rebuilds every vector if we switch embedding provider.

### M9. Speech-to-text

- Record in the browser with MediaRecorder, or upload mp3, m4a, wav, webm.
- Transcribe through Groq Whisper with a language hint (`fr`, `mg` or auto). Uploads are capped at 25 MB, the provider's limit, so no splitting is needed yet.
- Output: segments with start and end times; the transcript is saved and can be ingested into RAG.
- Play the audio from any segment by clicking its timestamp.

### M10. Agent

- A simple loop: model, tool calls, results, until an answer or a limit of 6 steps.
- Starting tools: `search_sources` (RAG), `fetch_url`, `find_claims`, `web_search`. Dedicated search
  optionally uses Tavily's free API; keyless HTML search is a best-effort legacy fallback.
- Each step is shown in the UI (tool called, short result), so the reasoning is visible in the demo.
- Adding a tool means writing one Python function with a typed signature and a docstring.

### M11. Web app shell and PWA

- Pages: login, sign up, workspace switcher, items list, item detail, upload, ask (RAG chat), transcribe, members, settings.
- Responsive from 360 px wide; bottom navigation on mobile.
- PWA manifest, icon and installability; share target so a link can be shared into the app from a phone.
- Typed API client generated from FastAPI's OpenAPI schema; loading, empty and error states on every page.
- French as the default UI language, with strings kept in one file so Malagasy can be added.

### M12. Demo tools and newsroom verification

- "Reset demo data" button for any member (fictional people and numbers only, labelled démo; it never verifies a newsroom).
- « Demandes des rédactions » (`/checky`) for the Checky team: pending, approved and refused requests, Valider / Refuser with a reason.
- Health page showing database, storage and each AI provider as up or down.

## Features

Five features cover the journalist's main verification tasks, from checking a claim to sharing its confirmed verdict.

| Feature | What the journalist does | Built on |
| --- | --- | --- |
| F1. Claim checker | Paste text, a link or a screenshot; get the checkable claims, evidence from sources with citations, and a suggested verdict | M4, M7, M8, M10 |
| F2. Verification board | Track claims on a shared board: to check, in progress, verified, published; assign, comment, see changes live | M3, M5 |
| F3. Interview to quotes | Record or upload audio; get a transcript, the key quotes and the claims to check, each with its timestamp | M9, M7 |
| F4. Image check | Upload an image; see its metadata, duplicates already seen in the workspace, and reverse image search links | M4 |
| F5. Verdict card | Turn a verified claim into a shareable image card and a short post in French or Malagasy | M3, M7 |

Checky (2 Nov) adds the newsroom's shelves and the road back, on the same base:

| Feature | What it does | Built on |
| --- | --- | --- |
| C1. The crew (Vérifier) | Paste a message, a link or a file: eight fact checks race in parallel (provenance, registry, figures, fact-checkers, web, archives, source credibility, tone), then a dashed reading, a contradictor and a confidence score computed from the evidence; « Mode sans IA » keeps the facts | `graph.py`, `crew.py`, `confidence.py`, `tone.py`, `credibility.py` |
| C2. Sign and publish | « Signer et publier » turns the verdict solid under the newsroom's byline; batch sign; « Reprendre ce verdict » from a fact-checker's review; carnet de diligence and an Ed25519 attestation | `signing.py`, `attest.py` |
| C3. Qui peut le prouver | The one person who can prove the missing point, with their official page and a ready question sent by WhatsApp, mail or SMS; the answer becomes a dated source | `directory.py`, `/reponse/[token]` |
| C4. Registre and sceau | Originals registered by institutions, a quoted communiqué compared word by word (Authentique, Modifié, Introuvable, Incohérent), an Ed25519 seal verified offline from a QR, the public « Fil officiel » | `registry.py`, `seal.py`, `/sceau/[id]`, `/officiel` |
| C5. Chiffres | Every number in a claim against the official figure, its source, date and age; World Bank refresh | `figures.py`, `numbers.py` |
| C6. Ma rubrique, Veille, À l'antenne | A journalist's morning page by beats and places; the feed of what circulates (tips, SMS, press, radio clips) with a map; « Entendu à la radio » records what a station said in ten seconds; watched words; the rumour weather by season; story angles | `rubrique.py`, `veille.py`, `seasons.py` |
| C7. Trajet and Diffuser | The rumour's stops and the truth's, the gaps, and one button to send the verdict back: card, radio line, flash, SMS, poster with a sealed QR; Malagasy formats go out only as the exact text a journalist reread (« Relu en malgache ») | `trajet.py` |
| C8. Public layer and SMS | A citizen's check answers with a signed verdict, a fact-checker's review or the facts alone; « Me prévenir »; an SMS line with keywords, hashed numbers and an outbox; flashs of the day; short links | `verify_public.py`, `sms.py`, `/flashs`, `/v/[ref]` |
| C9. Alerts | The same dangerous rumour across tips, SMS, radio and dossiers grouped into one alert (ALR-…), French and Malagasy alike; a journalist splits or merges; danger level adjustable with a logged reason | `alerts.py` |
| C10. Est-ce bien eux ? | A pasted message's attribution, page, phone number and headline compared with the Annuaire (contact kinds, declared official numbers), the registry and Veille: facts, never a verdict | `gestures.py`, `directory.py` |
| C11. Safe pictures | Every uploaded image and video keyframe gets a single-frame, EXIF-free, face-blurred copy; only it is shown or reverse-searched; an original is revealed on request with the look logged; « déjà vue » recall | `media.py`, `media_api.py` |
| C12. Reading preferences | A−/A+ text size and « Mode éco » (system fonts, no motion, slower polling, images and maps on request), remembered per device | `lib/prefs.ts`, `components/prefs/` |

### F1. Claim checker

- Input: text, a URL (Facebook post, article) or a screenshot. Screenshots go through OCR by a vision-capable model, if a free one is available.
- Step 1: extract the checkable claims (who, what, number, date) as a list the journalist can edit.
- Step 2: for each claim, search the workspace's sources (RAG) and the web (agent), and list evidence for and against, each with its citation.
- Step 3: suggest a verdict from a fixed scale: `true`, `misleading`, `false`, `unverifiable`, with a one-line reason. The journalist always confirms or changes it; the app never publishes a verdict on its own.
- Beyond the attached sources, the checker reads up to 3 other sources of the newsroom that are close enough to the claim (similarity ≥ 0.78, measured on the demo files), marked as coming from another file.
- Dates are worked out in code, never guessed by the model: today, when the rumour was first seen, each source's date and its gap to the rumour. A "true" whose supporting passages all date from more than 30 days before the rumour becomes "unverifiable"; each piece of evidence shows its date. A page date that is only guessed and falls today, with no metadata to back it, counts as unknown. The journalist can set or correct any source's date by hand.
- Output: a claim item on the verification board, with its evidence attached.

### F2. Verification board

- Columns by status; cards show the claim, assignee, verdict and number of sources.
- Drag a card to change status; the change appears live for everyone in the workspace.
- Card detail: claim, evidence panel, comments, activity history.
- Filters by assignee, verdict, tag and date.
- While a new claim is typed, the claims already followed with the same words are shown, to open instead of creating a duplicate (word overlap, no AI).

### F3. Interview to quotes

- Upload or record audio, transcribe (M9), then extract quotes and checkable claims with timestamps.
- Click a quote to play the audio at that moment; send a claim to F1 in one click.

### F4. Image check

- Show EXIF data (camera, date, location when present) and say clearly when it is missing.
- Perceptual hash to find the same or near-same image already in the workspace.
- One-click links to reverse image search engines.
- Show any signals as hints, never as proof: the app does not claim to detect AI-generated images with certainty.
- Traces of AI generators found in the file (EXIF, PNG text, XMP/IPTC « trainedAlgorithmicMedia », Midjourney, Stable Diffusion, DALL·E, Firefly…) and Content Credentials (C2PA) when present; none found proves nothing.

### F6. Vérifier un message ou un lien

- This is the desk's home, « Vérifier »: a pasted or dictated message works as well as a link, and FANILO's work shows live on the numbered line (the phrases that should worry lit one after another, a log of what it reads and searches, the sources arriving, then the suggested conclusion).
- Paste a post, article or image link (or the post's text when the link needs an account, as on Facebook and TikTok) and get in one pass: what it claims, the warning signs in how it is written (each with its quote), what fact-checkers, the web and Wikipedia already say, and a suggested verdict resting only on those results, each quote checked.
- Nothing is written until the journalist follows it in the desk, with the sources they tick; the journalist still confirms the verdict on the claim.
- No detector of AI-written text is reliable, so text only gets hints, never an "AI probability".
- The content's publication date and age come from code; past 30 days the page warns that an old post may be circulating again.

### F5. Verdict card

- Template with the claim, the verdict, a short reason and the sources, rendered as a PNG sized for Facebook and WhatsApp.
- A draft post of 2 to 3 sentences generated in French or Malagasy, editable before copying.

### F7. Browser extension

- A separate Manifest V3 extension (`0nlyDevs/fanilo-extension`), usable without an account:
  selected text, a public link or image → explicit confirmation → side-panel checks.
- Anonymous text checks return related, journalist-confirmed published verdicts and external
  sources. Matches are candidates to compare with the original claim, not automatic verdicts on
  the submitted passage. New subjects receive evidence to examine, never an invented AI verdict.
- Before searching, one bounded AI call extracts literal claims, entities and grounded queries
  from the full cleaned text. No invented name, year or verdict is accepted. Distinctive names
  beyond the first 200 characters are retained; unavailable/invalid AI preparation falls back
  explicitly. Public preparation excludes paid Claude fallback and uses no persistent response cache.
- Queries and service outcomes are visible. Blocked services, partial coverage and successful
  empty results are distinguished. Up to three sources are read for literal passages, with
  unread search snippets clearly labelled. Similar wording is a possible reprise, not proof of
  independent corroboration. No source count is presented as a confidence score.
- Dedicated web search uses an operator's server-side Tavily key, never a visitor account.
  Only verified free-plan usage without pay-as-you-go is accepted. Basic search, no automatic
  depth upgrade, no generated answer and no POST retry. API activation needs a key; no paid
  search service is activated by the repository. Setup is in `docs/WEB_SEARCH.md`.
- Selected text is checked independently of the surrounding page. No passive page reading,
  content scripts, browsing history, provider keys or cookie-reading permission.
- Connection is optional at save time or for newsroom analysis. It reuses the website session JWT,
  the private `link-check` stream and confirmed copilot actions. Public results survive connection;
  no write happens until confirmation. Private errors never silently fall back to public processing.
- Image provenance is separate from factual truth: metadata generator hints, unverified Content
  Credentials presence, reverse-search links, a persistent fallibility warning, and no invented
  confidence percentage. An image caption can be checked as text, not inferred from its pixels.
- `POST /workspaces/{ws}/image-check {url}` reads public raster images only (5 MB and 20 MP max).
  An optional pixel-detector adapter remains disabled until configured and evaluated by an operator.
  No external pixel detector is enabled or claimed to be reliable by default.
- `POST /public/check {text?,url?}` and `/public/image-check {url}` require no JWT. They share
  per-process limits: 12 requests/IP/10 minutes, 1,000/24-hour budget period, 2 in flight. The public
  `/check/stream` route exposes preparation/search/reading progress without a token. Public detector
  use needs an additional operator opt-in.
- Initial distribution is an unpacked Chromium extension. Browser-store publication, OCR,
  screenshots, private images and Firefox/Safari are not included. Production login and Edge/Brave
  behaviour require manual validation before distribution.

## UI and design

The UI looks like civic signage for rumours, « Le signal clair »: calm, clear and simple enough for someone who has never used a fact-checking tool, with one design system for the desk and the public site. The full rules live in `apps/web/DESIGN.md`.

**Design system**

- Tokens as CSS variables in the Tailwind theme, light and dark: chalk ground `#f1f2ec`, white cards, ink `#171a18`, 1 px rules, square-ish corners.
- One citron `#d7f45b`, only for the one action of a screen, the active step and highlights (the phrases of a message that should worry); never a verdict, a status or decoration.
- Four verdict colours used everywhere the same way (`true` green, `misleading` ochre, `false` rust, `unverifiable` grey), each with fill / on / soft / ink tokens at 4.5:1 contrast, always with an icon and a word, never colour alone. An AI suggestion is a dashed outline; a confirmed verdict is solid. Workflow status uses ink icons only.
- Typography: Archivo for titles, numbers, refs and verdict words; Atkinson Hyperlegible Next for everything read.
- Icons: one set only (lucide, which ships with shadcn/ui). shadcn/ui components themed once with the tokens.
- Signature: the numbered line every rumour travels, 01 L'affirmation, 02 Les éléments, 03 La conclusion. It runs live while FANILO checks a message, sits on every dossier, runs down a dossier's page, and explains a published verdict and a tip's follow-up.
- The assistant never covers the page: on a computer it is docked on the right and the page makes room; on a phone it is a sheet over the lower part. It opens from the navigation, not from a floating button.

**Navigation**

- Desk, five tabs and no more: Ma rubrique (home; angles), Vérifier (paste or dictate a message or a link), Dossiers (with Sources), Veille (map with a country menu and « Monde », the feed, what the public asks, « Entendu à la radio »), Annuaire (with Documents, Communiqués, Chiffres). Réglages (with Équipe and Vérification) in the account menu. New features go inside an existing page. In the UI: « rédaction » for the workspace, « dossier » for each followed rumour.
- Public: Vérifier (the home: « Est-ce déjà vérifié ? », the latest verdicts, a fictional rumour worked through, how a rumour is verified, a band for newsrooms), Les verdicts, Signaler; « Espace rédaction » leads to sign-in.

**Public features**

Ordinary people can use FANILO without an account, in the same world as the desk:
- « Est-ce déjà vérifié ? » (`/verifies`): a public AI assistant. Ask a question or paste a message received on WhatsApp or Facebook, in French or Malagasy; it answers only from verdicts published by newsrooms, citing them [n] with links to each file. With nothing published on the subject it makes no AI call and invites a tip. It never makes up a verdict.
- The archive of published verdicts, searchable, each with its reason, sources and a shareable page that can be listened to and shared on WhatsApp.
- « Signaler une rumeur » (`/signaler`): send a message or link to a newsroom; it lands in its « à vérifier » list, tagged « signalement », live. No personal data is asked; a follow-up link (`/suivi/…`) shows the steps and the verdict once published.
- The assistant sits on every page (docked beside it on a computer) and is an agent for the site itself, not only for checking facts. For visitors it answers from published verdicts, explains FANILO, prepares a tip (shown as an editable draft, sent only when the visitor presses Envoyer), says where their own tips stand and opens the right page. Inside a workspace it is the desk's copilot: what has circulated longest, the night in brief, claims without sources, answers from the sources, and proposed changes (new claim, attach a link, run the analysis, move a status, open a claim) that run only after the journalist confirms, with their own rights. It never confirms a verdict and never publishes. Questions can be dictated in French or Malagasy (Groq Whisper), and in voice mode the question is sent as soon as it is spoken and the answer is read aloud.
- Each newsroom opts in (« Publier nos verdicts » in Réglages) and must be verified by the Checky team; the demo reset opts the demo newsroom in, verification stays the Checky team's.
- Any country: search covers every newsroom with the visitor's country first; a tip with no newsroom chosen goes to the newsroom where the rumour circulates, else the nearest, and the visitor is told which.

**Component inventory**

| Component | Used in |
| --- | --- |
| App shell: sidebar on desktop, bottom navigation on mobile, workspace switcher | All pages |
| Verdict badge and status badge | F1, F2, F5 |
| Claim card and board column | F2 |
| Evidence panel with citation chips that open the source at the passage | F1, M8 |
| Chat with streaming answer, citations and agent steps | M8, M10 |
| Upload dropzone with progress, and audio recorder | M4, M9 |
| Transcript viewer with clickable timestamps | M9, F3 |
| Job progress toast | M6 |
| Empty state, loading skeleton, error state | All pages |

**Polish checklist (every main screen)**

- [ ] Looks right at 360 px and 1440 px wide.
- [ ] Loading shows skeletons, never a blank page or a spinner alone.
- [ ] Empty states explain what to do next, with one primary button.
- [ ] Errors say what happened and offer a retry.
- [ ] Actions give feedback within 100 ms (optimistic update or toast).
- [ ] Light and dark mode both checked.
- [ ] Keyboard focus visible; all inputs labeled.
- [ ] Subtle motion only: 150 to 200 ms transitions, no decorative animation.

**Branding**

- Product name and logo kept in one config file and one SVG, so they change in one place.
- A clean favicon and PWA icon, since the jury may see the app installed on a phone.

## Data model

Better Auth manages its own tables (`user`, `session`, `account`, `verification`, `jwks`) in the `better_auth` schema (not `auth`, which hosted Postgres platforms often reserve); our tables live in the `app` schema, all with UUID primary keys and `created_at` / `updated_at`.

| Table | Key fields | Notes |
| --- | --- | --- |
| `workspace` | id, name, slug |  |
| `membership` | workspace\_id, user\_id | Unique on (workspace\_id, user\_id); no role |
| `invitation` | workspace\_id, token, expires\_at, used\_at | Link-based invites |
| `newsroom_request` | workspace\_id, outlet, kind, city, region, country, website, full\_name, job\_title, phone, email, press\_card, reason, reviewed\_by/at | The verification request; `workspace.verification` = none, pending, approved, refused |
| `official_source` | country, host, name, workspace\_id | A newsroom's « Sources officielles », shared with its country once it is verified |
| `item` | workspace\_id, author\_id, type, title, body, status, tags (text\[\]), data (JSONB) | Claims and newsroom records; GIN index on tags and data |
| `comment` | item\_id, author\_id, body |  |
| `activity` | workspace\_id, actor\_id, entity, entity\_id, action, diff (JSONB) | Written on every create, update, delete |
| `file` | workspace\_id, item\_id?, storage\_key, mime, size\_bytes, sha256, meta (JSONB) | Object in the Neon bucket; EXIF and other metadata in meta |
| `source` | workspace\_id, kind (`pdf`, `url`, `text`, `transcript`), title, url?, file\_id?, author?, published\_at?, text | One row per ingested document |
| `chunk` | source\_id, workspace\_id, ord, text, page?, start\_s?, end\_s?, embedding vector(N), embed\_model | HNSW index on embedding; N set by the chosen model |
| `transcript` | file\_id, language, duration\_s, segments (JSONB) | Segments: start, end, text |
| `job` | workspace\_id, kind, status, progress, input (JSONB), result (JSONB), error |  |
| `conversation` / `message` | workspace\_id, user\_id / conversation\_id, role, content, citations (JSONB), tool\_calls (JSONB) | RAG chat and agent history |
| `ai_call` | provider, model, latency\_ms, tokens\_in, tokens\_out, ok, error | Gateway log, no prompt text stored |

The user id in `app` tables is the Better Auth user id (text), referenced without a foreign key across schemas.

## API specification

All FastAPI routes live under `/api/v1`, require `Authorization: Bearer <jwt>` except `/health`, and are scoped by `{ws}` = workspace id. Errors use one shape: `{"error": {"code": "...", "message": "..."}}`; someone outside a workspace gets 404, not 403.

| Method | Path | Purpose | Who |
| --- | --- | --- | --- |
| GET | `/health` | Database, storage, AI providers status | public |
| GET | `/me` | Current user and memberships | any |
| POST | `/workspaces` | Create workspace | any |
| GET | `/workspaces/{ws}/members` | List members | any member |
| POST | `/workspaces/{ws}/invitations` | Create invite link | member |
| POST | `/invitations/{token}/accept` | Join a workspace | any |
| DELETE | `/workspaces/{ws}/members/{user}` | Remove a colleague or leave | member |
| GET / POST | `/workspaces/{ws}/items` | List (filters, pagination) / create | any member / journalist+ |
| GET | `/workspaces/{ws}/items/similar?q=` | Claims sharing most of the words of a claim being typed | any member |
| GET / PATCH / DELETE | `/workspaces/{ws}/items/{id}` | Read / update / delete | member |
| GET / POST | `/workspaces/{ws}/items/{id}/comments` | Comments | any member |
| GET | `/workspaces/{ws}/activity` | Activity log | any member |
| POST | `/workspaces/{ws}/files/upload-url` | Get a presigned upload URL | journalist+ |
| POST | `/workspaces/{ws}/files/{id}/complete` | Confirm an upload; creates the source and starts its analysis | journalist+ |
| POST | `/workspaces/{ws}/sources` | Add a source (URL or pasted text); a URL starts an ingest job | journalist+ |
| GET | `/workspaces/{ws}/sources` | List sources | any member |
| POST | `/workspaces/{ws}/transcriptions` | Transcribe a file; starts a job | journalist+ |
| GET | `/workspaces/{ws}/jobs/{id}` | Job status and result | any member |
| POST | `/workspaces/{ws}/jobs/{id}/retry` | Retry a failed job | journalist+ |
| POST | `/workspaces/{ws}/ai/complete` | One completion through the gateway (JSON) | any member |
| POST | `/workspaces/{ws}/ai/stream` | The same, streamed as SSE | any member |
| POST | `/workspaces/{ws}/search` | Semantic search over chunks | any member |
| POST | `/workspaces/{ws}/ask` | RAG answer with citations, streamed as SSE | any member |
| POST | `/workspaces/{ws}/agent` | Agent run, steps streamed as SSE | any member |
| POST | `/workspaces/{ws}/demo/reset` | Reset seed data | member |
| GET / PUT | `/workspaces/{ws}/verification` | The newsroom's verification request | member |
| GET / POST | `/platform/requests`, `/platform/requests/{ws}/approve`, `…/refuse` | Review requests | Checky team |

**SSE events for `/ai/stream`:** `delta` (`{text}`), then `done` (the full completion) or `error`.

**SSE events for `/ask` and `/agent`:** `token` (text delta), `citation` (source id, passage, page or timestamp), `step` (tool name, input, short result), `done`, `error`.

**Socket.IO:** namespace `/`, auth payload `{token}`, client emits `join` with a workspace id; server emits the events listed in M5 to room `ws:{id}`.

## Non-functional requirements

The bar is a demo that never fails in front of the jury, on a phone, on a weak connection.

| Area | Requirement |
| --- | --- |
| Performance | First page load under 3 s on 3G-like conditions; JS bundle under 250 KB gzipped for the main pages; API reads under 300 ms excluding AI calls |
| AI latency | First streamed token under 2 s; any AI call times out after 30 s and falls back |
| Reliability | No single free tier can take the app down: AI fallback, retries with backoff, jobs retryable |
| Resilience to network | Socket auto-reconnect; uploads resumable or retryable; clear offline and error messages |
| Security | JWT verified on every API call; workspace isolation on every query; secrets only in environment variables; CORS limited to the web app's origin; upload type and size checked; private bucket, presigned URLs only |
| Privacy | Only public test data while on free AI tiers; no prompt text stored in logs |
| Accessibility | Keyboard navigable, labeled form fields, contrast AA |
| Languages | UI in French; content in French and Malagasy supported end to end (ingest, search, transcription) |
| Maintainability | Typed end to end (Pydantic → OpenAPI → TypeScript); one copyable example per pattern; README with setup in under 15 minutes |
| Compliance | `THIRD_PARTY.md` lists every dependency and API with version and license, generated where possible |

## Repository, configuration and deployment

One monorepo, a local Postgres for development (Docker optional), and one push to `main` deploys both services. Setup steps for teammates are in the repository README.

**Repository layout**

```
fanilo-base/
  apps/
    web/            Next.js app, Better Auth, PWA
      app/          routes and pages
      lib/auth.ts   Better Auth config + JWT plugin
      lib/api.ts    API client (adds the JWT)
    api/            FastAPI
      app/
        core/       config, db, security (JWT/JWKS), errors, ai (gateway), storage (S3)
        modules/    workspaces, items, files, sources, jobs, ai, rag, stt, agent
        realtime/   Socket.IO server and events
        workers/    job handlers (Postgres queue)
      alembic/      migrations
      scripts/      seed.py, reembed_all.py
  packages/
    shared/         generated types, constants
  docker-compose.yml   postgres+pgvector (optional)
  THIRD_PARTY.md
  README.md
```

**Environment variables**

| Variable | Used by | Example |
| --- | --- | --- |
| `DATABASE_URL` | web, api | Neon Postgres connection string (direct, not pooled; `sslmode=require` is translated for asyncpg); a local Postgres in development |
| `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL` | web | random 32 bytes; web URL |
| `AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE` | api | `https://<web>/api/auth/jwks` |
| `NEXT_PUBLIC_API_URL` | web | API base URL |
| `CORS_ORIGINS` | api | web URL |
| `STORAGE_ENDPOINT`, `STORAGE_REGION`, `STORAGE_ACCESS_KEY_ID`, `STORAGE_SECRET_ACCESS_KEY`, `STORAGE_BUCKET` | api | Neon branch storage endpoint and credential; bucket `uploads` (production), `uploads-dev` (local) |
| `LLM_PROVIDERS` | api | `groq,gemini,nvidia` (order = fallback order) |
| `GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY` | api | one set per team member if needed |
| `LLM_MODEL_GROQ`, `LLM_MODEL_GEMINI`, `LLM_MODEL_NVIDIA` | api | empty = gateway defaults (`openai/gpt-oss-120b`, `gemini-3.5-flash-lite`, `nvidia/nemotron-3.5-lightning-30b-a3b`) |
| `EMBED_PROVIDER`, `EMBED_MODEL`, `EMBED_DIM` | api | set once, never changed during the event |
| `STT_PROVIDER`, `STT_MODEL` | api | Groq Whisper |
| `AI_CACHE` | api | `true` in development |

**Deployment**

- Web: Vercel Hobby, connected to the repo, root `apps/web`.
- API + in-process worker: Render free web service (Docker), or Railway trial, in Frankfurt next to the database.
- Database and file storage: one Neon free project (`fanilo`, org 0nlydevs); migrations run with Alembic on deploy.
- A GitHub Action regenerates the TypeScript client when the OpenAPI schema changes, and fails the build if types are out of date.
- Before the pitch: open the API health page 5 minutes ahead to wake the service, and open Réglages so the Neon database wakes up.

## Testing and demo readiness

We test the paths the demo will walk, not coverage numbers.

**Automated (run in CI on every push)**

- API: pytest on auth (401, 403), workspace isolation (user A cannot read workspace B), items CRUD, job lifecycle, gateway fallback with a mocked failing provider.
- RAG: a fixed set of 10 questions over 3 seed documents; each must return at least one correct citation.
- Web: Playwright smoke test: sign up, create workspace, create item, see it appear in a second browser.

**Manual checks**

- [ ] Full flow on a real phone over mobile data.
- [ ] Embedding comparison: 20 French and Malagasy sentences, top-3 search accuracy per provider; choose one.
- [ ] Transcription quality on a French and a Malagasy voice note.
- [ ] Rate-limit behavior: 30 quick requests in a row do not crash the UI.
- [ ] Réglages shows database, storage and AI providers up; Render service awake; all keys loaded.

**Pitch kit** (`docs/pitch/`)

- Deck generated from one content file (`deck/content.js` → `fanilo-pitch.pptx`, 7 slides + 2 in reserve, importable into Google Slides with its fonts). It follows one rumour from 23:47 to its verdict: the night, the need in the jury's words, the pivot (not an AI that judges, a case file a journalist signs), the demo on the same rumour, what changes for journalists, what comes next, and the close back on the first frame. One idea per slide, few words on screen, the rest in the speaker notes. Every open point is a `{{hole}}` the build lists.
- Timed script (`script.md`, generated from the speaker notes, 3:00 split slide by slide) and the storyboard of the demo video.
- Demo video filmed by `scripts/pitch_video.py` from `video/scenes.json` on the real app with the demo data, following the same rumour (chapter cards, visible cursor, captions; silent, commented live; filmed again on the deployed app on Tuesday evening as the backup if the network fails).
- `checklist.md`: Tuesday 18:00–20:00 before the hand-in, Wednesday morning (wake Render and Neon, demo reset, tabs, plan B).

## Risks and mitigations

The biggest risk is a demo that fails in front of the jury: no single free tier, network or model may take the app down.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| UI polish eats the time needed for the core | Beautiful screens on a broken flow | Design system first, then polish only screens whose flow already works end to end |
| A free AI tier rate-limits or blocks us during the event | Features stop working | Three providers with automatic fallback; one key per member; response cache |
| A free AI model is renamed or retired | Calls fail with model errors | Models set by env (`LLM_MODEL_*`); Réglages shows each provider and model; already happened once (Groq Llama 3.3, Gemini 2.5 Flash) |
| Render service asleep at pitch time | 1-minute blank screen in front of the jury | Wake it 5 minutes before; backup screen recording |
| Neon database asleep at the first request | A few seconds' delay on the first screen | Open Réglages a few minutes before the demo to wake it |
| Weak Malagasy support in embeddings or transcription | Poor results on local content | Test on real French and Malagasy samples; pick the best provider; show French in the demo if Malagasy is weak |
| Venue internet slow or down | Cannot deploy or call AI | Phone hotspot as backup; local setup works offline except AI calls |
| Better Auth and FastAPI JWT setup breaks | Nothing works across services | Tested end to end; one integration test in CI |
| AI suggests a wrong verdict in the demo | Loss of trust with the jury | The journalist always confirms the verdict; evidence and citations always shown |
| Embedding provider changed mid-event | All vectors invalid | Provider fixed by config; `reembed_all` script ready |

## Open questions

- [x] Supabase or Neon? Neon, for both the database and file storage.
- [ ] Does the team registration page of the rules need to be submitted, or is the form enough?
- [ ] What prizes are offered, and does that change what the jury values?
- [x] Which embedding model? Gemini `gemini-embedding-2` (both Gemini models scored 18/18; NVIDIA not tested, no key).
- [ ] Is the Gemini free tier usable from Madagascar?
- [ ] Is a free vision model available for screenshot OCR in F1?
- [x] Free web search for the agent? Yes, without a key: DuckDuckGo's HTML results, the Wikipedia API and fact-checkers' sites (27 Oct). Google Fact Check Tools is an optional free key (Brave Search was dropped: no free plan any more); Claude is wired in as an optional provider, off until a key is set.
- [ ] Render free or Railway trial for the API?

## Sources

- [FANILO hackathon rules (PDF)](https://homemade.mg/media/img/reglement_hackathon_fanilo.pdf)
- [Neon pricing](https://neon.com/pricing)
- [Neon Object Storage](https://neon.com/docs/storage/overview)
- [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)
- [Render free tier](https://render.com/docs/free)
- [Railway plans](https://docs.railway.com/pricing/plans)
