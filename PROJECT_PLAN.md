# Ornithopter 35B Web Chat — Project Plan

**Single source of truth for every implementation step.** Every prompt in `PROMPTS.md` references
sections of this file. Any agent implementing a step MUST read this file fully first, implement
ONLY that step, run the step's TEST GATE, and update the §Progress Tracker when the gate passes.

- **Workspace:** `/home/vk/Desktop/LLM_Chat_Interface` (path contains a space — always quote it)
- **Python:** uv-managed `.venv` at the workspace root (Python 3.11.14) — already created
- **Goal:** multi-user ChatGPT-style web app in front of a local llama.cpp server
  (Ornithopter 35B via Llama-GUI, OpenAI-compatible API), exposed through the owner's own
  Cloudflare tunnel. The app itself exposes exactly **one** local port (3001).

---

## 1. Overview & Constraints

- Multi-user: JWT accounts, per-user conversation history, token streaming (SSE), rate limiting,
  daily usage tracking. First registered user becomes admin (`FIRST_USER_IS_ADMIN`).
- The real LLM server is **not running during development**. `scripts/mock_llm_server.py` (port
  8001) is a stand-in OpenAI-compatible server used for all dev/E2E testing. When the owner's
  Llama-GUI server is up, set `LLM_API_URL=http://localhost:8000/v1` and `LLM_LIVE_TEST=1` to
  enable live tests. No code changes are needed to switch.
- Owner handles: Cloudflare tunnel, llama.cpp/Llama-GUI operation. Out of scope for all steps.
- Bare-metal deployment (no Docker): systemd **user** service + shell scripts.

## 2. Tech Stack

| Layer | Choice |
|---|---|
| API backend | Python 3.11 + FastAPI + uvicorn + sse-starlette (SSE) |
| Database | PostgreSQL (apt) + SQLAlchemy 2.0 async (asyncpg) + Alembic |
| Cache / limits | Redis (apt): slowapi rate-limit counters, model-list + health cache |
| Auth | PyJWT (HS256) access 60 min / refresh 7 days with rotation table + bcrypt |
| Rate limiting | slowapi with Redis storage |
| LLM client | httpx async — OpenAI-compatible, timeouts, 2× retry on 5xx/timeout only, `asyncio.Semaphore(LLM_MAX_CONCURRENT)` |
| Frontend | React + Vite + TypeScript + Tailwind CSS; zustand, axios, react-router-dom, react-markdown + remark-gfm, react-syntax-highlighter, recharts, date-fns |
| Frontend tests | vitest + @testing-library/react + Playwright (E2E) |
| Backend tests | pytest, pytest-asyncio (auto mode), pytest-cov, respx (mocked LLM), real Postgres (`llmchat_test`) + Redis (db 1) |
| Tooling | uv, ruff, git |

## 3. Ports & Services

| Service | Port | Notes |
|---|---|---|
| FastAPI app (API + built frontend, single origin) | 3001 | the ONLY port to tunnel |
| Vite dev server | 5173 | dev only; proxies `/api` → 3001 |
| llama.cpp / Llama-GUI (owner-managed) | 8000 | `http://localhost:8000/v1` |
| Mock LLM server | 8001 | `scripts/mock_llm_server.py` |
| PostgreSQL | 5432 | user/password `llmchat`/`llmchat`, DBs `llmchat`, `llmchat_test` |
| Redis | 6379 | db 0 = app, db 1 = tests |

## 4. Directory Layout

