from __future__ import annotations
import json
import datetime as dt
import aiosqlite
from typing import Optional, Tuple

# Берём путь к базе из существующего сервиса, чтобы всё писалось в тот же db.db
from bot.services.db import DB_PATH  # noqa: F401

# === Вспомогательные даты ===
def _month_bounds(now: Optional[dt.datetime] = None) -> tuple[str, str]:
    now = now or dt.datetime.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # вычисляем первый день следующего месяца
    y, m = start.year, start.month
    if m == 12:
        nxt = dt.datetime(y + 1, 1, 1)
    else:
        nxt = dt.datetime(y, m + 1, 1)
    return start.isoformat(), nxt.isoformat()

# === Инициализация таблиц (одноразово на старте) ===
async def ensure_tables() -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS token_wallets (
            user_id INTEGER PRIMARY KEY,
            period_start TEXT NOT NULL,
            period_end   TEXT NOT NULL,
            allowance_tokens INTEGER NOT NULL,
            spent_tokens     INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS token_tx (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ts TEXT NOT NULL DEFAULT (datetime('now')),
            delta_tokens INTEGER NOT NULL,
            reason TEXT,
            request_id TEXT,
            meta_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_token_tx_user_ts ON token_tx(user_id, ts DESC);
        """)
        await conn.commit()

# === Публичный API кошелька ===
async def ensure_current_wallet(user_id: int, allowance_tokens: int) -> None:
    """Гарантирует кошелёк на текущий месяц и правильный лимит."""
    p_start, p_end = _month_bounds()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
        INSERT INTO token_wallets(user_id, period_start, period_end, allowance_tokens, spent_tokens, status)
        VALUES(?, ?, ?, ?, 0, 'active')
        ON CONFLICT(user_id) DO UPDATE SET
            period_start = excluded.period_start,
            period_end   = excluded.period_end,
            allowance_tokens = excluded.allowance_tokens,
            status = 'active',
            updated_at = datetime('now')
        """, (user_id, p_start, p_end, int(allowance_tokens)))
        await conn.commit()

async def get_balance(user_id: int) -> Tuple[int, int, int]:
    """return (allowance, spent, remaining)"""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT allowance_tokens, spent_tokens FROM token_wallets WHERE user_id=?",
                                (user_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return 0, 0, 0
    allowance, spent = int(row[0]), int(row[1])
    return allowance, spent, max(0, allowance - spent)

async def can_spend(user_id: int, tokens: int) -> bool:
    allowance, spent, _ = await get_balance(user_id)
    if allowance == 0 and spent == 0:
        # кошелька нет — запрещаем, пока не ensure_current_wallet()
        return False
    return (spent + int(tokens)) <= allowance

async def debit(user_id: int, tokens: int, reason: str = "llm", request_id: Optional[str] = None, meta: Optional[dict] = None) -> bool:
    """Атомарное списание. Вернёт True, если уложились в лимит."""
    tokens = int(tokens)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        async with conn.execute("SELECT allowance_tokens, spent_tokens FROM token_wallets WHERE user_id=?",
                                (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                await conn.execute("ROLLBACK")
                return False
            allowance, spent = int(row[0]), int(row[1])
            if spent + tokens > allowance:
                await conn.execute("ROLLBACK")
                return False
        await conn.execute("UPDATE token_wallets SET spent_tokens = spent_tokens + ?, updated_at=datetime('now') WHERE user_id=?",
                           (tokens, user_id))
        await conn.execute("""
            INSERT INTO token_tx(user_id, delta_tokens, reason, request_id, meta_json)
            VALUES(?, ?, ?, ?, ?)
        """, (user_id, -tokens, reason, request_id, json.dumps(meta or {}, ensure_ascii=False)))
        await conn.commit()
        return True

# Ненавязчивая грубая оценка токенов (пока нет usage из OpenRouter).
# При желании заменим на реальное значение.
def rough_token_estimate(prompt: str, completion: Optional[str]) -> int:
    # эмпирика: ~1 токен ≈ 4 символа (для RU/EN в среднем)
    p = len(prompt or "") // 4
    c = len(completion or "") // 4
    return max(1, p + c)
