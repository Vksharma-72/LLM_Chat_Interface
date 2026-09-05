#!/usr/bin/env bash
# End-to-end smoke test (S9). Boots its own throwaway stack — mock LLM :8001 and
# the app on :3100 against the llmchat_test database — then curls through the
# whole user journey and prints a pass/fail summary. Exits non-zero on failure.
set -uo pipefail
cd "$(dirname "$0")/.."

BASE_URL="${BASE_URL:-http://127.0.0.1:3100}"
PASS=0
FAIL=0
PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

check() {
  local name="$1" ok="$2"
  if [[ "$ok" == "true" ]]; then
    PASS=$((PASS + 1)); echo "  PASS  $name"
  else
    FAIL=$((FAIL + 1)); echo "  FAIL  $name"
  fi
}

echo "== booting throwaway stack (mock LLM :8001, app :3100 on llmchat_test) =="
uv run --no-sync python scripts/mock_llm_server.py > /tmp/smoke_mock.log 2>&1 &
PIDS+=($!)
DATABASE_URL="postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat_test" \
REDIS_URL="redis://localhost:6379/1" \
LLM_API_URL="http://127.0.0.1:8001/v1" \
  uv run --no-sync uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 3100 > /tmp/smoke_backend.log 2>&1 &
PIDS+=($!)

ready=false
for _ in $(seq 1 60); do
  if curl -sf "$BASE_URL/health" > /dev/null 2>&1; then ready=true; break; fi
  sleep 0.5
done
check "app becomes healthy on $BASE_URL" "$ready"

echo "== end-to-end checks =="
HEALTH=$(curl -sf "$BASE_URL/health" || true)
check "health returns status ok" "$([[ $HEALTH == *'"ok"'* ]] && echo true || echo false)"

UNIQUE="smoke_$(date +%s)_$RANDOM"
REG=$(curl -sf -X POST "$BASE_URL/api/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$UNIQUE@example.com\",\"username\":\"$UNIQUE\",\"password\":\"password123\"}" || true)
check "register user" "$([[ $REG == *access_token* ]] && echo true || echo false)"
TOKEN=$(echo "$REG" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
AUTH="Authorization: Bearer $TOKEN"

LOGIN=$(curl -sf -X POST "$BASE_URL/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username_or_email\":\"$UNIQUE\",\"password\":\"password123\"}" || true)
check "login" "$([[ $LOGIN == *access_token* ]] && echo true || echo false)"

CONV=$(curl -sf -X POST "$BASE_URL/api/conversations" -H "$AUTH" \
  -H 'Content-Type: application/json' -d '{"title":"Smoke conversation"}' || true)
CID=$(echo "$CONV" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
check "create conversation" "$([[ -n $CID ]] && echo true || echo false)"

SENT=$(curl -sf -X POST "$BASE_URL/api/chat/send" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"conversation_id\":\"$CID\",\"content\":\"smoke test message\"}" || true)
check "send message (mock LLM)" "$([[ $SENT == *assistant_message* ]] && echo true || echo false)"

STREAM=$(curl -sf -N -X POST "$BASE_URL/api/chat/stream" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"conversation_id\":\"$CID\",\"content\":\"smoke stream message\"}" || true)
check "stream emits meta and done" "$([[ $STREAM == *'event: meta'* && $STREAM == *'event: done'* ]] && echo true || echo false)"

LIST=$(curl -sf "$BASE_URL/api/conversations" -H "$AUTH" || true)
check "list conversations" "$([[ $LIST == *'"items"'* ]] && echo true || echo false)"

EXPORT=$(curl -sf "$BASE_URL/api/conversations/$CID/export?format=md" -H "$AUTH" || true)
check "export conversation (md)" "$([[ $EXPORT == '#'* ]] && echo true || echo false)"

STATUS=$(curl -sf -o /dev/null -w "%{http_code}" -X DELETE \
  "$BASE_URL/api/conversations/$CID" -H "$AUTH" || true)
check "delete conversation (204)" "$([[ $STATUS == 204 ]] && echo true || echo false)"

echo
echo "== summary: $PASS passed, $FAIL failed =="
[[ $FAIL -eq 0 ]]