```
LLM Chat Interface/
├── .env                    # real secrets — gitignored
├── .env.example            # committed template of every var (§5)
├── .gitignore
├── pyproject.toml          # uv project; deps + [tool.pytest] + [tool.ruff]
├── PROJECT_PLAN.md         # this file
├── PROMPTS.md              # the 9 build prompts
├── README.md               # written in Step 9
├── backups/                # pg_dump output — gitignored (Step 9)
├── backend/
│   ├── alembic.ini         # script_location = alembic (run from backend/)
│   ├── alembic/
│   │   ├── env.py          # async engine, reads DATABASE_URL from app config
│   │   └── versions/
│   └── app/
│       ├── __init__.py
│       ├── main.py         # app factory: CORS, security headers (S9), /api router, SPA mount (S6)
│       ├── core/
│       │   ├── config.py   # pydantic-settings, loads root .env
│       │   └── logging.py  # JSON structured logging with request IDs
│       ├── api/
│       │   ├── deps.py     # get_db, get_redis, get_current_user
│       │   └── routes/
│       │       ├── health.py        # GET /health
│       │       ├── auth.py          # /api/auth/*           (S3)
│       │       ├── users.py         # /api/users/*          (S3, usage in S8)
│       │       ├── conversations.py # /api/conversations/*  (S5, export in S8)
│       │       └── chat.py          # /api/chat/*           (S5)
│       ├── db/
│       │   ├── base.py     # DeclarativeBase
│       │   ├── session.py  # async engine + sessionmaker
│       │   └── repositories.py
│       ├── models/         # user.py, conversation.py, message.py, api_usage.py, refresh_token.py
│       ├── schemas/        # pydantic: auth.py, user.py, conversation.py, message.py, chat.py
│       └── services/
│           ├── security.py # bcrypt + JWT + refresh rotation (S3)
│           ├── cache.py    # redis helpers (get/set with TTL)  (S4)
│           └── llm.py      # LLM gateway (S4)
├── tests/
│   ├── conftest.py         # event loop, app/client fixtures, DB+Redis test config
│   ├── test_health.py
│   ├── db/                 # S2
│   ├── auth/               # S3
│   ├── llm/                # S4
│   └── chat/               # S5
├── frontend/               # from S6
│   ├── package.json  vite.config.ts  tailwind.config.js  index.html
│   ├── playwright.config.ts         # webServer: mock LLM + backend(test DB) + vite
│   ├── e2e/                # auth.spec.ts (S6), chat.spec.ts (S7), profile.spec.ts (S8)
│   └── src/
│       ├── main.tsx  App.tsx
│       ├── components/     # Sidebar, ConversationList, MessageList, MessageBubble,
│       │                   # MarkdownContent, ChatInput, SettingsDrawer, ProtectedRoute,
│       │                   # ThemeToggle, Toast provider, ConfirmDialog, UsageChart (S8)
│       ├── pages/          # LoginPage, RegisterPage, ChatPage, ProfilePage
│       ├── stores/         # authStore.ts, chatStore.ts, uiStore.ts
│       ├── services/       # api.ts (axios + refresh-on-401), chat.ts (SSE via fetch stream)
│       ├── hooks/          # useChat, useDebounce
│       └── types/          # shared TS types mirroring §7 response shapes
└── scripts/
    ├── mock_llm_server.py  # S4
    ├── start_dev.sh        # S9: backend reload + vite dev
    ├── build_and_run.sh    # S9: build frontend + alembic upgrade + uvicorn :3001
    ├── backup_db.sh  restore_db.sh   # S9
    ├── smoke.sh  load_test.py        # S9
    └── systemd/llm-chat.service      # S9
```

**Import/run conventions (important, keep consistent):**
- The `app` package lives under `backend/`. Run the server as:
  `uv run uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 3001 [--reload]`
- pytest: `[tool.pytest.ini_options] pythonpath = ["backend"]`, `asyncio_mode = "auto"`, `testpaths = ["tests"]`
- Alembic runs from the `backend/` directory: `cd backend && uv run alembic upgrade head`
- Tests ALWAYS use `llmchat_test` + Redis db 1 (conftest.py overrides env before importing app config).

## 5. Environment Variables

`.env` lives at the workspace root, loaded by `backend/app/core/config.py` (pydantic-settings).
`.env.example` is committed with the same keys; `.env` is gitignored.

| Variable | Default / Example | Used in |
|---|---|---|
| `APP_HOST` | `127.0.0.1` | S1 |
| `APP_PORT` | `3001` | S1 |
| `APP_ENV` | `development` / `production` | S1 (S9 gates on it) |
| `DATABASE_URL` | `postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat` | S2 |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat_test` | S2 |
| `REDIS_URL` | `redis://localhost:6379/0` | S3+ |
| `TEST_REDIS_URL` | `redis://localhost:6379/1` | S2+ tests |
| `JWT_SECRET` | random 64-hex (generate once per machine) | S3 |
| `JWT_ALG` | `HS256` | S3 |
| `ACCESS_TOKEN_MINUTES` | `60` | S3 |
| `REFRESH_TOKEN_DAYS` | `7` | S3 |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` (comma-separated) | S1/S6 |
| `REGISTRATION_ENABLED` | `true` | S3 |
| `FIRST_USER_IS_ADMIN` | `true` | S3 |
| `RATE_LIMIT_CHAT_PER_MIN` | `20` | S5 |
| `RATE_LIMIT_API_PER_HOUR` | `120` | S5 |
| `RATE_LIMIT_LOGIN_PER_15MIN` | `5` | S3 |
| `MAX_MESSAGE_CHARS` | `16000` | S5 validation |
| `LLM_API_URL` | `http://localhost:8000/v1` (mock: `http://localhost:8001/v1`) | S4 |
| `LLM_API_KEY` | empty (omit Authorization header when empty) | S4 |
| `LLM_MODEL` | empty = first model from `/models` | S4 |
| `LLM_TIMEOUT_SECONDS` | `120` | S4 |
| `LLM_MAX_CONCURRENT` | `2` | S4 |
| `LLM_LIVE_TEST` | `0` (set `1` only when the real server is up) | S4+ |
| `MOCK_LLM_PORT` | `8001` | S4 |
| `MOCK_LLM_REPLY` | `This is a mock reply from the mock LLM server.` | S4 |
| `MOCK_LLM_LATENCY_MS` | `0` | S4 |
| `MOCK_LLM_CHUNKS` | `12` (streaming chunk count) | S4 |

