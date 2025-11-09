from __future__ import annotations
import asyncio, logging
from typing import Dict, Optional
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramConflictError, TelegramUnauthorizedError
import contextlib
from . import state
from .worker import bot_worker

log = logging.getLogger(__name__)

def active_bots() -> Dict[str, Dict[str, object]]:
    return dict(state.ACTIVE)

async def check_token_free(bot_token: str) -> None:
    """
    Делает один короткий getUpdates и смотрит, есть ли конфликт.
    НИЧЕГО не сохраняем, это чисто диагностика.
    """
    tmp_bot = Bot(bot_token)
    try:
        # timeout=0, limit=1 — мгновенный запрос без long polling
        await tmp_bot.get_updates(limit=1, timeout=0)
        log.info("check_token_free(%s…): OK, конфликтов нет", bot_token[:10])
    except TelegramConflictError:
        log.error("check_token_free(%s…): КТО-ТО ЕЩЁ ПОЛЛИТ ЭТОТ ТОКЕН!", bot_token[:10])
    except TelegramUnauthorizedError:
        log.warning("check_token_free(%s…): Unauthorized — токен невалиден/отозван", bot_token[:10])
    except Exception as e:
        log.exception("check_token_free(%s…): неожиданный сбой: %s", bot_token[:10], e)
    finally:
        await tmp_bot.session.close()

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
    rec = state.ACTIVE.get(bot_token)
    if not rec:
        logging.info("stop_bot(%s…): в ACTIVE нет записи", bot_token[:10])
        await check_token_free(bot_token)
        return False

    task: Optional[asyncio.Task] = rec.get("task")    # type: ignore[assignment]
    dp:   Optional[Dispatcher] = rec.get("dp")        # type: ignore[assignment]
    bot:  Optional[Bot] = rec.get("bot")              # type: ignore[assignment]

    # 1) мягко останавливаем polling
    if dp is not None:
        logging.info("stop_bot(%s…): вызываю dp.stop_polling()", bot_token[:10])
        with contextlib.suppress(Exception):
            dp.stop_polling()

    # 2) отменяем задачу, если ещё жива
    if isinstance(task, asyncio.Task) and not task.done():
        logging.info("stop_bot(%s…): отменяю polling task", bot_token[:10])
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logging.exception("Polling task raised on cancel")

    # 3) на всякий случай закрываем сессию бота, если воркер сам не успел
    if bot is not None:
        with contextlib.suppress(Exception):
            await bot.session.close()

    # 4) чистим реестр
    state.ACTIVE.pop(bot_token, None)

    # 5) диагностический пинг — смотрим, есть ли ещё кто-то, кто poll'ит этот токен
    await check_token_free(bot_token)

    return True
    state.ACTIVE.pop(bot_token, None)

    # ⬇️ вот здесь диагностический "пинг"
    await check_token_free(bot_token)

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