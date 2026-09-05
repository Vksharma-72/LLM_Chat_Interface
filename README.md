# LLM Chat Interface

A multi-user, ChatGPT-style web app in front of a **local** llama.cpp server
(OpenAI-compatible API). Built to be exposed through your own Cloudflare
tunnel: the app is a **single origin** on `http://localhost:3001` (API + built
frontend together), so you only tunnel one port. SSE streaming works through
Cloudflare with no extra configuration.

## Features

- 💬 **Streaming chat** — token-by-token SSE replies, stop/abort, regenerate,
  markdown + GFM + syntax-highlighted code blocks with copy buttons
- 📎 **File attachments** — images, video, audio, PDF/DOCX/text documents via
  drag-and-drop, clipboard paste, or the 📎 picker (100 MB/file); images are
  sent to vision-capable models, documents are extracted to text
- 👤 **Accounts** — JWT auth with refresh-token rotation, per-user history,
  first user becomes admin, registration toggle
- 🗂 **Conversations** — sidebar grouped by day, pinned conversations,
  full-text search over titles *and* message content, markdown/JSON export
- 📊 **Usage tracking** — daily token/request totals, 30-day chart, profile
  management with password change
- 🚦 **Rate limiting** — Redis-backed per-user limits (chat/min, API/hour,
  login/15 min) with friendly banners
- 🌓 **Polish** — dark mode, toasts, skeleton loaders, responsive to 375 px,
  keyboard shortcuts (Ctrl/Cmd+K search, Ctrl/Cmd+Shift+O new chat)

**Stack:** Python 3.11 · FastAPI · SQLAlchemy 2.0 async (asyncpg) · Alembic ·
Redis (slowapi + caches) · PyJWT/bcrypt — React + Vite + TypeScript · Tailwind
CSS · zustand · recharts — pytest · vitest · Playwright · uv · ruff

## Requirements