## 6. Database Schema

All PKs are `UUID` (generated in Python with `uuid4`), timestamps are `timestamptz` (UTC, set in
Python via `default=datetime.utcnow`-equivalent using timezone-aware `now()`), `updated_at` is
touched on modification.

**users** — `id` PK · `email` varchar(320) UNIQUE NOT NULL (lowercased) · `username` varchar(50)
UNIQUE NOT NULL · `password_hash` varchar NOT NULL (bcrypt) · `is_active` bool default true ·
`is_admin` bool default false · `created_at` · `updated_at` · `last_login` nullable.
Index: unique(email), unique(username).

**refresh_tokens** — `id` PK · `user_id` FK→users ON DELETE CASCADE · `jti` varchar(36) UNIQUE
NOT NULL · `expires_at` timestamptz NOT NULL · `revoked` bool default false · `created_at`.
Index: unique(jti), index(user_id).

**conversations** — `id` PK · `user_id` FK→users ON DELETE CASCADE · `title` varchar(200)
default `'New Conversation'` · `model` varchar(100) nullable · `is_pinned` bool default false ·
`created_at` · `updated_at`.
Index: (user_id, updated_at desc). Soft-delete NOT used — hard delete cascades messages.

**messages** — `id` PK · `conversation_id` FK→conversations ON DELETE CASCADE · `role`
varchar(16) CHECK IN (`user`,`assistant`,`system`) · `content` text NOT NULL · `tokens` int
nullable (completion tokens when reported) · `metadata` jsonb default `'{}'` (temperature,
max_tokens, model, system_prompt fingerprint) · `created_at`.
Index: (conversation_id, created_at).

**api_usage** — `id` PK · `user_id` FK→users ON DELETE CASCADE · `date` date NOT NULL ·
`total_tokens` bigint default 0 · `total_requests` int default 0 · `created_at` · `updated_at`.
Index: UNIQUE (user_id, date) — rows are upserted/incremented per user per day.

## 7. API Specification

Global conventions:
- All `/api/*` routes (except `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`)
  require `Authorization: Bearer <access_token>`.
- Error envelope everywhere: `{"error": {"code": "...", "message": "..."}}`
  Codes: `validation_error`, `invalid_credentials`, `unauthorized`, `token_expired`,
  `invalid_token`, `duplicate_email`, `duplicate_username`, `registration_disabled`,
  `rate_limited`, `not_found`, `llm_unavailable`, `llm_rate_limited`, `forbidden`.
- List endpoints return `{"items": [...], "total": n}`.
- Foreign resources return 404 (never 403 — no existence leak). IDs are UUID strings; dates ISO 8601 UTC.

### Health (S1)
- `GET /health` → `200 {"status": "ok", "version": "0.1.0"}` (unauthenticated)

### Auth (S3)
- `POST /api/auth/register` `{email, username, password (≥8 chars)}` → `201` `AuthResponse` ·
  `409 duplicate_email/duplicate_username` · `403 registration_disabled`
- `POST /api/auth/login` `{username_or_email, password}` → `200 AuthResponse` ·
  `401 invalid_credentials` · `429 rate_limited` (5 per 15 min per IP+username)
- `POST /api/auth/refresh` `{refresh_token}` → `200 {"access_token","refresh_token","token_type":"bearer"}`
  (old refresh jti revoked, new one issued) · `401 invalid_token`
- `POST /api/auth/logout` `{refresh_token}` → `204` (revokes jti)
- `GET /api/auth/me` → `200 {"id","email","username","is_admin","created_at"}`

