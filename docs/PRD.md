# FANILO Hackathon Base Platform – PRD

Oct 23, 2026 · @coco

## Overview

We will build a reusable, problem-agnostic base platform (the "socle") before 2 November 2026, so that during the FANILO Hackathon all 48 hours go into the features that answer the problem revealed on day one.

**The event.** The FANILO Hackathon is organized by the Institut français de Madagascar (IFM) and the press service of the French Embassy, hosted at 42 Antananarivo in Andraharo. Teams of 4 build a working web or mobile app that meets a real need of journalists and media professionals around information resilience: verifying information, misinformation and AI-generated content.

**The catch.** The exact problem is presented by video at the kickoff on Monday 2 November at 8:00. The IFM contact confirmed that work prepared in advance is allowed, so besides the generic plumbing we pre-build the features most likely to be needed and a polished UI, then adapt them on day one.

**The base.** A web app (Next.js, installable as a PWA) and an API (FastAPI) that already provide authentication, workspaces, file handling, realtime updates, background jobs and a generic AI layer: a model gateway with fallback, a RAG pipeline with citations, speech-to-text and a simple tool-using agent. Everything runs on free tiers.

## Goals and success criteria

The base succeeds if, on Monday at 8:30, a new feature can go from idea to deployed and demoable in under 2 hours.

**Goals**

1. Remove setup work from the hackathon: auth, database, deployment and UI shell are done and tested.
2. Provide generic AI building blocks that fit most likely problems: ask questions over documents with citations, transcribe audio, run an agent with tools.
3. Pre-build the features journalists are most likely to need (see Pre-built features), designed so they can be reshaped, renamed or dropped within an hour on day one.
4. Ship a polished, consistent UI that looks like a finished product, not a hackathon prototype (see UI and design).
5. Make the demo reliable: hosted URL, fallback between AI providers, seed data, no dependency on one free tier.
6. Stay compliant with the hackathon rules: every third-party component listed with version and license; pre-built work declared in the pitch.
7. Cost nothing: free tiers only until a deliberate decision on 31 October.

**Non-goals**

- No native mobile app. The PWA covers phones; Expo may come later on the same API.
- No landing or marketing page: the app itself is what the jury sees.
- No production hardening beyond what a 3-minute demo needs (no SSO, no multi-region, no audit compliance).
- No conversational voice agent until everything in Priority 2 works.
- No guessed feature built deeper than its core flow: depth goes into whatever the real problem turns out to be.

**Success criteria (checked on 1 November)**

- [ ] A user can sign up, log in and land in a workspace on the hosted URL, from a phone on mobile data.
- [ ] A PDF and a web URL can be ingested, and a question returns an answer citing source and passage.
- [ ] A 5-minute French audio file returns a timestamped transcript.
- [ ] Job progress and new items appear live in a second browser without refresh.
- [ ] Turning off the primary AI provider key does not break the app (fallback works).
- [ ] The claim checker and the verification board work end to end on seed data.
- [ ] Every main screen passes the UI polish checklist on a phone and a laptop.
- [ ] The 2-hour dry run on a mock problem ends with a working, deployed feature.

## Users

The base has two kinds of users: our own team, who build on it during the hackathon, and the media professionals who will use whatever app we build on top.

| Persona | Who | What they need from the base |
| --- | --- | --- |
| Builder | One of our 4 team members, Monday morning | Copyable patterns for a new page, endpoint, job and AI call; a working deploy in one command |
| Journalist | Reporter in the field, often on a phone with a slow or unstable connection | Fast mobile pages, upload a photo, record audio, paste a link from Facebook or WhatsApp, work in French and Malagasy |
| Editor | Desk editor or fact-checker who reviews and validates | Shared workspace, live status of items, see who did what |
| Admin | Team lead or demo operator | Manage members and roles, reset seed data before the pitch |
| Jury | Evaluates a 3-minute pitch on 4 November | A live demo that loads instantly and never fails |

