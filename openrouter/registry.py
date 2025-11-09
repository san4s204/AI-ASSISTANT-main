from __future__ import annotations
import asyncio, logging
from typing import Dict, Optional
from aiogram import Bot, Dispatcher

from . import state
from .worker import bot_worker

log = logging.getLogger(__name__)

def active_bots() -> Dict[str, Dict[str, object]]:
    return dict(state.ACTIVE)

async def run_bot(bot_token: str, doc_id: str, owner_id: int) -> bool:
    """
    Запускает «дочернего» бота в фоне.
    True — если стартанули, False — если уже есть живой воркер для этого токена.
    """
    if not bot_token:
        raise ValueError("bot_token is empty")

    rec = state.ACTIVE.get(bot_token)
    if rec is not None:
        task = rec.get("task")
        if isinstance(task, asyncio.Task) and not task.done():
            log.info("run_bot(%s…): уже запущен", bot_token[:10])
            return False

    log.info("run_bot(%s…): стартуем воркер", bot_token[:10])
    task = asyncio.create_task(
        bot_worker(bot_token, doc_id, owner_id),
        name=f"child-bot:{bot_token[:10]}",
    )

    state.ACTIVE[bot_token] = {
        "task": task,
        "owner_id": owner_id,
        "doc_id": doc_id,
    }

    def _done(_):
        # если воркер умер сам — подчистим реестр
        rec = state.ACTIVE.get(bot_token)
        if rec is not None and rec.get("task") is task:
            log.info("run_bot(%s…): воркер завершился, чистим ACTIVE", bot_token[:10])
            state.ACTIVE.pop(bot_token, None)

    task.add_done_callback(_done)
    return True

async def stop_bot(bot_token: str) -> bool:
    """
    Останавливает «дочернего» бота по токену.
    True — если что-то реально останавливали, False — если не найден.
    """
    rec = state.ACTIVE.get(bot_token)
    if rec is None:
        log.info("stop_bot(%s…): в ACTIVE нет записи", bot_token[:10])
        return False

    task = rec.get("task")
    if not isinstance(task, asyncio.Task):
        log.warning("stop_bot(%s…): task отсутствует/битый, просто удаляем запись", bot_token[:10])
        state.ACTIVE.pop(bot_token, None)
        return False

    if task.done():
        log.info("stop_bot(%s…): task уже завершён", bot_token[:10])
        state.ACTIVE.pop(bot_token, None)
        return True

    log.info("stop_bot(%s…): отменяю polling task", bot_token[:10])
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("Polling task raised on cancel")

    state.ACTIVE.pop(bot_token, None)
    return True


async def stop_user_bots(owner_id: int) -> int:
    """
    Останавливает все дочерние боты, которые принадлежат owner_id.
    Возвращает количество остановленных воркеров.
    """
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
            logging.exception("stop_bot(%s) failed", tok[:10])
    logging.info("stop_user_bots(uid=%s): остановлено %s воркеров", owner_id, stopped)
    return stopped