`AuthResponse` = `{"access_token","refresh_token","token_type":"bearer","user":{...user...}}`

### Users (S3, usage in S8)
- `GET /api/users/me` → user · `PUT /api/users/me` `{username}` → user ·
  `PUT /api/users/me/password` `{current_password, new_password (≥8)}` → `204` (invalidates
  nothing else; wrong current password → `401 invalid_credentials`) ·
- `GET /api/users/usage` → `200 {"days": [{"date": "2026-09-05", "tokens": 1234, "requests": 12}]}`
  (last 30 days, zero-filled)

### Conversations (S5; export S8)
- `GET /api/conversations?limit=50&offset=0&q=` → items:
  `{"id","title","is_pinned","model","message_count","created_at","updated_at"}`;
  pinned first then `updated_at` desc; `q` case-insensitive search over title + message content
- `POST /api/conversations` `{title?}` → conversation
- `GET /api/conversations/{id}` → `{"conversation": {...}, "messages": [Message...]}` (created_at asc)
- `PATCH /api/conversations/{id}` `{title?, is_pinned?}` → conversation
- `DELETE /api/conversations/{id}` → `204` (cascades messages)
- `GET /api/conversations/{id}/export?format=md|json` → file download
  (`Content-Disposition: attachment`); md = `# {title}` then `**User:**`/`**Assistant:**` blocks;
  json = `{"title","exported_at","messages":[...]}`

`Message` = `{"id","conversation_id","role","content","tokens","metadata","created_at"}`

### Chat (S5)
- `POST /api/chat/send` `{conversation_id?: uuid|null, content: string (≤MAX_MESSAGE_CHARS),
  temperature?: float 0–2, max_tokens?: int, model?: string|null}` →
  `200 {"conversation": {...}, "user_message": {...}, "assistant_message": {...}}`.
  Persists the user message, calls the LLM (non-streaming), persists the assistant message,
  increments `api_usage`, auto-titles a new conversation from the first ~60 chars of the first
  user message. LLM failure → `502 llm_unavailable` (user message IS kept; no assistant row).
- `POST /api/chat/stream` — same body, Server-Sent Events (sse-starlette), events in order:
  ```
  event: meta
  data: {"conversation_id": "...", "user_message": {…}}

  event: delta
  data: {"content": "token"}

  event: done
  data: {"assistant_message": {…}, "usage": {"prompt_tokens": 12, "completion_tokens": 344}}

  event: error
  data: {"error": {"code": "llm_unavailable", "message": "..."}}
  ```
- `GET /api/chat/models` → `{"models": ["..."]}` (Redis-cached 5 min)
- `GET /api/chat/status` → `{"status": "ok"|"unavailable", "model": "..."}` (Redis-cached 30 s)

### Rate limits (S5, via slowapi + Redis storage)
- Chat endpoints: `RATE_LIMIT_CHAT_PER_MIN` per user/min → `429` with `Retry-After`
- All other `/api`: `RATE_LIMIT_API_PER_HOUR` per user/hour
- Login: `RATE_LIMIT_LOGIN_PER_15MIN` per IP+username/15 min

## 8. LLM Service Contract (S4)

`backend/app/services/llm.py` — the ONLY module that talks to the LLM upstream.

```python
class LLMUnavailable(Exception): ...      # connect/timeout/5xx after retries
class LLMRateLimited(Exception): ...      # upstream 429
class LLMBadResponse(Exception): ...      # malformed payload/SSE

class LLMService:
    async def list_models() -> list[str]                  # GET {LLM_API_URL}/models, cache 5 min
    async def health() -> bool                            # list_models() succeeds, cache 30 s
    async def chat_completion(messages, *, model=None, temperature=0.7,
                             max_tokens=1024, system_prompt=None) -> LLMResult
    # LLMResult = {"content": str, "usage": {"prompt_tokens","completion_tokens"} | None,
    #              "model": str}
    def chat_completion_stream(...) -> AsyncIterator[LLMEvent]
    # LLMEvent = {"type": "delta"|"usage"|"done"|"error", ...}  (see §7 stream format)
```

Behavior: `system_prompt` prepended as a `system` message when non-empty; `model=None` →
`LLM_MODEL` or first from `/models`; Bearer header only when `LLM_API_KEY` non-empty; all HTTP
calls inside `asyncio.Semaphore(LLM_MAX_CONCURRENT)`; retries: 2 attempts, 0.5 s then 1 s
backoff, only on `TimeoutException`/`ConnectError`/HTTP 5xx (never 4xx, never 429).