**Roles in the base:** `admin`, `editor`, `journalist`. Each workspace member has exactly one role. Permissions are kept simple so they can be adapted to the real problem on day one.

## Constraints

The hard limits come from the hackathon rules, the free tiers we rely on, and the network conditions in Antananarivo.

**From the hackathon rules**

- Work prepared before the event is allowed (confirmed with the IFM contact). We still say in the pitch what was pre-built and what was built during the 48 hours.
- Every third-party component (libraries, runtimes, algorithms, APIs) must be listed with its version and license (Article 6). We keep `THIRD_PARTY.md` updated as we go.
- Hard deadline Tuesday 3 November at 20:00; no extension (Article 4).
- Pitch of 3 minutes maximum on Wednesday 4 November, 8:00 to 13:00 at IFM Analakely.
- We keep ownership of our code; organizers may publicize screenshots and slides with our names (Article 6).
- Participants are responsible for their own equipment and data (Article 8).

**From free tiers**

- Supabase free: 500 MB database, 500 MB file storage, 2 projects, project pauses after 1 week of inactivity.
- Vercel Hobby: non-commercial use only; no persistent WebSocket connections.
- Render free: service spins down after 15 minutes idle (about 1 minute to wake), ephemeral filesystem, no free background workers.
- AI free tiers have per-minute and per-day rate limits that change without notice; free-tier data may be used by providers.

**From the environment**

- Connection at the venue and on mobile data may be slow or drop. Pages must stay light; the app must handle reconnection.
- Content arrives in French and Malagasy, often as Facebook posts, WhatsApp forwards, screenshots and voice notes.
- Paying online in USD from Madagascar can be hard, which is one more reason to stay on free tiers.

## Architecture and stack

Two services share one Postgres database: Next.js owns the UI and authentication, FastAPI owns business logic, AI and realtime, and every call to FastAPI carries a Better Auth JWT.

&#91;embedded content: architecture · 2 services, 3 backing services\]

The browser talks to both services; files go straight from the browser to Supabase Storage through a signed URL that FastAPI issues, so large uploads never pass through the API.

| Layer | Choice | Notes |
| --- | --- | --- |
| Web app | Next.js (App Router), TypeScript | Deployed on Vercel Hobby |
| UI | Tailwind CSS + shadcn/ui | Mobile-first; PWA manifest and icon |
| Auth | Better Auth in Next.js, JWT plugin | FastAPI verifies tokens with the JWKS endpoint |
| API | FastAPI (Python), Pydantic, SQLAlchemy + Alembic | OpenAPI schema generates the TypeScript client |
| Realtime | python-socketio on FastAPI; socket.io-client in the browser | SSE for streaming AI answers |
| Database | Postgres + pgvector (Supabase free) | Better Auth tables and app tables in one database, separate schemas |
| File storage | Supabase Storage (S3-compatible) | Never on the API server's disk |
| Background jobs | ARQ + Redis, worker running in the API process | Avoids a paid separate worker on Render |
| Language models | Groq (primary), Gemini (fallback), NVIDIA NIM (third) | All called through one OpenAI-compatible gateway |
| Embeddings | One provider, chosen after the 25 Oct test: Gemini Embedding or NVIDIA | Model name stored with every vector |
| Speech-to-text | Groq Whisper; local faster-whisper as backup | Test French and Malagasy first |
| Parsing | PyMuPDF (PDF), trafilatura (web pages) |  |
| API hosting | Render free (or Railway trial) | Wake it up before the pitch |
| Monorepo | npm workspaces + Turborepo | `apps/web`, `apps/api`, `packages/shared` |

## Functional requirements

Each module below is generic: it is the plumbing any likely problem needs, and gets its domain meaning on day one. Priority P1 is due 27 October, P2 by 30 October, P3 only if time allows.

### M1. Authentication and roles (P1)

