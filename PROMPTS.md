# PROMPTS.md — Step-by-Step Build Prompts

Copy-paste **one prompt at a time**, in order 1 → 9, into ZCode (this session or a fresh one —
each prompt is self-contained because it starts by reading `PROJECT_PLAN.md`).

## How to use

1. Paste **Prompt 1** exactly as-is. The agent will implement ONLY that step and run its
   **TEST GATE**, showing real output (pytest, curl, ruff, browser tests…). If anything fails,
   the agent fixes it and re-runs the gate until green — nothing else gets built meanwhile.
2. Review the result (quickly run the app yourself if you like). Then paste **Prompt 2**.
3. Repeat through **Prompt 9**. After each green gate the agent updates the Progress Tracker in
   `PROJECT_PLAN.md`, so any session can see where the build stands.
4. When your real llama.cpp/Llama-GUI server is running, set in `.env`:
   `LLM_API_URL=http://localhost:8000/v1`, your `LLM_API_KEY`, and `LLM_LIVE_TEST=1` — live
   tests activate with no code changes. Until then everything runs on the mock server (:8001).
5. The Cloudflare tunnel stays yours: the app is a single origin on `http://localhost:3001`
   (API + built frontend together), so you only tunnel that one port. Step 9 leaves a section
   for it in the README.

**If a session loses context:** just paste the next prompt — the agent reads `PROJECT_PLAN.md`
(§Progress Tracker shows current state) and `PROMPTS.md` first.

---

## Prompt 1 — Scaffold, tooling & local services

```
Read PROJECT_PLAN.md and PROMPTS.md in this workspace first. Work only in "/home/vk/Desktop/LLM Chat Interface" (uv-managed .venv, Python 3.11). Implement ONLY Step 1.

1. Local services (bare metal): install PostgreSQL and Redis via apt (if sudo needs a password, give me the exact commands to run myself, then verify and continue). Create role/db: CREATE USER llmchat WITH PASSWORD 'llmchat'; CREATE DATABASE llmchat OWNER llmchat; CREATE DATABASE llmchat_test OWNER llmchat;. Verify pg_isready and redis-cli ping.
2. Create pyproject.toml (uv) and install into .venv: fastapi, uvicorn[standard], httpx, sse-starlette, pydantic-settings, sqlalchemy[asyncio], asyncpg, alembic, redis, pyjwt, bcrypt, slowapi; dev: pytest, pytest-asyncio, pytest-cov, ruff, respx, asgi-lifespan.
3. Backend layout per PROJECT_PLAN.md §Directory layout: backend/app/{main.py, core/config.py, core/logging.py, api/deps.py, api/routes/health.py, db/, models/, schemas/, services/}, scripts/, tests/.
4. core/config.py (pydantic-settings) loading every var from PROJECT_PLAN.md §Environment Variables; create .env.example and .env (random JWT_SECRET; DATABASE_URL=postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat; TEST_DATABASE_URL=…/llmchat_test; REDIS_URL=redis://localhost:6379/0; LLM_API_URL=http://localhost:8000/v1; APP_PORT=3001; CORS_ORIGINS=http://localhost:5173).
5. App factory: CORS middleware, JSON structured logging with request IDs, GET /health → {"status":"ok"}. tests/conftest.py + tests/test_health.py. .gitignore; git init; initial commit.

TEST GATE — run all, show outputs, fix until green: (a) uv run pytest -q; (b) uvicorn boots on :3001 and GET /health = 200; (c) uv run ruff check .; (d) pg_isready and redis-cli ping. Do NOT implement Steps 2–9. When done, update the §Progress Tracker in PROJECT_PLAN.md.
```

## Prompt 2 — Database layer

```
Implement ONLY Step 2 (database layer) per PROJECT_PLAN.md §Database Schema. Postgres is installed and running.
1. models/: User, Conversation, Message, ApiUsage, RefreshToken exactly per schema — UUID PKs, timestamps, indexes (users.email unique, conversations.user_id, messages.conversation_id, unique (user_id,date) on api_usage), FK cascade delete conversation→messages.
2. db/session.py async engine + sessionmaker (DATABASE_URL); db/base.py.
3. Alembic async setup reading DATABASE_URL from .env; autogenerate initial migration; run alembic upgrade head against BOTH llmchat and llmchat_test.
4. db/repositories.py typed async CRUD: users (get_by_email/username), conversations (list per user — paginated, pinned first, updated_at desc), messages (ordered list, append), usage (increment per user/day), refresh tokens (create/revoke/get).
5. tests/db/ run against TEST_DATABASE_URL (fresh schema per session, rollback per test): round-trips, constraints, cascades, repository behavior.

TEST GATE (show outputs): alembic upgrade head OK on both DBs; FULL uv run pytest -q green; ruff clean. No Steps 3–9. When done, update the §Progress Tracker in PROJECT_PLAN.md.
```

## Prompt 3 — Authentication & users

