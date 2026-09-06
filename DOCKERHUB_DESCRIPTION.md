# LLM Chat Interface

A multi-user, ChatGPT-style web application for local LLM inference via llama.cpp (OpenAI-compatible API). Designed to run as a **single origin** on one port — perfect for Cloudflare Tunnel, ngrok, or reverse proxies.

![Architecture](https://raw.githubusercontent.com/Vksharma-72/LLM_Chat_Interface/main/docs/architecture.png)

---

## ✨ Features

| Category | Capabilities |
|----------|--------------|
| **Chat** | Token-by-token SSE streaming, stop/abort, regenerate, markdown + GFM + syntax highlighting with copy buttons |
| **Attachments** | Images, video, audio, PDF/DOCX/text via drag-drop, clipboard, or picker (100 MB/file); vision-capable model support; document text extraction |
| **Auth** | JWT with refresh-token rotation, per-user history, first user becomes admin, registration toggle |
| **Conversations** | Day-grouped sidebar, pinning, full-text search (titles + messages), markdown/JSON export |
| **Usage** | Daily token/request totals, 30-day charts, profile management with password change |
| **Rate Limiting** | Redis-backed per-user limits (chat/min, API/hour, login/15min) with friendly UI banners |
| **Polish** | Dark mode, toasts, skeleton loaders, responsive to 375px, keyboard shortcuts (Ctrl/Cmd+K search, Ctrl/Cmd+Shift+O new chat) |

---

## 🏗 Architecture

```
Browser ──> :3001 FastAPI (single origin: API + built frontend)
              ├── /api/auth/*          Register, login, refresh rotation, logout, /me
              ├── /api/users/*         Profile, password, 30-day usage
              ├── /api/conversations/* CRUD, search, export (MD/JSON)
              ├── /api/chat/*          Send, SSE stream, models, status
              ├── /api/attachments/*   Multipart upload + owner-scoped file serving
              ├── /health              Liveness probe
              └── /                    frontend/dist (SPA fallback)
                      │
                      ├── PostgreSQL :5432  (users, conversations, messages, attachments, api_usage, refresh_tokens)
                      ├── Redis :6379       (rate-limit counters, model/health caches)
                      └── LLM upstream      llama.cpp / Llama-GUI (any OpenAI-compatible) or mock server
```

**Single port to expose:** `3001` (API + SSE + frontend all together)

---

## 🚀 Quick Start with Docker Compose

```bash
# 1. Clone and configure
git clone https://github.com/Vksharma-72/LLM_Chat_Interface.git
cd LLM_Chat_Interface
cp .env.example .env

# 2. Generate JWT secret (required)
python3 -c "import secrets; print(secrets.token_hex(32))"
# → paste into .env as JWT_SECRET

# 3. If llama.cpp runs on the Docker host, set:
#    LLM_API_URL=http://host.docker.internal:8080/v1

# 4. Launch full stack (app + PostgreSQL 16 + Redis 7)
docker compose up -d --build

# 5. Open http://<host>:3001
#    First registered user becomes admin automatically
```

**Key ports:**
- `3001` — App (API + built frontend) — **only port to expose/tunnel**
- `5432` — PostgreSQL (internal)
- `6379` — Redis (internal)

---

## 🐳 Docker Image Details

**Base:** `python:3.12-slim` + multi-stage Node build  
**Runtime user:** Non-root `appuser` (UID 1000)  
**Writable path:** `/srv/llmchat/uploads` (volume-mounted)  
**Healthcheck:** `GET /health`  
**Entry point:** Runs Alembic migrations → starts Uvicorn on `0.0.0.0:3001`

### Environment Variables (configured via `.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_HOST` | `0.0.0.0` | Bind address |
| `APP_PORT` | `3001` | App port |
| `APP_ENV` | `production` | Environment mode |
| `DATABASE_URL` | (compose) | PostgreSQL connection |
| `REDIS_URL` | (compose) | Redis connection |
| `JWT_SECRET` | **required** | 64-char hex, generate once per deployment |
| `JWT_ALG` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_MINUTES` | `60` | Access token TTL |
| `REFRESH_TOKEN_DAYS` | `7` | Refresh token TTL (rotated, stored in DB) |
| `REGISTRATION_ENABLED` | `true` | Toggle open registration |
| `FIRST_USER_IS_ADMIN` | `true` | Promote first user to admin |
| `RATE_LIMIT_CHAT_PER_MIN` | `20` | Chat send/stream per user |
| `RATE_LIMIT_API_PER_HOUR` | `120` | Other `/api` calls per user |
| `RATE_LIMIT_LOGIN_PER_15MIN` | `5` | Login attempts per IP |
| `LLM_API_URL` | `http://localhost:8000/v1` | OpenAI-compatible upstream |
| `LLM_API_KEY` | *(empty)* | Bearer header (sent only when set) |
| `LLM_MODEL` | *(auto)* | Model override (empty = first from `/models`) |
| `LLM_TIMEOUT_SECONDS` | `120` | Upstream timeout |
| `LLM_MAX_CONCURRENT` | `2` | Semaphore over all upstream calls |
| `LLM_VISION_ENABLED` | `true` | Send images to vision-capable models |
| `UPLOAD_DIR` | `uploads` | Attachment storage root |
| `UPLOAD_MAX_FILE_MB` | `100` | Per-file upload cap |
| `DOC_MAX_CHARS` | `100000` | Extracted document text limit |

---

## 🔒 Security Hardening (Production)

- Security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`
- Request body size limits
- Strict CORS (same-origin in production; configurable via `CORS_ORIGINS`)
- No tokens/keys in logs
- Authenticated file serving (attachments only accessible to owner)
- Dangerous upload types rejected (HTML, executables)
- Unbound uploads cleaned after 24 hours

---

## 📦 Volumes

| Volume | Purpose |
|--------|---------|
| `pgdata` | PostgreSQL data (`/var/lib/postgresql/data`) |
| `uploads` | User attachments (`/srv/llmchat/uploads`) |

---

## 🧪 Testing & Development

```bash
# Backend tests (requires test DB + Redis)
uv run pytest -q

# Frontend unit tests
cd frontend && npx vitest run

# E2E tests (boots mock LLM + backend + Vite)
cd frontend && npx playwright test

# Type-check + production build
cd frontend && npm run build

# Lint
uv run ruff check .
```

---

## 📁 Project Structure

```
LLM_Chat_Interface/
├── backend/                 # FastAPI application
│   ├── app/
│   │   ├── api/            # Route handlers
│   │   ├── core/           # Config, security, database
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # Business logic (LLM, attachments, cache, rate-limit)
│   │   └── repositories/   # Data access layer
│   └── alembic/            # Migrations
├── frontend/               # React + Vite + TypeScript
│   ├── src/
│   │   ├── components/     # UI components
│   │   ├── pages/          # Route pages
│   │   ├── stores/         # Zustand state
│   │   └── hooks/          # Custom hooks
│   └── e2e/                # Playwright tests
├── scripts/                # Dev/prod utilities (backup, restore, load test, systemd)
├── tests/                  # Backend pytest suites
├── Dockerfile              # Multi-stage production image
├── docker-compose.yml      # Full stack (app + db + redis)
└── PROJECT_PLAN.md         # Single source of truth (schema, API, env, layout)
```

---

## 🌐 Cloudflare Tunnel / Reverse Proxy

The app is a **single origin** — point your tunnel at `http://localhost:3001`:

- SSE streaming (`/api/chat/stream`) works through Cloudflare with no extra config
- Set `APP_ENV=production` and a real `JWT_SECRET` in `.env`
- CORS is same-origin in production; set `CORS_ORIGINS=https://your.domain` if needed

---

## 🛠 Tech Stack

**Backend:** Python 3.11+ · FastAPI · SQLAlchemy 2.0 async (asyncpg) · Alembic · Redis (slowapi + caches) · PyJWT/bcrypt  
**Frontend:** React 18 · Vite · TypeScript · Tailwind CSS · Zustand · Recharts  
**Testing:** pytest · vitest · Playwright · uv · ruff  
**Infrastructure:** PostgreSQL 16 · Redis 7 · Docker Compose · systemd service

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🔗 Links

- **GitHub:** https://github.com/Vksharma-72/LLM_Chat_Interface
- **Issues:** https://github.com/Vksharma-72/LLM_Chat_Interface/issues
- **Project Plan (spec):** [PROJECT_PLAN.md](https://github.com/Vksharma-72/LLM_Chat_Interface/blob/main/PROJECT_PLAN.md)