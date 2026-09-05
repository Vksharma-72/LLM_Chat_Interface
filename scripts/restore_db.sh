#!/usr/bin/env bash
# Restore a database dump created by backup_db.sh into llmchat (or $DATABASE_URL).
# Usage: scripts/restore_db.sh [backups/llmchat-YYYYmmdd-HHMMSS.dump]
#        (defaults to the newest dump in ./backups)
set -euo pipefail
cd "$(dirname "$0")/.."

DUMP_FILE="${1:-}"
if [[ -z "$DUMP_FILE" ]]; then
  DUMP_FILE="$(ls -1t backups/llmchat-*.dump 2>/dev/null | head -1 || true)"
fi
[[ -z "$DUMP_FILE" || ! -f "$DUMP_FILE" ]] && {
  echo "No dump file found. Usage: $0 backups/llmchat-YYYYmmdd-HHMMSS.dump" >&2
  exit 1
}

DB_URL="${DATABASE_URL:-}"
if [[ -z "$DB_URL" && -f .env ]]; then
  DB_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)"
fi
[[ -z "$DB_URL" ]] && { echo "DATABASE_URL not set (and no .env found)" >&2; exit 1; }
PG_URL="${DB_URL/postgresql+asyncpg:/postgresql:}"

echo "==> Restoring $DUMP_FILE into ${PG_URL##*/}"
echo "    This drops existing objects (--clean). Continue? [y/N]"
read -r answer
[[ "$answer" == "y" || "$answer" == "Y" ]] || { echo "Aborted."; exit 1; }

pg_restore "$PG_URL" --clean --if-exists --no-owner "$DUMP_FILE"
echo "==> Restore complete."