```
Implement ONLY Step 3 (auth & users) per PROJECT_PLAN.md §API Specification.
1. services/security.py: bcrypt hash/verify; PyJWT access (ACCESS_TOKEN_MINUTES) + refresh (REFRESH_TOKEN_DAYS) tokens with jti/type claims; refresh rotation stored in refresh_tokens.
2. api/routes/auth.py: POST /api/auth/register (email/username/password≥8; 409 duplicates; honor REGISTRATION_ENABLED), /login (5/15min per IP+username via Redis), /refresh (rotate; reject revoked), /logout (revoke), GET /api/auth/me. FIRST_USER_IS_ADMIN promotes first registered user.
3. api/routes/users.py: GET/PUT /api/users/me, PUT /api/users/me/password (requires current password), GET /api/users/usage.
4. api/deps.py: get_current_user (Bearer JWT → 401), get_db, get_redis. All errors use {"error":{"code","message"}}.
5. tests/auth/: full flow register→login→me→refresh→logout; wrong password 401; duplicate email 409; expired/garbage token 401; revoked refresh 401; login rate-limit 429; password change then re-login; registration disabled blocks register.

TEST GATE (show outputs): FULL uv run pytest -q green (limiter tested against real Redis); ruff clean. No Steps 4–9. When done, update the §Progress Tracker in PROJECT_PLAN.md.
```

## Prompt 4 — LLM gateway + mock server

```
Implement ONLY Step 4 (LLM gateway + mock server) per PROJECT_PLAN.md §LLM Service Contract. No chat endpoints yet.
1. services/llm.py: async httpx client for OpenAI-compatible llama.cpp at LLM_API_URL — list_models(), chat_completion(messages, model, temperature, max_tokens, system_prompt), chat_completion_stream(...) async generator. Bearer LLM_API_KEY only if set; timeout LLM_TIMEOUT_SECONDS; retry 2× with backoff on timeouts/5xx only, never 4xx; asyncio.Semaphore(LLM_MAX_CONCURRENT) around requests; parse SSE "data:" lines incl. [DONE] → typed events {"type":"delta"|"usage"|"done"|"error"}; extract token usage when present.
2. Redis caching: model list 5 min, upstream health 30 s; unreachable → "llm_unavailable" state.
3. scripts/mock_llm_server.py: FastAPI on MOCK_LLM_PORT (8001) implementing /v1/models + /v1/chat/completions (streaming + non-streaming, env-tunable reply text and latency) — the LLM for all dev/E2E until your real server exists.
4. tests/llm/ (respx): success, timeout→retry→success, 429 passthrough, malformed SSE, concurrency cap, usage extraction, health cache. Live tests run only when LLM_LIVE_TEST=1.

TEST GATE (show outputs): FULL uv run pytest -q green; boot scripts/mock_llm_server.py and demo chat_completion + streaming through services/llm.py via curl; ruff clean. No Steps 5–9. When done, update the §Progress Tracker in PROJECT_PLAN.md.
```

## Prompt 5 — Conversations + chat API

```
Implement ONLY Step 5 (conversations + chat API) per PROJECT_PLAN.md §API Specification.
1. api/routes/conversations.py: GET /api/conversations (?q search over titles+message content, pagination, pinned first), POST create, GET /:id with messages, PATCH /:id (title, is_pinned), DELETE /:id (cascade). Owner-scoped — foreign ids return 404.
2. api/routes/chat.py: POST /api/chat/send {conversation_id?, content, temperature?, max_tokens?, model?} → persist user msg, call LLM non-stream, persist assistant msg + usage into api_usage, auto-title new conversations from first user message, return saved messages. POST /api/chat/stream — same but SSE (sse-starlette): meta → delta* → done{assistant_message, usage} → error. GET /api/chat/models, GET /api/chat/status (cached health).
3. slowapi + Redis: chat 20/min/user, API 120/hour/user → 429 with Retry-After. LLM failure → 502 {"error":{"code":"llm_unavailable"}}; user message kept, no orphan assistant row.
4. tests/chat/ (respx-mocked LLM): send persists both messages; streaming emits deltas then done and persists; auto-title; usage increments; cross-user isolation; 429; 502; search + pagination.

TEST GATE (show outputs): FULL uv run pytest -q green; curl demo of send + stream against the mock LLM; ruff clean. No Steps 6–9. When done, update the §Progress Tracker in PROJECT_PLAN.md.
```

## Prompt 6 — Frontend scaffold + auth UI

