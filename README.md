# LLM Chat Interface

A multi-user, ChatGPT-style web app in front of a **local** llama.cpp server
(Ornithopter 35B via Llama-GUI, OpenAI-compatible API). Built to be exposed
through your own Cloudflare tunnel: the app is a **single origin** on
`http://localhost:3001` (API + built frontend together), so you only tunnel
one port. SSE streaming works through Cloudflare with no extra configuration.

- **Backend:** Python 3.11 · FastAPI · SQLAlchemy 2.0 async (asyncpg) · Alembic ·
  Redis (slowapi rate limits + caches) · PyJWT/bcrypt auth · SSE streaming
- **Frontend:** React + Vite + TypeScript · Tailwind CSS · zustand · recharts
- **Testing:** pytest (real Postgres + Redis, respx-mocked LLM) · vitest · Playwright
- **Tooling:** uv, npm, ruff

---

## Architecture

```
Browser ──> :3001 FastAPI (single origin)
             ├── /api/auth/*        register / login / refresh-rotation / logout / me
             ├── /api/users/*       profile, password, 30-day usage
             ├── /api/conversations/*  CRUD + search + export (md/json)
             ├── /api/chat/*        send, SSE stream, models, status
             ├── /health            liveness probe
             └── / (frontend/dist, SPA fallback)
                     │
                     ├── PostgreSQL :5432  (users, conversations, messages, api_usage, refresh_tokens)
                     ├── Redis :6379       (rate-limit counters, model/health caches)
                     └── LLM upstream      llama.cpp/Llama-GUI :8000 (real) or mock :8001
```

| Service | Port | Notes |
|---|---|---|
| FastAPI app (API + built frontend) | 3001 | the **only** port to tunnel |
| Vite dev server | 5173 | dev only; proxies `/api` → 3001 |
| llama.cpp / Llama-GUI (yours) | 8000 | `http://localhost:8000/v1` |
| Mock LLM server | 8001 | `scripts/mock_llm_server.py` |
| PostgreSQL | 5432 | role/db `llmchat`, test db `llmchat_test` |
| Redis | 6379 | db 0 = app, db 1 = tests |

Directory layout, database schema, API contract and env vars are specified in
[`PROJECT_PLAN.md`](PROJECT_PLAN.md) — the single source of truth.

---

## Environment variables

`.env` lives at the workspace root (gitignored); `.env.example` is the committed
template. Copy it and fill in real values:

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # → JWT_SECRET
```

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
| `LLM_API_URL` | `http://localhost:8000/v1` | OpenAI-compatible upstream (mock: `:8001/v1`) |
| `LLM_API_KEY` | *(empty)* | Bearer header sent only when set |
| `LLM_MODEL` | *(empty = first from `/models`)* | model override |
| `LLM_TIMEOUT_SECONDS` | `120` | upstream timeout |
| `LLM_MAX_CONCURRENT` | `2` | semaphore over all upstream calls |
| `LLM_LIVE_TEST` | `0` | `1` enables live tests against the real server |
| `MOCK_LLM_PORT` | `8001` | mock server port |
| `MOCK_LLM_REPLY` | `This is a mock reply…` | mock reply text |
| `MOCK_LLM_LATENCY_MS` | `0` | mock artificial latency |
| `MOCK_LLM_CHUNKS` | `12` | mock streaming chunk count |
| `UPLOAD_DIR` | `uploads` | attachment storage root |
| `UPLOAD_MAX_FILE_MB` | `100` | per-file upload cap |
| `DOC_MAX_CHARS` | `100000` | extracted document text limit |
| `LLM_VISION_ENABLED` | `true` | send images to the LLM (disable for text-only models) |
| `MOCK_VISION_REPLY` | `I can see the image.` | mock reply when an image part is present |

---

## Development

```bash
uv sync                          # backend deps into .venv
(cd frontend && npm install)     # frontend deps
./scripts/start_dev.sh           # mock LLM + backend + Vite dev server
# open http://localhost:5173
```

Manual equivalent (3 terminals):

```bash
uv run python scripts/mock_llm_server.py                       # :8001
LLM_API_URL=http://localhost:8000/v1 uv run uvicorn --app-dir backend app.main:app --port 3001 --reload
cd frontend && npm run dev                                     # :5173
```

Migrations (needed once before first run):

```bash
cd backend && uv run alembic upgrade head
```

When your real llama.cpp/Llama-GUI server is up, set in `.env`:
`LLM_API_URL=http://localhost:8000/v1`, your `LLM_API_KEY`, and
`LLM_LIVE_TEST=1` — live tests activate with no code changes.

## Production

```bash
./scripts/build_and_run.sh       # build frontend → migrate → serve on :3001
```

The backend serves `frontend/dist` at `/` with an SPA fallback, so the app is
one origin on port 3001. Set `APP_ENV=production` and a real `JWT_SECRET` in
`.env`. Hardening applied by the app: security headers
(`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`),
1 MB request-body cap, strict CORS, and no tokens/keys in logs.

## Backup & restore

```bash
./scripts/backup_db.sh                          # pg_dump → backups/, keeps 14 newest
./scripts/restore_db.sh backups/llmchat-YYYYmmdd-HHMMSS.dump
```

## systemd (user service)

```bash
mkdir -p ~/.config/systemd/user
cp scripts/systemd/llm-chat.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now llm-chat
journalctl --user -u llm-chat -f          # JSON logs live here
```

The unit applies migrations on start (`alembic upgrade head`) and restarts on
failure. Adjust `WorkingDirectory` if the project lives elsewhere. For the
service to keep running after logout: `loginctl enable-linger $USER`.

## Attachments

Users can attach images, videos, audio, and documents to chat messages (📎 in
the chat input, drag-and-drop, or clipboard paste). Files are stored under
`UPLOAD_DIR` (default `uploads/`, gitignored) and served only to their owner
through an authenticated endpoint. Images are downscaled once for the vision
prompt (`LLM_VISION_ENABLED=true` — your llama-server must have an mmproj
loaded), and PDF/DOCX/text documents are extracted to text so the model can
read them. Unbound uploads are cleaned up after 24 h.

## Testing

```bash
uv run pytest -q                       # backend (real llmchat_test DB + Redis db 1)
cd frontend && npx vitest run          # frontend units
cd frontend && npx playwright test     # E2E (boots mock LLM + backend + Vite itself)
cd frontend && npm run build           # type-check + production build
./scripts/smoke.sh                     # curl end-to-end against a throwaway stack
uv run python scripts/load_test.py --users 50 --duration 300   # needs running app + mock
systemd-analyze verify scripts/systemd/llm-chat.service
uv run ruff check .
```

## Load testing

`scripts/load_test.py` runs async virtual users doing mixed non-stream/stream
chat against the mock LLM and reports p50/p95/p99 latency, error rate and an
`LLM_MAX_CONCURRENT` tuning hint. Boot the app with **elevated rate limits**
and the test database (see the script docstring), then run it.

## Cloudflare Tunnel (yours)

The app is a single origin: point your tunnel at `http://localhost:3001` and
everything — API, SSE streaming, and the built frontend — passes through.

- Set `APP_ENV=production` and a real `JWT_SECRET` in `.env`.
- SSE works through Cloudflare with no extra configuration; the app's
  `/api/chat/stream` uses standard `text/event-stream`.
- CORS is belt-and-braces in production (same origin); set
  `CORS_ORIGINS=https://your.host` if you also want direct cross-origin use.