- Sign up and log in with email and password through Better Auth; optional Google OAuth.
- Session cookie on the web; JWT issued by the Better Auth JWT plugin for calls to FastAPI.
- FastAPI dependency `current_user` verifies the JWT signature against the cached JWKS, checks expiry, and loads the user.
- Workspace roles `admin`, `editor`, `journalist`, checked by a FastAPI dependency `require_role(...)`.
- Acceptance: an unauthenticated call to any `/api` route returns 401; a journalist calling an admin route returns 403.

### M2. Workspaces and members (P1)

- Create a workspace; the creator becomes admin.
- Invite by email (link with token, no email sending required: the admin copies the link).
- List, change role, remove members.
- Every domain record belongs to one workspace; every query filters by workspace.

### M3. Generic items (P1)

One flexible model, `item`, that becomes the domain object on day one (a claim, a story, a rumor, a source).

- Fields: title, body, `type`, `status`, `tags`, `data` (JSONB for anything problem-specific), author, timestamps.
- Full CRUD with pagination, filter by status, type and tag, text search.
- Comments on items, and an activity log (who changed what, when).
- Acceptance: adding a new field on day one needs only a JSONB key and a UI field, no migration.

### M4. Files and sources (P1)

- Upload images, PDFs and audio (max 25 MB) through a signed upload URL straight to Supabase Storage.
- Attach files to items. Store type, size, hash and metadata.
- Add a web source by URL: fetch, extract the main text with trafilatura, store title, author, date and text.
- Images: read EXIF metadata and offer a reverse image search link.

### M5. Realtime (P1)

- Socket.IO server on FastAPI, authenticated with the same JWT at handshake; connection rejected without a valid token.
- One room per workspace; joining checks membership.
- Events: `item.created`, `item.updated`, `comment.created`, `job.progress`, `job.done`, `job.failed`, `presence`.
- Client reconnects automatically and re-fetches the list after a reconnection.

### M6. Background jobs (P1)

- ARQ queue on Redis; jobs: `ingest_document`, `ingest_url`, `transcribe_audio`, `embed_chunks`.
- Each job has status (`queued`, `running`, `done`, `failed`), progress 0 to 100, error message, result.
- Progress pushed over Socket.IO; failed jobs can be retried from the UI.

### M7. AI gateway (P2)

- One function `complete(messages, tools?, stream?)` over an OpenAI-compatible client.
- Provider order from config: Groq, then Gemini, then NVIDIA. On 429, 5xx or timeout, retry with backoff, then move to the next provider.
- Streaming to the browser over SSE.
- Logs per call: provider, model, latency, tokens, success. A cache keyed on the request avoids burning quota during development.
- Acceptance: with the Groq key removed, calls still succeed through Gemini.

### M8. RAG pipeline (P2)

- Ingest: PDF, URL, text and transcripts → clean → split into chunks of about 800 tokens with 100 overlap → embed in batches → store in pgvector with source id, page or timestamp, and model name.
- Search: embed the question, top-k by cosine similarity filtered by workspace, optional keyword boost.
- Answer: the model answers only from the retrieved passages and cites each claim as `[n]`; every citation links to the source and passage.
- When no passage is relevant, the answer says so instead of guessing.
- A `reembed_all` script rebuilds every vector if we switch embedding provider.

### M9. Speech-to-text (P2)

- Record in the browser with MediaRecorder, or upload mp3, m4a, wav, webm.
- Transcribe through Groq Whisper with a language hint (`fr`, `mg` or auto); split files longer than the provider limit.
- Output: segments with start and end times; the transcript is saved and can be ingested into RAG.
- Play the audio from any segment by clicking its timestamp.

### M10. Agent (P2)

- A simple loop: model, tool calls, results, until an answer or a limit of 6 steps.
- Starting tools: `search_documents` (RAG), `fetch_url`, `web_search` (if a free search API is available), `get_item`.
- Each step is shown in the UI (tool called, short result), so the reasoning is visible in the demo.
- Adding a tool means writing one Python function with a typed signature and a docstring.

