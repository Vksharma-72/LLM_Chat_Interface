# Feature Plan — File Attachments (Steps 10–11)

Scope confirmed with user: uploads + display + LLM understanding only. **No image/video generation.** Vision input is available (user's llama-server loads an mmproj), served from `http://localhost:8080/v1`.

The plan follows the project's step methodology: PROJECT_PLAN.md gains the spec + steps 10–11 with test gates, PROMPTS.md gains the two prompts, then each step is implemented and gated exactly like steps 1–9.

---

## Step 10 — Attachments backend (storage, upload/serve, message pipeline)

### Data model (Alembic migration #2, chained to `5aa2aa03baa3`, applied to both DBs)
New table **attachments**:
- `id` UUID PK (uuid4) · `user_id` FK→users CASCADE (indexed) · `conversation_id` FK→conversations CASCADE **nullable** · `message_id` FK→messages CASCADE **nullable** (both set when the message is sent)
- `filename` (display name, String 255) · `stored_filename` (disk name = `{attachment_id}{ext}`, never client-controlled) · `mime_type` String(127) · `size_bytes` BigInteger · `kind` String(16) CHECK IN (`image`,`video`,`audio`,`document`,`other`)
- `extracted_text` TEXT nullable (documents: extracted once at upload) · `model_image_path` nullable (Pillow-downscaled derivative for the vision prompt)
- `created_at` timestamptz
- Indexes: `ix_attachments_user_id`, `ix_attachments_message_id`
- `Message` model gains `attachments` relationship (loaded with `selectinload` — never lazy in async)

### Storage & serving
- Disk layout `{UPLOAD_DIR}/{user_id}/{attachment_id}/{stored_filename}` (+ `model.jpg` derivative); `UPLOAD_DIR` default `uploads/` at root, gitignored. Files streamed to/from disk in 1 MB chunks (never fully in RAM).
- `GET /api/attachments/{id}/content` — owner-scoped (404 for others, no existence leak), `FileResponse` with real MIME; `Content-Disposition: inline` for image/video/audio/pdf, `attachment` otherwise; Starlette's FileResponse already handles HTTP Range (video scrubbing). Authenticated only — **no static mount**, so URLs are private.
- `GET /api/attachments/{id}` — metadata (used by frontend after refresh).

### Upload endpoint
- `POST /api/attachments` — multipart, one file per request (frontend uploads in parallel), slowapi `api_limit` per user.
- Validation: size ≤ `UPLOAD_MAX_FILE_MB` (default 100, enforced both by content-length and while streaming); kind detection from MIME + magic bytes (`filetype` lib) — reject unknown/dangerous (e.g. `text/html`, executables) with 422 `unsupported_file_type`; client filename sanitized for display only.
- At upload: images → Pillow downscale-for-model derivative (max 1024px JPEG, keeps original untouched); documents → one-time text extraction stored in `extracted_text` (**pypdf** for PDFs, **python-docx** for .docx, direct read for txt/md/csv/json/code; audio/video/other → stored, no extraction).
- Response: `AttachmentResponse {id, filename, mime_type, size_bytes, kind, url}`.

### Middleware change
`BodySizeLimitMiddleware` becomes path-aware: keeps the 1 MB cap everywhere except `POST /api/attachments` where the cap is `UPLOAD_MAX_FILE_MB + 1 MB` overhead. (Tests updated: oversized normal request still 413; oversized upload → 413 `payload_too_large`.)

### Message pipeline (send + stream + regenerate)
- `ChatSendRequest.attachment_ids: list[UUID] = []`; `_validate_combination` now allows missing content **if** attachment_ids non-empty (caption-less image message) or regenerate.
- `_prepare_exchange`: loads attachment rows, validates ownership + not-yet-bound (`message_id IS NULL`), binds them to the new message, commits together. Auto-title: caption → first 60 chars; else `📷 {filename}` / `📎 {filename}`.
- New shared **prompt builder** used by send, stream, and regenerate: builds the OpenAI multimodal payload from `(content, attachments)`:
  - images → content parts `[{type:"text",…},{type:"image_url", image_url:{url:"data:{mime};base64,…"}}]` using the **model derivative**; gated by `LLM_VISION_ENABLED` (default true) — when disabled or a non-vision server rejects parts, fallback to a text note `[User attached image: name]` so the message still works
  - documents → `[Document: {filename}]\n{extracted_text}` (truncated to `DOC_MAX_CHARS`, default 100000) prepended as text context
  - audio/video/other → textual note `[User attached {kind}: {filename} ({size} MB)]`
- Regenerate re-derives the prompt from the stored user message + its attachment rows (images re-read from the derivative file).
- `MessageResponse` gains `attachments: list[AttachmentResponse]`; SSE `meta`/`done` and `/conversations/{id}` detail include them (selectinload).
- Export: JSON includes attachment metadata; MD adds `![filename](url)` for images and `📎 filename` lines for others.
- Orphan cleanup: lifespan task (on startup + daily) deletes unbound rows (`message_id IS NULL`) older than 24 h and disk files with no DB row.

### Mock server + tests
- `scripts/mock_llm_server.py`: accept array content parts; when an image part is present reply with `MOCK_VISION_REPLY` (default "I can see the image.") — makes vision E2E-testable without the real model.
- New `tests/attachments/`: upload per kind, size cap 413, bad type 422, cross-user fetch 404, bind-on-send + owner validation, **respx assert** the upstream request contains the base64 image part / extracted PDF text, caption-less send, auto-title, regenerate re-sends image parts, cascade delete removes rows + files, cleanup job. Existing suites stay green (119 + new).
- New deps (pyproject): `pypdf`, `python-docx`, `Pillow`, `filetype`.
- New env vars (config.py + .env + .env.example + README table): `UPLOAD_DIR`, `UPLOAD_MAX_FILE_MB`, `LLM_VISION_ENABLED`, `DOC_MAX_CHARS`, `MOCK_VISION_REPLY`.

**Gate 10:** alembic upgrade head on both DBs; FULL backend pytest green; ruff clean; curl demo — upload image → send → mock vision reply, upload PDF → send → reply reflects extracted text.

## Step 11 — Attachments UI

- `types/chat.ts`: `Attachment`; `Message.attachments: Attachment[]`.
- **ChatInput**: 📎 button (hidden file input, `accept` list), multi-select sequential uploads, drag-and-drop onto the chat area, clipboard paste for images, pending-attachment chips with × remove and upload progress, client-side size pre-check (friendly toast on >100 MB). `onSend(content, attachmentIds)` signature change.
- **chatStore.send**: accepts attachments, includes `attachment_ids` in the SSE body; optimistic temp message carries the pending attachment objects; `meta` event swaps in the persisted ones (reducer extended + unit-tested).
- **MessageBubble**: images → thumbnail grid, click → **Lightbox** modal (full-size, keyboard Esc/arrows); video → `<video controls>`; audio → `<audio controls>`; documents/other → file chip (icon, name, size, download). Only sent after `GET /api/attachments/{id}/content` with the Bearer token (fetch → blob URL, since <img src> can't carry auth).
- Export menu unchanged (backend handles links). Friendly banners for `payload_too_large` / `unsupported_file_type` via the existing `friendlyError` map.
- **Tests**: vitest units (reducer attachments pass-through, chip rendering, size pre-check); Playwright chat spec extended — upload a tiny generated PNG via `setInputFiles` → send → streamed vision reply visible + thumbnail renders; upload a text-file PDF → reply references its content; delete conversation clears everything.
- `smoke.sh` gains an upload+send step.

**Gate 11:** FULL backend pytest; vitest + Playwright green; `npm run build`; ruff clean; smoke.sh passes.

---

### Files touched (summary)
Backend: new `models/attachment.py`, `schemas/attachment.py`, `api/routes/attachments.py`, `services/attachments.py` (storage/extraction/prompt-builder), migration #2; modified `models/message.py`+`__init__`, `schemas/chat.py`+`message.py`, `routes/chat.py`+`conversations.py`, `core/http_security.py`, `core/config.py`, `main.py` (cleanup task), `repositories.py`, `scripts/mock_llm_server.py`, `pyproject.toml`, `.env(.example)`, README. Frontend: `ChatInput`, `MessageBubble`, `MessageList`, `chatStore`, `types/chat.ts`, new `AttachmentChip` + `Lightbox`, `friendlyError`, tests. Docs: PROJECT_PLAN.md (§15 attachments spec + steps 10–11 + tracker rows), PROMPTS.md (two new step prompts).

### Risks / notes
- The 100 MB cap is env-tunable; video scrubbing relies on Starlette Range support (present in current version — verified in gate).
- Base64 vision payloads use the downscaled derivative, not the original, keeping prompts small.
- `.env` LLM_API_URL already points at your live llama-server (:8080); Playwright/tests keep overriding to the mock (:8001).
- No new ports, no new services — fits the single-origin :3001 tunnel design.