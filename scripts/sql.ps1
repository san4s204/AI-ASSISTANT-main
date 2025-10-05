# Пример: .\scripts\sql.ps1 "SELECT name FROM sqlite_master WHERE type='table';"
param([string]$Query = ".tables")
docker compose exec -T app sqlite3 db.db $Query