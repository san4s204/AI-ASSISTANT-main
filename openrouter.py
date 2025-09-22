# openrouter.py
from __future__ import annotations
import re
import asyncio
import logging
from typing import Dict, Optional
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode, ChatAction
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from hashsss import answer  # асинхронный вызов OpenRouter с кэшем и Google Docs
from providers.google_calendar_oauth_provider import (
    get_user_timezone_oauth,
    list_events_between_oauth,
)
from bot.services.db import get_user_calendar_id
from bot.services.token_wallet import ensure_current_wallet, can_spend, debit, rough_token_estimate
from bot.services.limits import month_token_allowance

load_dotenv(override=True)

# Храним активных «дочерних» ботов: токен -> {bot, dp, task, doc_id}
_active: Dict[str, Dict[str, object]] = {}

CAL_TRIGGERS = ("календар", "событ", "встреч", "созвон", "мит", "митап")

def _looks_calendar(text: str) -> bool:
    s = (text or "").lower()
    # Явные ключи или фразы "сегодня/завтра/недел"
    return any(t in s for t in CAL_TRIGGERS) or any(
        k in s for k in ("сегодня", "завтр", "недел", "выходн")
    )

async def _bot_worker(bot_token: str, doc_id: str, owner_id: int) -> None:
    """
    Запускает отдельного «дочернего» бота и держит polling до отмены.
    Всю очистку делаем в finally.
    """
    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Зарегистрируем хендлеры
    @dp.message(CommandStart())
    async def start_handler(message: types.Message):
        await message.answer(f"Привет, {message.from_user.full_name}!")

    @dp.message()
    async def echo_handler(message: types.Message):
        # 0) Обрабатываем только текст
        text = message.text or ""
        if not text.strip():
            # молча игнорируем или ответь подсказкой, если хочешь
            return

        # Пытаемся показать "печатает..."
        try:
            await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        except Exception:
            pass

        # 1) Гарантируем кошелёк и делаем быстрый предчек
        try:
            allowance = await month_token_allowance(owner_id)
            await ensure_current_wallet(owner_id, allowance)
        except Exception:
            logging.exception("ensure_current_wallet failed")

        est_min_cost = rough_token_estimate(text, None)
        try:
            can = await can_spend(owner_id, est_min_cost)
        except Exception:
            logging.exception("can_spend failed")
            can = True  # не ломаем UX в случае сбоя учёта

        if not can:
            await message.answer(
                "⛔️ Баланс токенов исчерпан. Пополните тариф в «Настройках» или уменьшите запрос."
            )
            return

        # 2) Попытка обработать как запрос к Календарю
        try:
            if _looks_calendar(text):
                uid = owner_id
                cal_id = await get_user_calendar_id(uid) or "primary"
                tz = await get_user_timezone_oauth(uid)

                start, end, label = _parse_range_ru(text, tz)
                events = await list_events_between_oauth(uid, cal_id, start, end)

                if not events:
                    await message.answer(f"Событий {label} не найдено.")
                else:
                    await message.answer(
                        f"События {label}:\n\n{_fmt_events(events)}",
                        disable_web_page_preview=True,
                    )
                return
        except Exception:
            # Мягко сообщаем и продолжаем как обычный LLM-вопрос
            logging.exception("Calendar branch failed")
            await message.answer(
                "⚠️ Не удалось обратиться к Календарю. Проверьте подключение Google и права Calendar."
            )

        # 3) Обычный ответ модели (Docs/Sheets/и т.д.)
        try:
            reply = await answer(text, doc_id, owner_id=owner_id)
            if reply is None or str(reply).strip() == "":
                reply = "🤖 (пустой ответ)"
        except Exception:
            logging.exception("answer() failed")
            await message.answer("⚠️ Ошибка при обращении к модели. Попробуйте позже.")
            return

        # 4) Списание оценочных токенов (заменим на реальные usage, когда будут)
        try:
            est = rough_token_estimate(text, reply)
            ok = await debit(
                owner_id,
                est,
                reason="llm-child-echo",
                request_id=str(message.message_id),
                meta={"bot_chat_id": message.chat.id},
            )
            if not ok:
                # Редкая гонка: предчек прошёл, но лимит исчерпан к моменту списания.
                await message.answer("ℹ️ Достигнут лимит токенов на месяц.")
        except Exception:
            logging.exception("debit failed")

        # 5) Финальный ответ пользователю
        await message.answer(reply, disable_web_page_preview=True)



    # Сохраняем ссылку на экземпляры, чтобы stop_bot мог корректно их завершить
    _active[bot_token] = {"bot": bot, "dp": dp, "task": asyncio.current_task(), "doc_id": doc_id, "owner_id": owner_id}

    try:
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        # Нормальная остановка через cancel
        pass
    except Exception as e:
        logging.error(f"[{bot_token[:8]}…] Ошибка во время polling: {e}")
    finally:
        # Аккуратная очистка
        try:
            await bot.delete_webhook(drop_pending_updates=True)
        except Exception:
            pass
        try:
            # В aiogram v3 достаточно закрыть сессию бота;
            # dp.stop_polling() вызываем только если polling активен (обычно cancel перехватывает)
            await bot.session.close()
        except Exception:
            pass
        # Сносим из реестра
        if bot_token in _active:
            _active.pop(bot_token, None)