## 9. Frontend Specification (S6–S8)

- **Routes:** `/login`, `/register`, `/chat` (protected), `/profile` (protected).
  Unauthenticated → redirect `/login`; authenticated on `/login|/register` → redirect `/chat`.
- **authStore** (zustand, persisted `localStorage["ornithopter-auth"]`):
  `{user, accessToken, refreshToken}`, actions: `login`, `register`, `logout`, `refresh`, `fetchMe`.
- **chatStore:** `{conversations, total, currentId, messages, isStreaming, streamingContent, error}`,
  actions: `loadConversations(q?)`, `openConversation(id)`, `newConversation()`, `send(content)`
  (always streams), `regenerate()`, `deleteConversation(id)`, `togglePin(id)`, `clearCurrent()`.
- **uiStore** (persisted `localStorage["ornithopter-ui"]`): `{sidebarOpen, settingsOpen, theme:
  "light"|"dark", settings: {model, temperature, maxTokens, systemPrompt}}`.
- **services/api.ts:** axios instance, base `/api`, request interceptor adds Bearer token;
  response interceptor: on 401 → try `/api/auth/refresh` once (single-flight) → retry original
  request; if refresh fails → `logout()` + redirect `/login`.
- **Streaming client (services/chat.ts):** `fetch("/api/chat/stream", {method:"POST", headers,
  body, signal})`, read the body `ReadableStream`, parse `event:`/`data:` lines (§7 format),
  dispatch into chatStore; `AbortController` for the stop button.
- **Vite dev:** `server.proxy = {"/api": "http://localhost:3001"}`. Production: backend mounts
  `frontend/dist` via StaticFiles at `/` with SPA fallback to `index.html` (single origin 3001).
- **Theming:** Tailwind `darkMode: "class"`; toggle persists via uiStore.
- **Vitest:** environment jsdom; unit tests for stores/interceptor/streaming reducer.
- **Playwright:** `webServer` array starts (1) mock LLM :8001, (2) backend :3001 with env
  `DATABASE_URL=TEST_DATABASE_URL`, `REDIS_URL=TEST_REDIS_URL`, `LLM_API_URL=http://localhost:8001/v1`,
  (3) vite dev :5173; specs run against :5173.

## 10. Conventions

- Errors: `{"error": {"code", "message"}}`; no stack traces in responses.
- Backend: full type hints, pydantic schemas for every request/response, ruff clean
  (`line-length = 100`, sensible default rule set).
- Frontend: TypeScript strict, no `any` in new code.
- Every step ends with the FULL test suite green (regression), not just new tests.
- Commits: one or more per step, message prefix `[step N]`.
- After each green gate, update the §Progress Tracker (status + date) and commit.

## 11. Step Breakdown & Test Gates

| # | Step | Deliverables | Test gate (must be green + shown) |
|---|---|---|---|
| 1 | Scaffold, tooling & services | pyproject+deps, layout, config, logging, `/health`, .env(.example), PG+Redis installed, `llmchat`/`llmchat_test` DBs, git init | pytest; `/health` 200 on :3001; ruff; `pg_isready`; `redis-cli ping` |
| 2 | Database layer | 5 models, Alembic (async) initial migration, session, repositories | `alembic upgrade head` on both DBs; FULL pytest; ruff |
| 3 | Auth & users | security.py, auth+users routes, deps, rate-limited login, refresh rotation | FULL pytest incl. auth negative cases + 429; ruff |
| 4 | LLM gateway + mock | llm.py (stream/non-stream/retry/semaphore), cache.py, mock_llm_server.py | FULL pytest (respx); live demo via curl through mock; ruff |
| 5 | Conversations + chat API | conversations CRUD+search, send, SSE stream, auto-title, usage, rate limits | FULL pytest incl. streaming/429/502; curl demo; ruff |
| 6 | Frontend scaffold + auth | Vite+TS+Tailwind, authStore, api.ts interceptor, login/register, protected /chat, SPA mount, dark mode | npm build; vitest; Playwright auth; FULL backend pytest |
| 7 | Chat UI | sidebar (grouping/search/pin/delete), markdown+highlight+copy, live streaming, settings drawer, shortcuts prep | vitest; Playwright chat vs mock LLM; FULL backend pytest; build |
| 8 | Profile, usage, export, polish | usage chart, profile mgmt, export md/json, toasts, banners, responsive, a11y | FULL backend pytest (usage/export); vitest; Playwright profile; build |
| 9 | Hardening & ops | security headers, body caps, systemd unit, start/build/backup/restore/smoke/load scripts, README | FULL suites; smoke.sh passes; load test <1% err; `systemd-analyze verify`; ruff |