### M11. Web app shell and PWA (P1)

- Pages: login, sign up, workspace switcher, items list, item detail, upload, ask (RAG chat), transcribe, members, settings.
- Responsive from 360 px wide; bottom navigation on mobile.
- PWA manifest, icon and installability; share target so a link can be shared into the app from a phone (P3).
- Typed API client generated from FastAPI's OpenAPI schema; loading, empty and error states on every page.
- French as the default UI language, with strings kept in one file so Malagasy can be added.

### M12. Admin and demo tools (P3)

- Seed script: one workspace, 3 users (one per role), 10 items, 3 documents, 1 transcript.
- "Reset demo data" button for admins.
- Health page showing database, Redis, storage and each AI provider as up or down.

## Pre-built features

We pre-build the two features most likely to match the problem (claim checker and verification board) to a demoable level, and three more to a working core flow. Each one is a thin layer over the generic modules, so it can be renamed, reshaped or dropped on day one.

| Feature | What the journalist does | Built on | Depth before 2 Nov |
| --- | --- | --- | --- |
| F1. Claim checker | Paste text, a link or a screenshot; get the checkable claims, evidence from sources with citations, and a suggested verdict | M4, M7, M8, M10 | Demoable |
| F2. Verification board | Track claims on a shared board: to check, in progress, verified, published; assign, comment, see changes live | M3, M5 | Demoable |
| F3. Interview to quotes | Record or upload audio; get a transcript, the key quotes and the claims to check, each with its timestamp | M9, M7 | Core flow |
| F4. Image check | Upload an image; see its metadata, duplicates already seen in the workspace, and reverse image search links | M4 | Core flow |
| F5. Verdict card | Turn a verified claim into a shareable image card and a short post in French or Malagasy | M3, M7 | Core flow |

### F1. Claim checker

- Input: text, a URL (Facebook post, article) or a screenshot. Screenshots go through OCR by a vision-capable model, if a free one is available.
- Step 1: extract the checkable claims (who, what, number, date) as a list the journalist can edit.
- Step 2: for each claim, search the workspace's sources (RAG) and the web (agent), and list evidence for and against, each with its citation.
- Step 3: suggest a verdict from a fixed scale: `true`, `misleading`, `false`, `unverifiable`, with a one-line reason. The journalist always confirms or changes it; the app never publishes a verdict on its own.
- Output: a claim item on the verification board, with its evidence attached.

### F2. Verification board

- Columns by status; cards show the claim, assignee, verdict and number of sources.
- Drag a card to change status; the change appears live for everyone in the workspace.
- Card detail: claim, evidence panel, comments, activity history.
- Filters by assignee, verdict, tag and date.

### F3. Interview to quotes

- Upload or record audio, transcribe (M9), then extract quotes and checkable claims with timestamps.
- Click a quote to play the audio at that moment; send a claim to F1 in one click.

### F4. Image check

- Show EXIF data (camera, date, location when present) and say clearly when it is missing.
- Perceptual hash to find the same or near-same image already in the workspace.
- One-click links to reverse image search engines.
- Show any signals as hints, never as proof: the app does not claim to detect AI-generated images with certainty.

### F5. Verdict card

- Template with the claim, the verdict, a short reason and the sources, rendered as a PNG sized for Facebook and WhatsApp.
- A draft post of 2 to 3 sentences generated in French or Malagasy, editable before copying.

## UI and design

The UI should look like a calm, trustworthy newsroom tool: one design system set up before any screen is built, so every screen added on day one looks finished automatically.

**Design system (built first, by 27 October)**

- Tokens as CSS variables in the Tailwind theme: colors, radius, spacing, shadows, light and dark mode.
- Palette: one neutral scale, one brand accent, and four verdict colors used everywhere the same way (`true` green, `misleading` amber, `false` red, `unverifiable` grey), always paired with a label or icon, never color alone.
- Typography: one sans-serif family (for example Inter or Geist) with a fixed scale; tabular numbers for dates and counts.
- Icons: one set only (lucide, which ships with shadcn/ui).
- shadcn/ui components themed once with the tokens; no one-off styles in pages.

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

