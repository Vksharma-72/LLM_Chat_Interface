#!/usr/bin/env bash
# Back up the llmchat database (pg_dump custom format) into ./backups,
# keeping the 14 most recent dumps (§13).
set -euo pipefail
cd "$(dirname "$0")/.."

DB_URL="${DATABASE_URL:-}"
if [[ -z "$DB_URL" && -f .env ]]; then
  DB_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)"
fi
[[ -z "$DB_URL" ]] && { echo "DATABASE_URL not set (and no .env found)" >&2; exit 1; }

# pg_dump speaks libpq URLs, not sqlalchemy's "+asyncpg" dialect
PG_URL="${DB_URL/postgresql+asyncpg:/postgresql:}"

KEEP="${KEEP:-14}"
OUT_DIR="backups"
mkdir -p "$OUT_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_FILE="$OUT_DIR/llmchat-$STAMP.dump"

echo "==> Dumping database to $OUT_FILE"
pg_dump "$PG_URL" --format=custom --file="$OUT_FILE"

echo "==> Pruning old backups (keeping $KEEP newest)"
ls -1t "$OUT_DIR"/llmchat-*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  echo "    removing $old"
  rm -f "$old"
done

echo "==> Done: $OUT_FILE"