| | |
|---|---|
| Python | 3.11+ with [uv](https://docs.astral.sh/uv/) |
| Node | 18+ with npm |
| PostgreSQL | 14+ (role/db `llmchat` + `llmchat_test`) |
| Redis | 6+ |

## Architecture

```
Browser ──> :3001 FastAPI (single origin)
             ├── /api/auth/*           register / login / refresh-rotation / logout / me
             ├── /api/users/*          profile, password, 30-day usage
             ├── /api/conversations/*  CRUD + search + export (md/json)
             ├── /api/chat/*           send, SSE stream, models, status
             ├── /api/attachments/*    multipart upload + owner-scoped file serving
             ├── /health               liveness probe
             └── / (frontend/dist, SPA fallback)
                     │
                     ├── PostgreSQL :5432  (users, conversations, messages,
                     │                      attachments, api_usage, refresh_tokens)
                     ├── Redis :6379       (rate-limit counters, model/health caches)
                     └── LLM upstream      llama.cpp / Llama-GUI (real) or mock :8001
```

| Service | Port | Notes |
|---|---|---|
| FastAPI app (API + built frontend) | 3001 | the **only** port to tunnel |
| Vite dev server | 5173 | dev only; proxies `/api` → 3001 |
| llama.cpp / Llama-GUI (yours) | any | set `LLM_API_URL`, e.g. `http://localhost:8080/v1` |
| Mock LLM server | 8001 | `scripts/mock_llm_server.py` |
| PostgreSQL | 5432 | role/db `llmchat`, test db `llmchat_test` |
| Redis | 6379 | db 0 = app, db 1 = tests |

Directory layout, database schema, API contract and env vars are specified in
[`PROJECT_PLAN.md`](PROJECT_PLAN.md) — the single source of truth.

## Quick start

```bash
# 1. Dependencies
uv sync                          # backend → .venv
(cd frontend && npm install)     # frontend

# 2. Environment
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # → JWT_SECRET in .env

# 3. Database (adjust role/db names to your setup)
sudo -u postgres psql -c "CREATE USER llmchat WITH PASSWORD 'llmchat'; \
  CREATE DATABASE llmchat OWNER llmchat; \
  CREATE DATABASE llmchat_test OWNER llmchat;"
cd backend && uv run alembic upgrade head && cd ..

# 4. Run (dev stack: mock LLM + backend + Vite)
./scripts/start_dev.sh           # → http://localhost:5173
```

Point the app at your real llama.cpp server by setting `LLM_API_URL` in
`.env` (e.g. `http://localhost:8080/v1`) and restarting the backend — no code
changes. `LLM_VISION_ENABLED=true` sends attached images to vision-capable
models (llama-server needs an mmproj loaded).

## Production

```bash
./scripts/build_and_run.sh       # build frontend → migrate → serve on :3001
```

The backend serves `frontend/dist` at `/` with an SPA fallback, so the app is
one origin on port 3001. Set `APP_ENV=production` and a real `JWT_SECRET` in
`.env`. Hardening applied by the app: security headers
(`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`),
request-body caps, strict CORS, and no tokens/keys in logs.

### systemd (user service)

```bash
mkdir -p ~/.config/systemd/user
cp scripts/systemd/llm-chat.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now llm-chat
loginctl enable-linger $USER             # keep running after logout
journalctl --user -u llm-chat -f         # JSON logs live here
```

The unit applies migrations on start and restarts on failure. Adjust
`WorkingDirectory` if the project lives elsewhere.

## Attachments

Users attach files via the 📎 picker, drag-and-drop, or clipboard paste.
Files are stored under `UPLOAD_DIR` (default `uploads/`, gitignored) and
served **only to their owner** through an authenticated endpoint — never as
public static URLs. Details:

- Images get a downscaled JPEG derivative used for the vision prompt
  (`LLM_VISION_ENABLED=true`); the original is never modified.
- PDF/DOCX/plain-text documents are extracted to text at upload so the model
  can read them (`DOC_MAX_CHARS` caps the injected text).
- Dangerous uploads (HTML, executables) are rejected; everything is streamed
  to disk in chunks and capped at `UPLOAD_MAX_FILE_MB`.
- Unbound uploads are cleaned up after 24 h by a background task.

## Testing

```bash
uv run pytest -q                       # backend (real llmchat_test DB + Redis db 1)
cd frontend && npx vitest run          # frontend units
cd frontend && npx playwright test     # E2E (boots mock LLM + backend + Vite itself)
cd frontend && npm run build           # type-check + production build
./scripts/smoke.sh                     # curl end-to-end against a throwaway stack
uv run ruff check .
```

Live tests against a running llama.cpp server: set `LLM_LIVE_TEST=1` in
`.env`, then `uv run pytest tests/llm/test_live.py -v`.

## Load testing

`scripts/load_test.py` runs async virtual users doing mixed non-stream/stream
chat against the mock LLM and reports p50/p95/p99 latency, error rate, and an
`LLM_MAX_CONCURRENT` tuning hint. Boot the app with **elevated rate limits**
and the test database (see the script docstring), then:

```bash
uv run python scripts/load_test.py --users 50 --duration 300
```

## Backup & restore

```bash
./scripts/backup_db.sh                          # pg_dump → backups/, keeps 14 newest
./scripts/restore_db.sh backups/llmchat-YYYYmmdd-HHMMSS.dump
```

## Environment variables

`.env` lives at the workspace root (gitignored); `.env.example` is the
committed template.

| Variable | Default / Example | Purpose |
|---|---|---|
| `APP_HOST` | `127.0.0.1` | bind address |
| `APP_PORT` | `3001` | app port |
| `APP_ENV` | `development` / `production` | environment |
| `DATABASE_URL` | `postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat` | app database |
| `TEST_DATABASE_URL` | `…/llmchat_test` | used by tests + Playwright |
| `REDIS_URL` | `redis://localhost:6379/0` | app Redis (db 0) |
| `TEST_REDIS_URL` | `redis://localhost:6379/1` | test Redis (db 1) |
| `JWT_SECRET` | random 64-hex | **generate once per machine** |
| `JWT_ALG` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_MINUTES` | `60` | access token TTL |
| `REFRESH_TOKEN_DAYS` | `7` | refresh token TTL (rotated, stored in DB) |
| `CORS_ORIGINS` | `http://localhost:5173,…` | comma-separated allowed origins |
| `REGISTRATION_ENABLED` | `true` | toggle open registration |
| `FIRST_USER_IS_ADMIN` | `true` | promote the first registered user |
| `RATE_LIMIT_CHAT_PER_MIN` | `20` | chat send/stream per user |
| `RATE_LIMIT_API_PER_HOUR` | `120` | all other `/api` per user |
| `RATE_LIMIT_LOGIN_PER_15MIN` | `5` | login attempts per IP+identifier |
| `MAX_MESSAGE_CHARS` | `16000` | per-message validation cap |
| `LLM_API_URL` | `http://localhost:8000/v1` | OpenAI-compatible upstream |
| `LLM_API_KEY` | *(empty)* | Bearer header sent only when set |
| `LLM_MODEL` | *(empty = first from `/models`)* | model override |
| `LLM_TIMEOUT_SECONDS` | `120` | upstream timeout |
| `LLM_MAX_CONCURRENT` | `2` | semaphore over all upstream calls |
| `LLM_VISION_ENABLED` | `true` | send images to the LLM (disable for text-only models) |
| `LLM_LIVE_TEST` | `0` | `1` enables live tests against the real server |
| `UPLOAD_DIR` | `uploads` | attachment storage root |
| `UPLOAD_MAX_FILE_MB` | `100` | per-file upload cap |
| `DOC_MAX_CHARS` | `100000` | extracted document text limit |
| `MOCK_LLM_PORT` | `8001` | mock server port |
| `MOCK_LLM_REPLY` | `This is a mock reply…` | mock reply text |
| `MOCK_VISION_REPLY` | `I can see the image.` | mock reply when an image part is present |
| `MOCK_LLM_LATENCY_MS` | `0` | mock artificial latency |
| `MOCK_LLM_CHUNKS` | `12` | mock streaming chunk count |

## Cloudflare Tunnel (yours)

The app is a single origin: point your tunnel at `http://localhost:3001` and
everything — API, SSE streaming, and the built frontend — passes through.

- Set `APP_ENV=production` and a real `JWT_SECRET` in `.env`.
- SSE works through Cloudflare with no extra configuration; the app's
  `/api/chat/stream` uses standard `text/event-stream`.
- CORS is belt-and-braces in production (same origin); set
  `CORS_ORIGINS=https://your.host` if you also want direct cross-origin use.