- Product name and logo kept in one config file and one SVG, so they can change on day one to fit the real problem.
- A clean favicon and PWA icon, since the jury may see the app installed on a phone.

## Data model

Better Auth manages its own tables (`user`, `session`, `account`, `verification`, `jwks`) in the `auth` schema; our tables live in the `app` schema, all with UUID primary keys and `created_at` / `updated_at`.

| Table | Key fields | Notes |
| --- | --- | --- |
| `workspace` | id, name, slug |  |
| `membership` | workspace\_id, user\_id, role | Unique on (workspace\_id, user\_id); role in `admin`, `editor`, `journalist` |
| `invitation` | workspace\_id, token, role, expires\_at, used\_at | Link-based invites |
| `item` | workspace\_id, author\_id, type, title, body, status, tags (text\[\]), data (JSONB) | The generic domain object; GIN index on tags and data |
| `comment` | item\_id, author\_id, body |  |
| `activity` | workspace\_id, actor\_id, entity, entity\_id, action, diff (JSONB) | Written on every create, update, delete |
| `file` | workspace\_id, item\_id?, storage\_key, mime, size\_bytes, sha256, meta (JSONB) | EXIF and other metadata in meta |
| `source` | workspace\_id, kind (`pdf`, `url`, `text`, `transcript`), title, url?, file\_id?, author?, published\_at?, text | One row per ingested document |
| `chunk` | source\_id, workspace\_id, ord, text, page?, start\_s?, end\_s?, embedding vector(N), embed\_model | HNSW index on embedding; N set by the chosen model |
| `transcript` | file\_id, language, duration\_s, segments (JSONB) | Segments: start, end, text |
| `job` | workspace\_id, kind, status, progress, input (JSONB), result (JSONB), error |  |
| `conversation` / `message` | workspace\_id, user\_id / conversation\_id, role, content, citations (JSONB), tool\_calls (JSONB) | RAG chat and agent history |
| `ai_call` | provider, model, latency\_ms, tokens\_in, tokens\_out, ok, error | Gateway log, no prompt text stored |

The user id in `app` tables is the Better Auth user id (text), referenced without a foreign key across schemas.

## API specification

All FastAPI routes live under `/api/v1`, require `Authorization: Bearer <jwt>` except `/health`, and are scoped by `{ws}` = workspace id. Errors use one shape: `{"error": {"code": "...", "message": "..."}}`.

