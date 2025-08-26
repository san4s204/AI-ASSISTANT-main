from __future__ import annotations
import os
import datetime
import aiosqlite

DB_PATH = os.getenv("DB_PATH", "db.db")

def _format_subscription(dt: datetime.datetime) -> str:
    # Прежний формат: HH:MM:SS DD:MM:YYYY
    return dt.strftime("%H:%M:%S %d:%m:%Y")

async def get_subscription_until(user_id: int | str) -> str | bool:
    """Возвращает строку c датой окончания подписки в формате "HH:MM:SS DD:MM:YYYY" или False."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT date_end FROM users WHERE id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
        if not row or not row[0]:
            return False
        try:
            dt_end = datetime.datetime.fromisoformat(row[0])
        except Exception:
            # fallback: не-ISO формат — попробуем сравнить строково, как было
            now_iso = datetime.datetime.now().isoformat()
            if str(now_iso) < str(row[0]):
                # не можем корректно отформатировать — вернём исходную строку
                return str(row[0])
            return False
        if datetime.datetime.now() < dt_end:
            return _format_subscription(dt_end)
        return False
    except Exception:
        return False

async def set_subscription_active(user_id: int | str, username: str | None = None, days: int = 30):
    """Устанавливает/продлевает подписку пользователю на days дней от текущего момента.
    Возвращает datetime окончания подписки."""
    end_date = datetime.datetime.now() + datetime.timedelta(days=days)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO users (id, subscribe, date_end, username, state_bot)
            VALUES (?, 'subscribe', ?, ?, COALESCE((SELECT state_bot FROM users WHERE id = ?), 'stop'))
            ON CONFLICT(id) DO UPDATE SET
                subscribe='subscribe',
                date_end=excluded.date_end,
                username=COALESCE(excluded.username, users.username)
            """,
            (user_id, end_date.isoformat(), username, user_id)
        )
        await conn.commit()
    return end_date

async def get_user_token_and_doc(user_id: int | str) -> tuple[str | None, str | None]:
    """Возвращает (bot_token, word_file) или (None, None)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT bot_token, word_file FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None, None
            return row[0], row[1]

async def update_user_state(user_id: int | str, new_state: str):
    """Обновляет state_bot для пользователя."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET state_bot = ? WHERE id = ?", (new_state, user_id))
        await conn.commit()

async def get_user_doc_id(user_id: int | str):
    """Возвращает ссылку/ID источника (Docs/Sheets) или None."""
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT word_file FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    val = row[0]
    if val is None:
        return None
    val = str(val).strip()
    return val or None

async def update_user_token(user_id: int | str, token: str) -> bool:
    """Обновляет bot_token только для пользователей с активной подпиской.
    Возвращает True/False — были ли обновлены строки."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """
            UPDATE users
            SET bot_token = ?
            WHERE id = ? AND subscribe = 'subscribe'
            """,
            (token, user_id)
        )
        await conn.commit()
        return cur.rowcount > 0


async def update_user_document(user_id: int | str, value: str) -> bool:
    """Сохраняет в users.word_file ссылку/ID (Doc или Sheet)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE users SET word_file = ? WHERE id = ?",
            (value, user_id),
        )
        await conn.commit()
        return cur.rowcount > 0
    
async def _ensure_prefs_table():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_prefs (
                user_id INTEGER PRIMARY KEY,
                calendar_id TEXT
            )
        """)
        await conn.commit()

async def set_user_calendar_id(user_id: int | str, calendar_id: str) -> None:
    await _ensure_prefs_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            INSERT INTO user_prefs(user_id, calendar_id)
            VALUES(?, ?)
            ON CONFLICT(user_id) DO UPDATE SET calendar_id=excluded.calendar_id
        """, (user_id, calendar_id))
        await conn.commit()

async def get_user_calendar_id(user_id: int | str) -> str | None:
    await _ensure_prefs_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT calendar_id FROM user_prefs WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None
        
async def clear_user_calendar_id(user_id: int | str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE user_prefs SET calendar_id = NULL WHERE user_id = ?",
            (user_id,)
        )
        await conn.commit()
        return cur.rowcount > 0