async def run_bot(bot_token: str, doc_id: str, owner_id: int) -> bool:
    """
    Запускает «дочернего» бота в фоне. Возвращает True, если запуск инициирован,
    False — если уже запущен.
    """
    if not bot_token:
        raise ValueError("bot_token is empty")
    if bot_token in _active:
        # уже работает
        return False

    task = asyncio.create_task(_bot_worker(bot_token, doc_id, owner_id), name=f"bot:{bot_token[:8]}")
    # На случай аварийного завершения — подчистим реестр
    def _done(_):
        _active.pop(bot_token, None)
    task.add_done_callback(_done)
    # Добавим запись (bot/dp допишутся внутри воркера)
    _active[bot_token] = {"task": task, "doc_id": doc_id}
    return True

async def stop_bot(bot_token: str) -> bool:
    """
    Останавливает «дочернего» бота. Возвращает True, если был активен и остановлен.
    """
    entry = _active.get(bot_token)
    if not entry:
        return False

    task: Optional[asyncio.Task] = entry.get("task")  # type: ignore[assignment]
    dp: Optional[Dispatcher] = entry.get("dp")  # type: ignore[assignment]
    bot: Optional[Bot] = entry.get("bot")  # type: ignore[assignment]

    # Пытаемся мягко остановить polling
    try:
        if dp:
            dp.stop_polling()
    except Exception:
        pass

    # Отменяем задачу
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logging.exception("Polling task raised on cancel")

    # Финальная очистка (если воркер не успел)
    try:
        if bot:
            await bot.delete_webhook(drop_pending_updates=True)
            await bot.session.close()
    except Exception:
        pass

    _active.pop(bot_token, None)
    return True

# (Опционально) Для отладки: список активных
def active_bots() -> Dict[str, Dict[str, object]]:
    return dict(_active)


TZ = ZoneInfo("Europe/Berlin")

def _parse_range_ru(text: str, tz) -> tuple[datetime, datetime, str]:
    """Вернёт (start, end, label) в TZ пользователя."""
    s = (text or "").lower()
    now = datetime.now(tz)

    def day_bounds(d: datetime):
        start = d.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)

    if "сегодня" in s:
        a, b = day_bounds(now);  return a, b, "сегодня"
    if "завтр" in s:
        a, b = day_bounds(now + timedelta(days=1));  return a, b, "завтра"
    if "выходн" in s:
        wd = now.weekday()  # 0=Mon
        days_to_sat = (5 - wd) % 7
        start = (now + timedelta(days=days_to_sat)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=2)
        return start, end, "на выходных"
    if "недел" in s:
        return now, now + timedelta(days=7), "на неделю"

    # по умолчанию ближайшие сутки
    return now, now + timedelta(days=1), "на сутки"

def _fmt_events(items: list[dict]) -> str:
    """Красивый вывод списка событий; учитывает all-day и dateTime."""
    if not items:
        return "Событий не найдено."
    out = []
    for ev in items[:20]:
        title = ev.get("summary") or "Без названия"
        start = ev.get("start", {}) or {}
        end = ev.get("end", {}) or {}
        if "date" in start:   # all-day
            when = f"{start['date']} → {end.get('date', start['date'])}"
        else:
            def _fmt(s: str) -> str:
                try:
                    dt = datetime.fromisoformat((s or "").replace("Z", "+00:00"))
                    return dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    return s or ""
            when = f"{_fmt(start.get('dateTime',''))} → {_fmt(end.get('dateTime',''))}"
        location = ev.get("location")
        link = ev.get("htmlLink")
        block = f"• <b>{title}</b>\n{when}"
        if location:
            block += f"\n{location}"
        if link:
            block += f"\n{link}"
        out.append(block)
    return "\n\n".join(out)