| Method | Path | Purpose | Role |
| --- | --- | --- | --- |
| GET | `/health` | Database, Redis, storage, AI providers status | public |
| GET | `/me` | Current user and memberships | any |
| POST | `/workspaces` | Create workspace | any |
| GET | `/workspaces/{ws}/members` | List members | any member |
| POST | `/workspaces/{ws}/invitations` | Create invite link | admin |
| POST | `/invitations/{token}/accept` | Join a workspace | any |
| PATCH / DELETE | `/workspaces/{ws}/members/{user}` | Change role, remove | admin |
| GET / POST | `/workspaces/{ws}/items` | List (filters, pagination) / create | any member / journalist+ |
| GET / PATCH / DELETE | `/workspaces/{ws}/items/{id}` | Read / update / delete | member / author or editor+ / editor+ |
| GET / POST | `/workspaces/{ws}/items/{id}/comments` | Comments | any member |
| GET | `/workspaces/{ws}/activity` | Activity log | any member |
| POST | `/workspaces/{ws}/files/upload-url` | Get a signed upload URL | journalist+ |
| POST | `/workspaces/{ws}/files` | Register an uploaded file | journalist+ |
| POST | `/workspaces/{ws}/sources` | Add a source (file or URL); starts an ingest job | journalist+ |
| GET | `/workspaces/{ws}/sources` | List sources | any member |
| POST | `/workspaces/{ws}/transcriptions` | Transcribe a file; starts a job | journalist+ |
| GET | `/workspaces/{ws}/jobs/{id}` | Job status and result | any member |
| POST | `/workspaces/{ws}/jobs/{id}/retry` | Retry a failed job | journalist+ |
| POST | `/workspaces/{ws}/search` | Semantic search over chunks | any member |
| POST | `/workspaces/{ws}/ask` | RAG answer with citations, streamed as SSE | any member |
| POST | `/workspaces/{ws}/agent` | Agent run, steps streamed as SSE | any member |
| POST | `/workspaces/{ws}/demo/reset` | Reset seed data | admin |

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
| Security | JWT verified on every API call; workspace isolation on every query; secrets only in environment variables; CORS limited to the web app's origin; upload type and size checked |
| Privacy | Only public test data while on free AI tiers; no prompt text stored in logs |
| Accessibility | Keyboard navigable, labeled form fields, contrast AA |
| Languages | UI in French; content in French and Malagasy supported end to end (ingest, search, transcription) |
| Maintainability | Typed end to end (Pydantic → OpenAPI → TypeScript); one copyable example per pattern; README with setup in under 15 minutes |
| Compliance | `THIRD_PARTY.md` lists every dependency and API with version and license, generated where possible |

## Repository, configuration and deployment

One monorepo, one `docker compose up` for local development, and one push to `main` deploys both services.

**Repository layout**

```
fanilo-base/
  apps/
    web/            Next.js app, Better Auth, PWA
      app/          routes and pages
      lib/auth.ts   Better Auth config + JWT plugin
      lib/api/      generated API client
    api/            FastAPI
      app/
        core/       config, db, security (JWT/JWKS), errors
        modules/    workspaces, items, files, sources, jobs, ai, rag, stt, agent
        realtime/   Socket.IO server and events
        workers/    ARQ tasks
      alembic/      migrations
      scripts/      seed.py, reembed_all.py
  packages/
    shared/         generated types, constants, i18n strings
  docker-compose.yml   postgres+pgvector, redis
  THIRD_PARTY.md
  README.md
```

**Environment variables**

| Variable | Used by | Example |
| --- | --- | --- |
| `DATABASE_URL` | web, api | Supabase Postgres connection string |
| `REDIS_URL` | api | `redis://localhost:6379` |
| `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL` | web | random 32 bytes; web URL |
| `AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE` | api | `https://<web>/api/auth/jwks` |
| `NEXT_PUBLIC_API_URL` | web | API base URL |
| `CORS_ORIGINS` | api | web URL |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `STORAGE_BUCKET` | api |  |
| `LLM_PROVIDERS` | api | `groq,gemini,nvidia` (order = fallback order) |
| `GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY` | api | one set per team member if needed |
| `LLM_MODEL_GROQ`, `LLM_MODEL_GEMINI`, `LLM_MODEL_NVIDIA` | api | model names chosen after testing |
| `EMBED_PROVIDER`, `EMBED_MODEL`, `EMBED_DIM` | api | set once, never changed during the event |
| `STT_PROVIDER`, `STT_MODEL` | api | Groq Whisper |
| `AI_CACHE` | api | `true` in development |

**Deployment**

- Web: Vercel Hobby, connected to the repo, root `apps/web`.
- API + in-process worker: Render free web service (Docker), or Railway trial; Redis on Render free key-value or Railway.
- Database and storage: Supabase free project; migrations run with Alembic on deploy.
- A GitHub Action regenerates the TypeScript client when the OpenAPI schema changes, and fails the build if types are out of date.
- Before the pitch: open the API health page 5 minutes ahead to wake the service, and check the Supabase project is active.

## Testing and demo readiness

We test the paths the demo will walk, not coverage numbers.