```
Implement ONLY Step 6 (frontend scaffold + auth UI) per PROJECT_PLAN.md §Frontend Specification.
1. frontend/: Vite react-ts template; Tailwind; deps axios, zustand, react-router-dom, react-markdown, remark-gfm, react-syntax-highlighter, date-fns; dev: vitest, @testing-library/react, jsdom, playwright (+ npx playwright install chromium). Vite dev proxy /api → http://localhost:3001.
2. Backend serves frontend/dist in production (StaticFiles mount at / with SPA fallback) — single origin :3001 for tunneling; keep CORS for dev origin http://localhost:5173.
3. stores/authStore (zustand, localStorage-persisted): user + tokens; services/api.ts axios instance with auth header and response interceptor: 401 → refresh once → retry, else logout.
4. Pages: /login, /register (Tailwind forms, client validation, error banners, loading states, links between them), /chat placeholder behind ProtectedRoute, unauthenticated → /login. Dark mode toggle (class strategy, persisted).
5. tests: vitest units (authStore, refresh-on-401 interceptor with mocked axios); Playwright auth.spec.ts: register → /chat → logout → login → wrong-password error.

TEST GATE (show outputs): cd frontend && npm run build + npx vitest run + Playwright spec green; backend FULL uv run pytest -q green; ruff clean. No Steps 7–9. When done, update the §Progress Tracker in PROJECT_PLAN.md.
```

## Prompt 7 — Chat UI (core)

```
Implement ONLY Step 7 (chat UI) per PROJECT_PLAN.md §Frontend Specification.
1. Layout: left sidebar (collapsible on mobile) + main chat column.
2. Sidebar: conversations grouped Today/Yesterday/Earlier, pinned first; debounced search (?q=); New chat; hover actions pin/delete (confirm dialog); active highlight.
3. Messages: user bubbles right (accent), assistant left (neutral); markdown with GFM + syntax-highlighted code blocks + copy-code button; copy whole message; regenerate last assistant reply (re-stream, replace); timestamps; auto-scroll only when already at bottom.
4. Streaming: send consumes SSE from /api/chat/stream via fetch ReadableStream; deltas render live with typing indicator; input disabled while streaming; abort button cancels.
5. Input: auto-growing textarea; Enter=send, Shift+Enter=newline; char counter (16k cap).
6. Settings drawer: model select (from /api/chat/models), temperature 0–2, max_tokens, system prompt — persisted in localStorage, sent with requests; Clear conversation.
7. tests: vitest units (streaming reducer, markdown/copy); Playwright chat.spec.ts against backend + mock LLM: new chat → send → streamed reply → switch conversation → delete.

TEST GATE (show outputs): npx vitest run + Playwright green; FULL backend pytest green; npm run build ok. No Steps 8–9. When done, update the §Progress Tracker in PROJECT_PLAN.md.
```

## Prompt 8 — Profile, usage, export, polish

```
Implement ONLY Step 8 (profile, usage, export, polish) per PROJECT_PLAN.md.
1. Backend: GET /api/users/usage → daily tokens+requests for last 30 days (from api_usage); GET /api/conversations/{id}/export?format=md|json (owner-scoped file download).
2. UI: /profile page — edit username, change password, 30-day usage bar chart (recharts), account info, logout. Export button (download .md/.json) in chat header.
3. Polish: toasts on all actions; friendly banners for 502 "model unavailable" and 429 "slow down"; empty states; loading skeletons; responsive to 375px (sidebar becomes drawer); a11y pass (focus rings, aria-labels); shortcuts Ctrl/Cmd+K (search), Ctrl/Cmd+Shift+O (new chat).
4. tests: backend tests for usage aggregation + both export formats; vitest units; Playwright profile.spec.ts (edit username, change password, re-login, chart renders, export downloads).

TEST GATE (show outputs): FULL backend pytest green; npx vitest run + Playwright green; npm run build ok; ruff clean. No Step 9. When done, update the §Progress Tracker in PROJECT_PLAN.md.
```

## Prompt 9 — Hardening, ops & final test

```
Implement ONLY Step 9 (production hardening & ops) per PROJECT_PLAN.md.
1. Security: CORS restricted to configured origins; security headers middleware (X-Content-Type-Options, X-Frame-Options=DENY, Referrer-Policy); enforce max body/message sizes; never log tokens/keys.
2. Ops: scripts/start_dev.sh (uvicorn + vite); scripts/build_and_run.sh (build frontend, alembic upgrade head, uvicorn :3001); scripts/backup_db.sh (pg_dump to ./backups, keep 14); scripts/restore_db.sh; systemd user unit scripts/systemd/llm-chat.service + install notes.
3. scripts/smoke.sh: curl end-to-end — health, register, login, create conversation, send (mock LLM), stream, list, export, delete — pass/fail summary.
4. scripts/load_test.py: asyncio, 50 virtual users, 5-minute mixed send/stream against mock LLM; print p50/p95/p99 latency + error rate + LLM_MAX_CONCURRENT tuning suggestion.
5. README.md: overview, architecture, full env-var table, dev + prod runbooks, backup/restore, systemd, and a "Cloudflare Tunnel (yours)" section — single origin http://localhost:3001, SSE pass-through note.
6. Final full regression of everything.

TEST GATE (show outputs): FULL backend pytest green; vitest + Playwright green; smoke.sh passes; load test <1% errors with report; systemd-analyze verify OK; ruff clean. Then summarize what was built and how to run it. When done, update the §Progress Tracker in PROJECT_PLAN.md.
```
