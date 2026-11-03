# Checky

Checky (« La torche des rédactions », named FANILO until 2 Nov 2026; the repos keep the old name) is an
app for newsrooms, Madagascar first, to verify claims, track misinformation and spot AI-generated
content, made for the **FANILO Hackathon** (IFM + French Embassy press service, Antananarivo).
A journalist follows a rumour from its first appearance to a signed verdict, and Checky sends the
truth back down the same road (WhatsApp, Facebook, radio, SMS, a printed poster). The product
rules (knowing is not publishing, facts solid and readings dashed, the crew of checks, one kind
of account, « tout le monde peut vérifier ; seules les rédactions vérifiées publient ») are in
[`CLAUDE.md`](CLAUDE.md).

The hackathon problem is presented on **Mon 2 Nov 2026, 08:00**. Hand-in is **Tue 3 Nov, 20:00**
and the pitch is on **Wed 4 Nov**. Journalists follow each rumour from its first appearance to
a sourced, confirmed verdict in one shared workspace.

- Product requirements: [`docs/PRD.md`](docs/PRD.md), a copy of the [PRD Claude Doc](https://claude.ai/artifact/XFypCd4WmGLBm6pMbGMwrv) (keep both in sync)
- Design rules: [`apps/web/DESIGN.md`](apps/web/DESIGN.md) and [`apps/web/PRODUCT.md`](apps/web/PRODUCT.md)
- Pitch kit (deck, timed script, demo video, day-of checklist): [`docs/pitch/README.md`](docs/pitch/README.md)
- Full technical reference (architecture, API, status, next steps): [`CLAUDE.md`](CLAUDE.md).
  It is also what Claude Code reads, so keep it up to date when something changes.

## What is in here

```
apps/web/         Next.js 16 (App Router) + Tailwind v4 + shadcn/ui + Better Auth   → UI in French
apps/api/         FastAPI + SQLAlchemy (async) + Alembic + Socket.IO, Python 3.13     → business logic, AI
packages/shared/  TypeScript types generated from the API (do not edit src/api.d.ts by hand)
docs/PRD.md       What we are building and why
```

How the pieces talk:

- **Login** happens in the web app (Better Auth, email + password). The browser then gets a
  15-minute token and calls the API with it. The API checks the token against the web app.
- **One Postgres database, two schemas:** `better_auth` (users and sessions, owned by Better
  Auth) and `app` (everything else, owned by Alembic migrations).
- **Background jobs** run inside the API process from a Postgres table (no Redis).
- **Realtime** updates go over Socket.IO from the API.
- **AI** calls go through one gateway (`apps/api/app/core/ai.py`) that falls back from Groq to
  Gemini to NVIDIA (and Claude, once its key is set) when a provider fails. Every outside-service
  key (AI, voice, Tavily search, fact-checks, image detection) may be a comma-separated list; a key
  that hits its quota is set aside and the next one is used.
- **Agents** (Vérifier's deep search, the docked assistant's desk copilot and public guide) share
  one tool loop and one set of guardrails (`apps/api/app/modules/guard.py`); they search the web,
  Wikipedia and fact-checkers (`apps/api/app/core/websearch.py`). Dedicated web search uses
  Tavily when configured; keyless HTML search is best-effort and may fail on hosting IPs.
  See [`docs/WEB_SEARCH.md`](docs/WEB_SEARCH.md) for the free-plan setup and cost guards.
- **One kind of account.** Every member of a newsroom can do everything. Anything public (verdicts,
  seals, SMS, radio flashes) only leaves a newsroom that the Checky team has verified
  (`Workspace.publishes`; reviewers are the user ids in `PLATFORM_ADMINS`, page `/checky`).
- **Pictures leave the desk blurred.** Every uploaded image and video keyframe gets a single-frame,
  EXIF-free copy with faces blurred (OpenCV, `apps/api/app/core/media.py`); only that copy is shown
  or sent to reverse image search. ffmpeg only reads plain video containers.
- **Reading preferences:** A−/A+ and « Mode éco », per device (`apps/web/lib/prefs.ts`).
- **In production:** web on Vercel, API on Render, database and file storage on **Neon**
  (project `fanilo`, org 0nlydevs). Deployment is not set up yet.
- **Phone app:** [`0nlyDevs/fanilo-mobile`](https://github.com/0nlyDevs/fanilo-mobile) (Expo,
  React Native). A video, photo or link shared to FANILO from WhatsApp, Facebook or TikTok is
  uploaded, transcribed and checked through the same API. It signs in through Better Auth's Expo
  plugin (`apps/web/lib/auth.ts`, trusted scheme `fanilo://`).
- **Browser extension:** [`0nlyDevs/fanilo-extension`](https://github.com/0nlyDevs/fanilo-extension)
  checks selected text and public links/images in a side panel **without an account**. Public
  routes return published verdict candidates, external sources and image provenance hints, not
  new AI verdicts or private dossiers. Connection is optional for saving into a newsroom or using
  its authenticated analysis. It never confirms or publishes a verdict. Its README covers installation.
  Public text checks now prepare grounded queries with a bounded AI call, stream actual progress,
  distinguish search outages from empty results, and label source passages and possible reprises.
  The optional pixel-detector contract and evaluation gate are in [`docs/IMAGE_DETECTOR.md`](docs/IMAGE_DETECTOR.md).

## Access you need

Ask the project owner (TsioryJonathan) for:

| Access | Why | Needed for |
|---|---|---|
| GitHub org **0nlyDevs**, repo `fanilo-base` | code, CI | everything |
| Neon org **0nlydevs**, project **fanilo** | database and file storage, credentials | deploying, migrating production, M4 files |
| Groq / Gemini / NVIDIA API keys (or create your own free ones) | AI features | anything using AI |
| Vercel and Render (later) | deployment | demo |

You can run the whole app locally with only GitHub access. AI features answer with an error
until at least one AI key is set.

## Set up (about 10 minutes)

### 1. Install the tools

- **Node 26** and **npm** (npm only: never `pnpm`, `yarn` or `bun` in this repo)
- **[uv](https://docs.astral.sh/uv/)** for Python (it installs Python 3.13 for you)
- **PostgreSQL 17 or 18**, running locally
- **ffmpeg** (reads the soundtrack and tags of uploaded videos; without it only mp4/webm videos
  are transcribed, sent whole to Whisper). The API's Docker image needs it too.
- `git`, and the [GitHub CLI](https://cli.github.com/) (`gh auth login`) to clone the private repo

### 2. Clone and install

```bash
gh repo clone 0nlyDevs/fanilo-base
cd fanilo-base
npm install                       # web + shared packages
cd apps/api && uv sync && cd ../..  # API (creates apps/api/.venv)
```

### 3. Create the databases

```bash
createdb -U postgres fanilo        # the app
createdb -U postgres fanilo_test   # used by the API tests (wiped after each test)
```

### 4. Environment files

There are two, with the same content:

| File | Read by |
|---|---|
| `.env` (repo root) | the API |
| `apps/web/.env.local` | the web app |

Both are gitignored. **Never commit them.**

```bash
cp .env.example .env
# edit .env (see the table below), then:
cp .env apps/web/.env.local
```

| Variable | Local value | Where it comes from |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:<your password>@localhost:5432/fanilo` | your local Postgres |
| `BETTER_AUTH_SECRET` | any random string | `openssl rand -base64 32` |
| `BETTER_AUTH_URL` | `http://localhost:3000` | where the web app runs |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | where the API runs |
| `AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE`, `CORS_ORIGINS` | keep the example values | must point to the web app's address |
| `PLATFORM_ADMINS` | your own user id, to review newsroom requests | `GET /api/v1/me` → `id` once you have signed up (Better Auth user ids, comma-separated) |
| `STORAGE_ENDPOINT`, `STORAGE_REGION` | branch storage endpoint, `eu-central-1` | Neon console → project `fanilo` → Object storage → Connect |
| `STORAGE_ACCESS_KEY_ID`, `STORAGE_SECRET_ACCESS_KEY` | secret (`nak_…` / `nsk_…`) | same panel → Reveal credential |
| `STORAGE_BUCKET` | `uploads-dev` | `uploads` is the production bucket |
| `GROQ_API_KEY` | secret | [console.groq.com](https://console.groq.com/keys) |
| `GEMINI_API_KEY` | secret | [aistudio.google.com](https://aistudio.google.com/apikey) |
| `NVIDIA_API_KEY` | secret | [build.nvidia.com](https://build.nvidia.com/) |
| `CLAUDE_API_KEY` | secret, optional and paid; empty = Claude is skipped | [console.anthropic.com](https://console.anthropic.com/) |
| `ELEVENLABS_API_KEY` | secret, optional (the assistant's voice; without it the browser reads) | [elevenlabs.io](https://elevenlabs.io/app/settings/api-keys) |
| `GOOGLE_FACTCHECK_API_KEY` | optional: claim reviews from fact-checkers worldwide | a Google Cloud key with the Fact Check Tools API enabled |
| `LLM_MODEL_*` | empty = gateway default | set once we have picked models |
| `LLM_PROVIDERS` | `groq,gemini,nvidia,claude` | the order is the fallback order; put `claude` first to prefer it |
| `SEAL_SECRET` | any random string | `openssl rand -base64 32`; seals verdicts and communiqués (without it sealing answers 503) |
| `PUBLIC_WEB_URL` | `http://localhost:3000` | the public site, written into QR codes and `/v/<n>` short links |
| `SMS_GATEWAY_SECRET` | any random string | shared with the SMS gateway phone |
| `SMS_GATEWAY_URL` | optional Android phone gateway API base URL | the phone's LAN address or its gateway relay URL |
| `SMS_GATEWAY_USER`, `SMS_GATEWAY_PASSWORD` | optional basic-auth credentials | the gateway app's API settings |
| `SMS_GATEWAY_TOKEN` | optional bearer token instead of basic auth | the gateway app's API settings |
| `SMS_GATEWAY_SIGNING_KEY` | optional webhook HMAC key | the gateway app's webhook settings |
| `SMS_GATEWAY_SIM` | `0` for the phone's default SIM | choose `1`–`3` for a specific SIM |

Several teammates' keys can share one variable: `GROQ_API_KEY=gsk_a,gsk_b` (one free account each;
several accounts per person usually breaks the providers' terms).
| `AI_CACHE` | `true` | caches identical AI requests on disk so reloads don't burn quota |

If you run the web app on a port other than 3000, change it in **all** of `BETTER_AUTH_URL`,
`AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE` and `CORS_ORIGINS`.

### 5. Create the tables

```bash
psql -U postgres -d fanilo -c "CREATE SCHEMA IF NOT EXISTS better_auth"
cd apps/web && set -a && . ./.env.local && set +a && npx @better-auth/cli@latest migrate --config lib/auth.ts --yes && cd ../..
cd apps/api && uv run alembic upgrade head && cd ../..
```

(On fish shell, run the Better Auth line from bash: `bash -c '…'`.)

### 6. Run

Two terminals:

```bash
cd apps/api && uv run uvicorn app.main:app --reload --port 8000
cd apps/web && npx next dev -p 3000
```

Open http://localhost:3000, create an account, and create a workspace with
**"Données de démonstration"** ticked (the default) to get 8 example claims. API docs: http://localhost:8000/docs.

### SMS gateway phone

Install an Android SMS gateway app that supports the `POST /messages` API and `sms:received`,
`sms:sent`, `sms:delivered`, and `sms:failed` webhooks (the adapter currently speaks the
SMS Gateway for Android format). Put a local SIM in the phone, enable its API, and set
`SMS_GATEWAY_URL` and either the basic-auth credentials or bearer token above. Point each of its
four webhooks to `https://<API-address>/api/v1/public/sms/gateway` (the app requires HTTPS,
except for a localhost development bridge). Set the same signing key in the app and
`SMS_GATEWAY_SIGNING_KEY`; if the app cannot sign, append `?secret=<SMS_GATEWAY_SECRET>` to the
webhook URL. The API accepts inbound SMS through that webhook and pushes queued replies through
its Postgres worker, retrying temporary failures. The SMS simulator in Réglages exercises the
same message handling without a phone. With `SMS_GATEWAY_URL` empty, the authenticated polling
outbox remains available to another gateway.

In **Vérifier → Avant l'antenne**, paste a caller's claim or dictate it in French. The signed
verdicts of public newsrooms appear first, with a two-sentence radio line and the verification
number. A Malagasy radio line appears only after a journalist has reread and attested it;
Malagasy input can be typed. Fact-checkers' published reviews follow under their own names.

### Alert kit

In **Veille → Alertes**, open a high-risk alert and prepare its kit from the reports already
attached to it. The draft is dashed until a journalist reviews and approves it. The call list
uses only contacts belonging to that newsroom, even when another newsroom has shared a contact
in the directory. The Malagasy radio script is held until a journalist marks its exact text
as reread. Sending to the desk creates a live notice; partner radios with an SMS number enter
the existing gateway outbox, and fictional demo numbers are simulated. WhatsApp remains a link
the journalist opens manually. Radio numbers are masked in the desk's SMS list, and the short
WhatsApp link in the kit response hides the number and expires after ten minutes. A journalist
may close an alert only with a reason; a published verdict on a linked case also closes it.

`/flashs` serves today's signed verdicts as a printable, script-free HTML page under 20 KB,
with French and Malagasy radio lines and an English interface option. A partner radio's link
keeps its one-tap « Diffusé » form; a recorded newsroom voice note is linked when available.
The line uses the same verification number as the card, SMS and short link. No operator SMS or
voice-line provider is configured by this application.

## Everyday commands

Run these before pushing. CI runs the same checks and fails otherwise.

```bash
# API
cd apps/api
uv run ruff check . && uv run ruff format --check . && uv run pytest -q && uv run alembic check

# Web
cd apps/web
npx next typegen && npx tsc --noEmit && npx eslint .
```

| When you… | Run | Then commit |
|---|---|---|
| change an API route or its models | `npm run gen:api` (API must be importable, not running) | `packages/shared/` |
| add or remove a dependency (npm or uv) | `npm run third-party` | `THIRD_PARTY.md` (required by the hackathon rules) |
| change a table in `apps/api/app/core/models.py` | `cd apps/api && uv run alembic revision --autogenerate -m "what changed"` then `uv run alembic upgrade head` | the new file in `alembic/versions/` |
| add a page in `apps/web/app` | `npx next typegen` | nothing extra |
| auto-format Python | `cd apps/api && uv run ruff format .` | |

## Git workflow

- Work on **`dev`** (the default branch). `main` is the release branch; ask before pushing to it.
- Commit messages: [Conventional Commits](https://www.conventionalcommits.org/), in English, one
  line. Examples: `feat(api): add source upload`, `fix(web): keep board filters on reload`.
- Pull before you start (`git pull --rebase`). There is no branch protection, so a broken push
  breaks everyone: run the checks first.

## Adding a feature (recipes)

Code, comments and commits are in **English**; everything the user sees is in **French**.

### A new field on a claim

Claims are rows in `app.item` with a free JSON `data` column, so **no migration is needed**.
Send the field in `data` on create or `PATCH /workspaces/{ws}/items/{id}`; it is merged into the
existing data. Fields in use: `ref`, `first_seen_at`, `origin`, `verdict`, `verdict_suggested`,
`source_count`, `assignee_id`, `demo`.

### A new API route

1. Add a function to a module in `apps/api/app/modules/` (or a new module, then
   `api.include_router(...)` in `apps/api/app/main.py`).
2. Protect workspace routes with `AnyMember` from `app/core/access.py` (every member of a
   newsroom may do everything; there are no roles). Outsiders automatically get a 404. Anything
   that reaches the public must check `Workspace.publishes` (opted in and verified by Checky).
3. Raise errors with `ApiError(status, "code", "message")` so they leave as
   `{"error": {"code", "message"}}`.
4. Add a test in `apps/api/tests/` (`as_user("alice")` gives a logged-in client).
5. `npm run gen:api` so the web gets the new types.

### Calling the AI

```python
from app.core import ai

reply = await ai.complete(
    [{"role": "system", "content": "…"}, {"role": "user", "content": claim_text}],
    workspace_id=member.workspace_id,
    temperature=0.2,
)
reply.content, reply.provider
```

To give an agent a new tool, write `async def tool(ctx, **args) -> (summary, result)` and add it
to the agent's tool table (`TOOLS` in `agent.py`, `COPILOT_TOOLS` in `copilot.py`); a tool that
changes something only *proposes* it with `ctx.propose(...)`, and the person confirms it in the
widget. Run the loop with `guard=` so the answer is checked against what the tools returned.

For streaming to the browser, use `POST /api/v1/workspaces/{ws}/ai/stream` (Server-Sent Events:
`delta` events with `{text}`, then `done`). The AI only **suggests** a verdict
(`data.verdict_suggested`); a journalist always confirms it.

### Files and sources

Uploads never pass through the API: `lib/upload.ts` asks `…/files/upload-url` for a presigned
URL, PUTs the file to Neon storage, then calls `…/files/{id}/complete`, which creates a source and
queues `ingest_file`. In the UI, drop `<SourcesPanel ws={ws} itemId={id} />` anywhere to get
add-link, upload and the live list. Server side, read a file with `storage.read(key)`.
Videos (`mp4`, `webm`, `quicktime`, `3gpp`) become `video` sources: ffmpeg pulls out the soundtrack
for Whisper and `ffprobe` reads the tags, which are scanned for AI generators (Sora, Veo…).
Images and 4–6 keyframes per video also get a face-blurred safe copy; a failed transcription keeps
the video ready with its keyframes (re-run it with « Transcrire »). Deleting a source deletes its
frames and copies.
`PATCH …/sources/{id} {item_id}` attaches a source to a claim later; `link-check {source_id}`
checks an uploaded file on its transcript (the phone app's share flow).

### A slow task (transcription, ingestion…)

```python
from app.workers.queue import handler, JobContext, enqueue

@handler("my_task")
async def my_task(ctx: JobContext) -> dict:
    await ctx.progress(50)          # pushed live to the browser as job.progress
    return {"result": "…"}

job = await enqueue(db, member.workspace_id, member.user.id, "my_task", {"item_id": "…"})
```

The browser follows it with Socket.IO events `job.progress` / `job.done` / `job.failed`, or
`GET /workspaces/{ws}/jobs/{id}`. Failed jobs can be retried.

### A new screen

1. Add a route under `apps/web/app/(app)/w/[ws]/…/page.tsx`, then `npx next typegen`.
2. Fetch data with SWR and `api()` from `lib/api.ts` (it adds the token); see
   `components/claims/claims-view.tsx`.
3. Live updates: `useWorkspaceSocket(workspaceId, { "item.updated": … })` from
   `hooks/use-workspace-socket.ts`.
4. **Every** user-visible string goes in `apps/web/lib/i18n/fr.ts`.
5. Follow `apps/web/DESIGN.md` (one world, « Le signal clair », for the desk and the public pages).
   The rules that must not break:
   - citron `#d7f45b` only for the one action of a screen (`<Button variant="action">`), the active
     step and highlights; never a verdict, a status or decoration;
   - a verdict is always **icon + label**, never colour alone; an AI suggestion is a dashed outline,
     a confirmed verdict is solid;
   - status icons never use verdict colours;
   - reuse the numbered line (`components/flow/step-line.tsx`) wherever a rumour's progress shows.
6. The public, no-account pages live in `apps/web/app/(site)/` (`/`, `/verifies`, `/signaler`,
   `/suivi/[token]`, API `/api/v1/public/*`, only for newsrooms that opted in). Every rumour shown as
   an example on them is fictional and labelled.

Next.js 16 is newer than most tutorials and AI training data: read
`apps/web/node_modules/next/dist/docs/` before using an unfamiliar API.

## Troubleshooting

| Problem | Fix |
|---|---|
| The page reloads in a loop after a crash | stop the web server, `rm -rf apps/web/.next`, start again |
| Login works but every API call is 401 | the web address differs from `AUTH_ISSUER` / `AUTH_AUDIENCE` / `AUTH_JWKS_URL` in `.env` |
| CORS error in the browser | add the web address to `CORS_ORIGINS` and restart the API |
| `relation "user" does not exist` | the `better_auth` schema or its tables are missing: redo step 5 |
| Not sure which service is down | open **Réglages** in the app (or `GET /api/v1/health`): database, storage and each AI provider, with the missing env variable named |
| AI routes return 503 `ai_unavailable` | no AI key in `.env`, or every provider failed (see `app.ai_call`) |
| `npm` warns it blocked an install script | harmless |

## Web app on Vercel

Project **checky-mg** → https://checky-mg.vercel.app (the old `fanilo-mg.vercel.app` is gone since 3 Nov; `fanilo.vercel.app` belongs to someone
else), in the team *tsioryjonathan's projects*, Root Directory `apps/web`, Node 26.
`apps/web/vercel.json` runs the server code in Frankfurt (`fra1`), next to Neon.

Deploys go through Vercel's GitHub integration (Settings → Git, repo `0nlyDevs/fanilo-base`):
every push to `dev`, the production branch, goes live, and other branches and pull requests get
a preview URL. It does not wait for CI. Vercel's **free plan cannot deploy a private repository
owned by a GitHub organization** (neither from GitHub nor with the CLI), so this needs the team on
Pro (on a trial since 1 Nov); back on the free plan, deploys stop. Teammates whose commits should
deploy must be members of the Vercel team.

Deploy by hand: `npx vercel@latest deploy --prod`, **from the repository root** (`.vercelignore`
keeps `.env` files and the API out of the upload).

In the project's **Settings → Environment Variables** (Production):

| Variable | Value |
|---|---|
| `DATABASE_URL` | the Neon **direct** connection string (as `PROD_DATABASE_URL`, without quotes). Not the pooled one: `lib/auth.ts` sets `search_path` at connection start, which Neon's pooler refuses |
| `BETTER_AUTH_SECRET` | a new one: `openssl rand -base64 32` |
| `BETTER_AUTH_URL` | `https://checky-mg.vercel.app` |
| `NEXT_PUBLIC_API_URL` | `https://fanilo-api.onrender.com` (built into the page: redeploy after changing it) |

Before the first sign-in, in Neon's SQL editor: `DELETE FROM better_auth.jwks;`. Better Auth
encrypts its signing key with `BETTER_AUTH_SECRET`; a key left from an older secret cannot be
read and `/api/auth/token` fails. It makes a new one by itself; no account is lost.

Preview URLs only show the pages: the API accepts calls from the production address alone
(`CORS_ORIGINS`), and sign-in is tied to it (JWTs carry `BETTER_AUTH_URL` as issuer).

## API on Render

[`render.yaml`](render.yaml) describes the service: free plan, Frankfurt, Render's own Python 3.13
(no Docker; ffmpeg comes with Render's runtime). It deploys `dev` once CI is green on it, and its
build runs `alembic upgrade head`, so the production database is migrated before new code goes live.

First time:

1. Render → **New → Blueprint**, connect GitHub (org **0nlyDevs**), pick `fanilo-base`.
2. Fill in the values it asks for:
   - `DATABASE_URL`: the Neon **direct** connection string (the same as `PROD_DATABASE_URL`);
   - the web app's production address (Vercel) in `AUTH_ISSUER`, `AUTH_AUDIENCE` and
     `CORS_ORIGINS`, and the same address followed by `/api/auth/jwks` in `AUTH_JWKS_URL`;
   - `STORAGE_ENDPOINT`, `STORAGE_ACCESS_KEY_ID`, `STORAGE_SECRET_ACCESS_KEY` (bucket `uploads` is set);
   - `GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`.
3. Optional keys go in the service's **Environment** tab: `CLAUDE_API_KEY`, `ELEVENLABS_API_KEY`,
   `GOOGLE_FACTCHECK_API_KEY`.
4. Open `<service URL>/api/v1/health`: the database, storage and AI providers should be `up`.

Good to know:

- A free instance sleeps after 15 minutes without a visit and takes about a minute to wake;
  background jobs wait and resume. Open Réglages a few minutes before a demo.
- `FORWARDED_ALLOW_IPS=*` makes the API read the visitor's address from Render's proxy; without
  it every visitor would share one rate limit on the public routes.
- There is deliberately no health check path: `/api/v1/health` queries Neon and every AI
  provider, and polling it would keep the database awake.

## Production database (Neon)

Project **fanilo** in the Neon org **0nlydevs** (id `green-heart-84751490`, AWS Frankfurt,
Postgres 18, free plan). Set up with `vector`, `better_auth` and `app` at the current migration.

- Its connection string is `PROD_DATABASE_URL` in `.env` (ask the owner, or Neon console →
  project → Connect, with **connection pooling off**). The app itself never reads that variable.
- Render's build migrates production on every deploy. To migrate by hand:
  ```bash
  cd apps/api && DATABASE_URL="$PROD_DATABASE_URL" uv run alembic upgrade head
  ```
  and after a Better Auth upgrade, run the Better Auth CLI the same way.
- The database sleeps when idle; the first request after a pause takes a few seconds. Open
  Réglages a few minutes before a demo to wake it.
- Neon branches give a free copy of the database (for a risky migration or a demo snapshot).

## File storage (Neon Object Storage)

Same Neon project, S3-compatible, private buckets: **`uploads`** (production) and
**`uploads-dev`** (local development). The browser uploads and downloads through short-lived
presigned URLs issued by the API (`apps/api/app/core/storage.py`); files never pass through the
API and nothing is publicly readable.

- Storage belongs to a database **branch** (here `production`): its endpoint is in the branch's
  Connect panel, and a new Neon branch gets its own copy of the files.
- Never put the storage secret in the web app or the browser; only the API uses it.