**Automated (run in CI on every push)**

- API: pytest on auth (401, 403), workspace isolation (user A cannot read workspace B), items CRUD, job lifecycle, gateway fallback with a mocked failing provider.
- RAG: a fixed set of 10 questions over 3 seed documents; each must return at least one correct citation.
- Web: Playwright smoke test: sign up, create workspace, create item, see it appear in a second browser.

**Manual checks before 1 November**

- [ ] Full flow on a real phone over mobile data.
- [ ] Embedding comparison: 20 French and Malagasy sentences, top-3 search accuracy per provider; choose one.
- [ ] Transcription quality on a French and a Malagasy voice note.
- [ ] Rate-limit behavior: 30 quick requests in a row do not crash the UI.
- [ ] Supabase project active, Render service awake, all keys loaded.

**Dry run (1 November)**

- Mock problem: "A viral Facebook post claims X; help a journalist verify it."
- 2 hours, all 4 members, on the deployed base. Note every blocker; fix the base, not the mock feature.

**Pitch kit**

- Slide template: problem, solution, live demo, impact, what was pre-built vs built during the event.
- Demo script with seed data loaded and a backup screen recording in case the network fails.

## Milestones

The core platform must work end to end by 27 October, the AI layer by 30 October, and nothing new is added after the 31 October freeze.

&#91;embedded content: build timeline · 23 Oct to 4 Nov 2026\]

P2 work starts only once P1 passes its acceptance checks; 1 November is kept for the dry run and fixes, not for new features.

## Risks and mitigations

The biggest risk is guessing the wrong features: time spent on F1 to F5 is lost if the real problem is elsewhere, so the generic modules come first and the guessed features stay shallow.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| The real problem does not match the pre-built features | Time spent on unused features | Generic modules first; F1 to F5 kept thin and built on M1 to M12, so their parts are reused anyway |
| UI polish eats the time needed for the core | Beautiful screens on a broken flow | Design system first, then polish only screens whose flow already works end to end |
| A free AI tier rate-limits or blocks us during the event | Features stop working | Three providers with automatic fallback; one key per member; response cache |
| Render service asleep at pitch time | 1-minute blank screen in front of the jury | Wake it 5 minutes before; backup screen recording |
| Supabase project paused after a week of inactivity | App down on the day | Use it daily; check it on 2 and 4 Nov morning |
| Weak Malagasy support in embeddings or transcription | Poor results on local content | Test on 25 Oct; pick the best provider; show French in the demo if Malagasy is weak |
| Venue internet slow or down | Cannot deploy or call AI | Phone hotspot as backup; local Docker setup works offline except AI calls |
| Better Auth and FastAPI JWT setup breaks | Nothing works across services | Built and tested first (P1); one integration test in CI |
| AI suggests a wrong verdict in the demo | Loss of trust with the jury | The journalist always confirms the verdict; evidence and citations always shown |
| Embedding provider changed mid-event | All vectors invalid | Provider fixed by config; `reembed_all` script ready |

## Open questions

- [x] Do the organizers allow work prepared before the event? Yes, confirmed with the IFM contact.
- [ ] Does the team registration page of the rules need to be submitted, or is the form enough?
- [ ] What prizes are offered, and does that change what the jury values?
- [ ] Which embedding provider wins the 25 October test: Gemini or NVIDIA?
- [ ] Is the Gemini free tier usable from Madagascar?
- [ ] Is a free vision model available for screenshot OCR in F1?
- [ ] Is a free web search API available for the agent's `web_search` tool, or do we leave it out?
- [ ] Render free or Railway trial for the API?

## Sources

- [FANILO hackathon rules (PDF)](https://homemade.mg/media/img/reglement_hackathon_fanilo.pdf)
- [Supabase pricing](https://supabase.com/pricing)
- [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)
- [Render free tier](https://render.com/docs/free)
- [Railway plans](https://docs.railway.com/pricing/plans)
