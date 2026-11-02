# FANILO base — project handoff

Read this first. It is the single source of truth for how this repo works, what is done, and what comes next. The human onboarding guide is `README.md` (setup, env vars, access, recipes): update it too when setup, commands or conventions change. Product requirements live in `docs/PRD.md` (copy of the Claude Doc "FANILO Hackathon Base Platform – PRD", https://claude.ai/artifact/XyTrF9rjtMvjWksbUZKX2r). Keep both in sync when a decision changes.

## The project in one paragraph

A reusable base platform built **before** the FANILO Hackathon (IFM + French Embassy press service, Antananarivo). Teams of 4 build an app for journalists around information resilience: verifying claims, misinformation, AI-generated content. The exact problem is revealed by video on **Mon 2 Nov 2026, 08:00**; pre-built work is allowed (confirmed with the IFM contact) and must be declared in the pitch. Hard deadline **Tue 3 Nov 20:00**, 3-minute pitch **Wed 4 Nov**. Goal: on day one, a new feature goes from idea to deployed demo in under 2 hours.

Milestones from the PRD: **P1 core by 27 Oct**, **P2 AI layer by 30 Oct**, **freeze 31 Oct**, dry run 1 Nov.

## Working agreements (directives for Claude)

- **Language:** code, commits and docs in English. App UI in **French** (all strings in `apps/web/lib/i18n/fr.ts`; Malagasy later as a sibling file). Talk to the user in the language they write in (often French or English mixed).
- **Package manager: npm only.** Never pnpm or yarn. Monorepo = npm workspaces + Turborepo.
- **Commits:** Conventional Commits, English, **subject line only** (no body), **no Claude co-author / attribution trailer**. Example: `feat(api): add job queue`.
- **Autonomy:** commit and push to `dev` freely as work is verified, then move on to the next item. **Ask first** before: pushing/merging to `main`, changing GitHub repo settings, anything that costs money, deleting user data, or anything needing the user's credentials/accounts.
- **Branches:** `dev` is the default branch; `main` is release. CI runs on pushes and PRs to both. No branch protection.
- **Remote:** `origin` is HTTPS (`https://github.com/0nlyDevs/fanilo-base.git`, private, org 0nlyDevs) and authenticates through `gh` (token has `repo` + `workflow` scopes). Plain `git push` works.
- **No Docker for now.** Use the local Postgres. `docker-compose.yml` exists but is optional/unused.
- **Verify before claiming done:** run the tests/lint/typecheck, and for UI drive it in a real browser (Playwright, see "Testing the UI").
- **Look up current docs with Context7** (MCP, user scope) before using an API of Next.js 16, Better Auth, Tailwind v4, dnd-kit, FastAPI, etc.; training data is out of date for these.
- **Supabase MCP** is configured for this repo in `.mcp.json`, scoped to project `fanilo` (`mrtuhyupracdihvzlyam`, eu-central-1, org TsioryJonathan's Org). OAuth in the browser via `/mcp` → supabase → Authenticate. Use it for logs, advisors and SQL; ask before destructive operations.
- **Never put secrets in commits.** `.env` and `apps/web/.env.local` are gitignored and hold the real local values (DB password, auth secret). `.env.example` has placeholders only.

## Stack and layout

```
fanilo-base/
  apps/web/        Next.js 16.4 (App Router, Turbopack, cacheComponents) + Tailwind v4 + shadcn/ui (radix-nova) + Better Auth 1.7
  apps/api/        FastAPI + SQLAlchemy 2 (async, asyncpg) + Alembic + python-socketio; Python 3.13 via uv
  packages/shared/ Generated OpenAPI types (src/api.d.ts) + friendly aliases/constants (src/index.ts)
  scripts/         third_party.py (generates THIRD_PARTY.md)
  docs/PRD.md      Product requirements
  THIRD_PARTY.md   Generated; required by hackathon rules article 6
  .github/workflows/ci.yml
```

Key architecture decisions (all reflected in the PRD):

- **Auth:** Better Auth runs in Next.js (email + password, `jwt` plugin, 15-min EdDSA JWTs). The browser gets a token from `/api/auth/token` and calls FastAPI with `Authorization: Bearer`. FastAPI verifies against `/api/auth/jwks` (`app/core/security.py`). Issuer and audience = `BETTER_AUTH_URL` and must match `AUTH_ISSUER` / `AUTH_AUDIENCE` on the API.
- **One Postgres, two schemas:** `better_auth` (Better Auth tables, created by its CLI; not `auth`, which Supabase reserves and does not let us write to) and `app` (ours, Alembic). User ids in `app` are Better Auth ids (text), no cross-schema FK. `better_auth."user"` is declared read-only in `app/core/models.py` for name joins and excluded from Alembic.
- **No Redis.** Background jobs = `app.job` table claimed with `SELECT … FOR UPDATE SKIP LOCKED` by worker loops inside the API process (`app/workers/queue.py`, `JOB_WORKERS`, default 2). Add a job kind with `@handler("kind")`. Interrupted jobs are requeued on startup.
- **Realtime:** Socket.IO on the API (same port). Handshake requires the JWT; client emits `join` with a workspace id (membership checked). Events: `item.created|updated|deleted`, `comment.created`, `job.progress|done|failed`, `demo.reset`.
- **Generic item model:** `app.item` with `type`, `status`, `tags`, and a JSONB `data` merged on PATCH (new day-one fields need no migration). Claim fields currently in `data`: `ref` (FAN-0142), `first_seen_at` (ISO), `origin` (facebook|whatsapp|tiktok|radio|press|other), `verdict` (confirmed), `verdict_suggested` (AI), `source_count`, `assignee_id`, `demo`.
- **Statuses:** `to_check`, `in_progress`, `verified`, `published`. **Verdicts:** `true`, `misleading`, `false`, `unverifiable`. The AI only suggests; a journalist always confirms.
- **AI gateway** (`app/core/ai.py`): `await complete(messages, tools?, **params)` → `Completion` (content, tool_calls, provider, model, tokens, `.message`); `complete(..., stream=True)` → `Stream` of text deltas with `.completion` set at the end. Plain httpx against OpenAI-compatible `/chat/completions`. Providers follow `LLM_PROVIDERS`, a provider with no key is skipped, and default models live in `PROVIDERS` (override with `LLM_MODEL_*`). 429/5xx/timeouts are retried `AI_ATTEMPTS` times with backoff before falling back; other errors (bad key, 400) fall back straight away; a stream only falls back before its first chunk. Every attempt goes to `app.ai_call` (no prompt text). `AI_CACHE=true` caches answers on disk in `apps/api/.ai-cache/` (gitignored). `AiUnavailable` → 503 `ai_unavailable`. Tests mock providers with `ai._transport` (httpx.MockTransport) and `ai._sleep`.
- **Errors** leave the API as `{"error": {"code", "message"}}`. Outsiders get **404** (not 403) on a workspace.

## API (FastAPI, prefix `/api/v1`)

Implemented: `GET /health` (DB only so far) · `GET /me` (with memberships) · `POST /workspaces` · `GET /workspaces/{ws}/members` (with names/emails) · `PATCH|DELETE /workspaces/{ws}/members/{user}` (last-admin guarded) · `POST /workspaces/{ws}/invitations` · `POST /invitations/{token}/accept` (single use, 7 days) · items CRUD + filters `GET|POST /workspaces/{ws}/items`, `GET|PATCH|DELETE …/items/{id}` · `GET|POST …/items/{id}/comments` · `GET /workspaces/{ws}/activity?entity_id=` · `GET …/jobs/{id}`, `POST …/jobs/{id}/retry` · `POST /workspaces/{ws}/demo/reset` (admin; seeds 8 claims) · `POST /workspaces/{ws}/ai/complete` (JSON) and `POST …/ai/stream` (SSE: `delta` `{text}` events, then `done` with the full completion, or `error`).

Roles: journalist (create, edit own), editor (edit/delete all), admin (members, invites, demo reset). Dependencies `AnyMember`, `Editor`, `Admin` in `app/core/access.py`.

Not yet: files/sources (M4), RAG `/search` `/ask` (M8), transcription (M9), agent (M10), full `/health` (M12).

## Web app

Routes: `/connexion`, `/inscription` (auth) · `/` (redirects to first workspace, or onboarding with optional demo data) · `/w/[ws]/affirmations` (day grid + table; `?vue=tableau` = board) · `/w/[ws]/affirmations/[id]` (detail) · `/w/[ws]/membres` · `/invitation/[token]`. `proxy.ts` does the optimistic cookie redirect (Next 16 name for middleware).

Data: SWR + `lib/api.ts` (`api()` adds the JWT, caches it until 1 min before expiry). Realtime via `hooks/use-workspace-socket.ts` (refetches after reconnect). `hooks/use-workspace.ts` gives my role and a user-id → name map. Server-side session read: `lib/session.ts` (`'use cache: private'`, behind Suspense in `app/(app)/layout.tsx`).

**Next.js 16 rules** (this is not the Next.js from training data; read `node_modules/next/dist/docs/` before using an API):
- With `cacheComponents`, don't `await params` in pages outside Suspense; client views read them with `useParams()`, and `useSearchParams()` must sit inside `<Suspense>`.
- Middleware is `proxy.ts`; its `matcher` is read at startup (restart the dev server after changing it).
- Run `npx next typegen` after adding routes (route types like `LayoutProps`/`PageProps`).

## Design system

Visual world **"Grille d'antenne"** (Malagasy radio programme grid), chosen through the Impeccable skill. Documented in `apps/web/DESIGN.md` (+ `.impeccable/design.json`), product truth in `apps/web/PRODUCT.md`, direction contract in `apps/web/.impeccable/surfaces/app-app.md`. For any new screen: use the `impeccable` skill, follow DESIGN.md, run `impeccable detect --json app components` (from `apps/web`).

Rules that must not break:
- Deep antenna green rail `#0f3b36` on cool white `#f4f6f5`; **signal yellow `#f2c230` only for "maintenant", focus and selection** — never buttons, verdicts or status.
- **Verdicts are never colour alone:** always icon + label. Each verdict has fill / on / soft / ink tokens (contrast ≥ 4.5:1). AI suggestion = dashed outline on soft ground; unchecked = outline on card.
- **Status is not truth:** status uses ink lucide icons (CircleDashed, Timer, ShieldCheck, Radio), never verdict colours.
- Barlow Condensed (tabular) for hours, times, durations and FAN refs; Public Sans for everything else.
- Signature: the **day grid** — each claim is a block from first-seen to now, to scale; focus lifts one and dims others to 40%; phone shows a 6-hour window opened on "maintenant". Reused as the airtime strip (detail) and hairline on board cards.

## Local setup and commands

Prereqs on this machine: Node 26 / npm 12, Python 3.13 via uv, local PostgreSQL 18 (user `postgres`, password in `.env`). Databases: `fanilo` (app) and `fanilo_test` (tests). **pgvector is not installed locally** (needed for M8; Supabase has it).

```bash
npm install                                   # root, installs all workspaces
cd apps/api && uv sync                        # API deps
# first time on a new database (Better Auth writes into the `better_auth` schema, which must exist):
psql "$DATABASE_URL" -c "CREATE SCHEMA IF NOT EXISTS better_auth"
cd apps/web && set -a && . ./.env.local && set +a && npx @better-auth/cli@latest migrate --config lib/auth.ts --yes
cd apps/api && uv run alembic upgrade head    # creates the app schema + tables

# run (two terminals)
cd apps/api && uv run uvicorn app.main:app --reload --port 8000
cd apps/web && npx next dev -p 3000
```

If the web runs on another port, set the same origin everywhere: `BETTER_AUTH_URL` (web) and `AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE`, `CORS_ORIGINS` (API).

Checks (same as CI):
```bash
cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run pytest -q && uv run alembic check
cd apps/web && npx next typegen && npx tsc --noEmit && npx eslint .
npm run gen:api        # after any API schema change; commit packages/shared
npm run third-party    # after any dependency change; commit THIRD_PARTY.md
```
New migration: `cd apps/api && uv run alembic revision --autogenerate -m "…"` then `upgrade head`.

API tests use `fanilo_test` (derived from `DATABASE_URL`, or `TEST_DATABASE_URL`), run with `JOB_WORKERS=0` and run jobs via `queue.run_once()`. The test conftest creates a stand-in `better_auth."user"` table.

### Testing the UI
Playwright browsers are installed in `~/.cache/ms-playwright`. Drive flows with `uv run --with playwright python -I script.py`, launching with `executable_path` set to the cached `chromium-*/chrome-linux*/chrome`. Sign up throwaway users with generated `*@fanilo.test` emails. Screenshots go to `apps/web/.impeccable/review/` (gitignored). Note: full-page captures reset the grid's horizontal scroll; use viewport captures for the phone grid.

### Gotchas
- If the dev server reloads the page in a loop after a crash, stop it and `rm -rf apps/web/.next` (regenerable cache).
- Don't use `pkill -f next` from a shell whose command line or cwd contains "next"/the web folder: it kills the shell. Kill by port (`ss -ltnp | grep :3000`).
- The API runs without `--reload` in background tests: restart it after API code changes.
- `npm` blocks some install scripts (unrs-resolver); harmless.

## Status (24 Oct 2026, after M7)

Done, on `dev`, CI green:
- M1 auth + roles, M2 workspaces/members/invitations, M3 items/comments/activity, M5 realtime, M6 Postgres job queue, M7 AI gateway (mocked tests only; no real keys yet)
- Web: design system, auth pages, onboarding, app shell, claims day grid + table, claim detail (verdict confirm, comments, history, assignee, status), **F2 verification board** (drag/touch/keyboard + "Déplacer vers…"), members screen + invitation links, PWA manifest + icons
- CI: API tests on pgvector Postgres, web typecheck/lint, generated API types and THIRD_PARTY.md up to date
- **Supabase project `fanilo`** set up (24 Oct): `vector` 0.8.2 in schema `extensions`, schemas `app` + `better_auth` with all tables at the current Alembic head, private bucket `uploads` (50 MB per file), `app`/`better_auth` revoked from `anon`/`authenticated`, security advisor clean. Migrations so far were applied through the MCP from the local schema; once `DATABASE_URL` for Supabase is known, run `alembic upgrade head` against it directly instead.

## Next steps (in order)

Not blocked:
1. **M12:** `/health` also reports storage and each AI provider; a health page in the web app; admin "reset demo data" button (endpoint exists).

Blocked on the user:
- **Supabase secrets** (the MCP cannot read them): the secret/service key (Dashboard → Project Settings → API keys) into `SUPABASE_SERVICE_KEY`, and the database password for a Supabase `DATABASE_URL` (use the session pooler string for Render/Vercel). `SUPABASE_URL` is already in `.env`. → M4 files/sources (signed upload URLs, EXIF, trafilatura for URLs), then M8 RAG.
- **AI keys** (Groq, Gemini, NVIDIA in `.env`) → real calls, M9 transcription (Groq Whisper), F1 claim checker, F3 interview to quotes, F5 verdict card.
- **Embedding test** (planned 25 Oct): ~20 French + ~20 Malagasy sentences, pick Gemini vs NVIDIA by top-3 accuracy; set `EMBED_PROVIDER/MODEL/DIM` once.
- **Deployment:** Vercel (root `apps/web`) and Render free (Docker, API + in-process workers); Supabase as the database.

Open questions (from the PRD): team registration page needed? prizes? Gemini free tier usable from Madagascar? a free vision model for screenshot OCR? a free web search API for the agent? Render free vs Railway trial?
