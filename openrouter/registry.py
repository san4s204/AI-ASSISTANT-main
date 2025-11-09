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
        logging.info("run_bot(%s): уже активен", bot_token[:10])
        return False

    task = asyncio.create_task(
        bot_worker(bot_token, doc_id, owner_id),
        name=f"bot:{bot_token[:8]}"
    )

    state.ACTIVE[bot_token] = {
        "task": task,
        "doc_id": doc_id,
        "owner_id": owner_id,
    }
    return True

async def stop_bot(bot_token: str) -> bool:
    """
    Останавливает «дочернего» бота. True — если был активен и остановлен.
    """
    entry = state.ACTIVE.get(bot_token)
    if not entry:
        logging.info("stop_bot(%s): нет активной записи", bot_token[:10])
        return False

    task: Optional[asyncio.Task] = entry.get("task")  # type: ignore[assignment]
    if not task:
        logging.warning("stop_bot(%s): в ACTIVE нет task", bot_token[:10])
        # запись всё равно удалит воркер в finally, но можем очистить сами:
        state.ACTIVE.pop(bot_token, None)
        return False

    if task.done():
        logging.info("stop_bot(%s): task уже завершена", bot_token[:10])
        # воркер в своём finally уже должен был сделать pop
        state.ACTIVE.pop(bot_token, None)
        return True

    logging.info("stop_bot(%s): отменяю polling task", bot_token[:10])
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        logging.exception("Polling task raised on cancel")

    # окончательный pop — на случай, если воркер не добрался до finally
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