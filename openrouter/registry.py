from __future__ import annotations
import asyncio, logging
from typing import Dict, Optional
from aiogram import Bot, Dispatcher

from . import state
from .worker import bot_worker

def active_bots() -> Dict[str, Dict[str, object]]:
    return dict(state.ACTIVE)

async def run_bot(bot_token: str, doc_id: str, owner_id: int) -> bool:
    """
    Запускает «дочернего» бота в фоне. True — если стартанули, False — уже работал.
    """
    if not bot_token:
        raise ValueError("bot_token is empty")
    if bot_token in state.ACTIVE:
        return False

    task = asyncio.create_task(bot_worker(bot_token, doc_id, owner_id), name=f"bot:{bot_token[:8]}")
    def _done(_):
        state.ACTIVE.pop(bot_token, None)
    task.add_done_callback(_done)

    state.ACTIVE[bot_token] = {"task": task, "doc_id": doc_id, "owner_id": owner_id}
    return True

async def stop_bot(bot_token: str) -> bool:
    """
    Останавливает «дочернего» бота. True — если был активен и остановлен.
    """
    entry = state.ACTIVE.get(bot_token)
    if not entry:
        return False

    task: Optional[asyncio.Task] = entry.get("task")  # type: ignore[assignment]
    dp: Optional[Dispatcher] = entry.get("dp")        # type: ignore[assignment]
    bot: Optional[Bot] = entry.get("bot")             # type: ignore[assignment]

    try:
        if dp:
            dp.stop_polling()
    except Exception:
        pass

    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logging.exception("Polling task raised on cancel")

    try:
        if bot:
            await bot.delete_webhook(drop_pending_updates=True)
            await bot.session.close()
    except Exception:
        pass

    state.ACTIVE.pop(bot_token, None)
    return True


async def stop_user_bots(owner_id: int) -> int:
    """
    Останавливает все дочерние боты, которые принадлежат owner_id.
    Возвращает количество остановленных воркеров.
    """
    # копируем ключи, чтобы не итерироваться по изменяемому dict
    tokens = [
        tok for tok, info in state.ACTIVE.items()
        if info.get("owner_id") == owner_id
    ]

    stopped = 0
    for tok in tokens:
        try:
            ok = await stop_bot(tok)
            if ok:
                stopped += 1
        except Exception:
            logging.exception("stop_bot(%s) failed", tok)
    return stopped