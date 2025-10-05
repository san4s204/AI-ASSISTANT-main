#!/usr/bin/env bash
# Пример: ./scripts/sql.sh "SELECT name FROM sqlite_master WHERE type='table';"
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T app sqlite3 db.db "${1:-.tables}"
