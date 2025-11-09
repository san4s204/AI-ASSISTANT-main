# bot/services/memory.py
from __future__ import annotations
from typing import List, Tuple
import aiosqlite

from config import DB_PATH

# сколько сообщений хранить на чат
DEFAULT_LIMIT = 10


async def add_memory_message(
    owner_id: int,
    chat_id: int,
    role: str,
    content: str,
    limit: int = DEFAULT_LIMIT,
) -> None:
    """
    Сохраняем одну реплику диалога и подчищаем старые.
    role: 'user' или 'assistant'
    """
    content = (content or "").strip()
    if not content:
        return

    role = "assistant" if role == "assistant" else "user"

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO chat_memory (owner_id, chat_id, role, content)
            VALUES (?, ?, ?, ?)
            """,
            (owner_id, chat_id, role, content),
        )
        await conn.commit()

        # подчистим старые записи сверх лимита
        async with conn.execute(
            """
            SELECT id
            FROM chat_memory
            WHERE owner_id = ? AND chat_id = ?
            ORDER BY id DESC
            LIMIT -1 OFFSET ?
            """,
            (owner_id, chat_id, limit),
        ) as cur:
            extra = await cur.fetchall()

        if extra:
            ids = [row[0] for row in extra]
            await conn.executemany(
                "DELETE FROM chat_memory WHERE id = ?",
                [(i,) for i in ids],
            )
            await conn.commit()


async def get_memory_history(
    owner_id: int,
    chat_id: int,
    limit: int = 10,
) -> List[Tuple[str, str]]:
    """
    Возвращает историю в виде списка (role, content),
    в хронологическом порядке (от старых к новым).
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            """
            SELECT role, content
            FROM chat_memory
            WHERE owner_id = ? AND chat_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (owner_id, chat_id, limit),
        ) as cur:
            rows = await cur.fetchall()

    rows = list(rows)
    rows.reverse()  # делаем от старых к новым
    return [(r[0], r[1]) for r in rows]


async def clear_memory(owner_id: int, chat_id: int) -> None:
    """На всякий случай: полная очистка истории конкретного чата."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM chat_memory WHERE owner_id = ? AND chat_id = ?",
            (owner_id, chat_id),
        )
        await conn.commit()