## 12. Testing Strategy

- **Backend:** real services, isolated data — `llmchat_test` DB (schema fresh per session, per-test
  rollback/truncate) and Redis db 1. LLM upstream is respx-mocked in unit tests.
- **Live LLM tests:** skip unless `LLM_LIVE_TEST=1`; they hit the real `LLM_API_URL` and are
  marked so CI-style runs never need the model.
- **Frontend:** vitest units; Playwright E2E boots its own mock-LLM + backend (test DB) + vite.
- **Final:** `scripts/smoke.sh` (curl end-to-end) + `scripts/load_test.py` (50 virtual users,
  5 min mixed send/stream → p50/p95/p99, error rate, `LLM_MAX_CONCURRENT` tuning hint).

## 13. Runbooks

- **Dev (3 terminals):** mock LLM: `uv run python scripts/mock_llm_server.py` · backend:
  `uv run uvicorn --app-dir backend app.main:app --reload --port 3001` (env `LLM_API_URL=http://localhost:8001/v1` for mock) · frontend: `cd frontend && npm run dev` → open http://localhost:5173
- **Migrations:** `cd backend && uv run alembic upgrade head`
- **Production:** `scripts/build_and_run.sh` (builds frontend, migrates, runs uvicorn :3001);
  systemd user unit `scripts/systemd/llm-chat.service` → install to `~/.config/systemd/user/`.
- **Backup/restore:** `scripts/backup_db.sh` / `scripts/restore_db.sh` (pg_dump, keep 14).
- **Tests:** `uv run pytest -q` · `cd frontend && npx vitest run` · `cd frontend && npx playwright test`
- **Cloudflare Tunnel (owner):** tunnel `https://your.host` → `http://localhost:3001`. Single
  origin; SSE works through Cloudflare (no extra config). Set `APP_ENV=production`, real
  `JWT_SECRET`, `CORS_ORIGINS=https://your.host` (CORS is belt-and-braces; same-origin in prod).

## 14. Progress Tracker

Agents: update this table after each green gate.

| Step | Status | Date | Notes |
|---|---|---|---|
| 1 — Scaffold, tooling & services | done | 2026-09-05 | PostgreSQL 16 + Redis 7 installed (apt); role/db `llmchat`+`llmchat_test` created; uv deps + lock; app factory with CORS, JSON request-ID logging, `/health`. Gate green: pytest 5 passed, `/health` 200 on :3001, ruff clean, `pg_isready` + `redis-cli ping` OK |
| 2 — Database layer | done | 2026-09-05 | 5 models per §6 (UUID PKs, timestamptz, cascades, indexes), async engine/sessionmaker, Alembic async env (reads app config; `-x db=test`), initial migration `5aa2aa03baa3` applied to BOTH DBs, typed repositories + usage upsert. Gate green: alembic upgrade head OK ×2, FULL pytest 31 passed, ruff clean |
| 3 — Auth & users | done | 2026-09-06 | security.py (bcrypt + JWT access/refresh w/ jti+type claims), auth routes (register/login/refresh rotation/logout/me), users routes (profile, password change, 30-day zero-filled usage), error envelope everywhere, Redis-backed login limiter (5/15min per IP+identifier), FIRST_USER_IS_ADMIN. Gate green: FULL pytest 56 passed (limiter vs real Redis), ruff clean |
| 4 — LLM gateway + mock | done | 2026-09-06 | services/llm.py per §8 (list_models/health/chat_completion/stream, Bearer-if-set, §8 retry policy, Semaphore cap, SSE → typed delta/usage/done/error events, Redis cache 5min/30s via services/cache.py), scripts/mock_llm_server.py on :8001 (stream+non-stream, env-tunable), tests/llm/ with respx + real-Redis cache tests + LLM_LIVE_TEST-gated live tests. Gate green: FULL pytest 82 passed + 1 skipped (live), mock demo via curl and services/llm.py, ruff clean |
| 5 — Conversations + chat API | not started | — | |
| 6 — Frontend scaffold + auth | not started | — | |
| 7 — Chat UI | not started | — | |
| 8 — Profile, usage, export, polish | not started | — | |
| 9 — Hardening & ops | not started | — | |
