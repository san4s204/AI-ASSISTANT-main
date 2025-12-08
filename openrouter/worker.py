from __future__ import annotations
import logging, os, tempfile, asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode, ChatAction
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from googleapiclient.errors import HttpError
import contextlib
from hashsss import answer
from providers.google_calendar_oauth_provider import (
    get_user_timezone_oauth,
    list_events_between_oauth,
)
from bot.services.db import get_user_calendar_id
from bot.services.token_wallet import ensure_current_wallet, can_spend, debit, rough_token_estimate
from bot.services.limits import month_token_allowance
from bot.services.memory import get_memory_history, add_memory_message
from .calendar_utils import looks_calendar, parse_range_ru, fmt_events
from . import state

from pathlib import Path
from aiogram import F
from stt.provider import transcribe_file

log = logging.getLogger(__name__)

def _bc_kwargs(msg: types.Message) -> dict:
    bc_id = getattr(msg, "business_connection_id", None)
    return {"business_connection_id": bc_id} if bc_id else {}

async def reply(msg: types.Message, *args, **kwargs):
    # Aiogram сам добавит business_connection_id в answer() для business-чата.
    # Убираем, если кто-то случайно передал его в kwargs.
    kwargs.pop("business_connection_id", None)
    kwargs.pop("business_message_id", None)
    return await msg.answer(*args, **kwargs)

async def bot_worker(bot_token: str, doc_id: str, owner_id: int) -> None:
    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    info = state.ACTIVE.get(bot_token)
    if info is not None:
        info["bot"] = bot
        info["dp"] = dp
        info["owner_id"] = owner_id
        info["doc_id"] = doc_id
    else:
        # на всякий случай, если кто-то вызвал bot_worker напрямую
        state.ACTIVE[bot_token] = {
            "bot": bot,
            "dp": dp,
            "task": asyncio.current_task(),
            "owner_id": owner_id,
            "doc_id": doc_id,
        }

    @dp.business_connection()
    async def on_biz_conn(update: types.BusinessConnection):
        logging.info("Business connection: %s", update)

    @dp.business_message(F.text | F.caption)
    async def on_biz_text(message: types.Message):
        text = message.text or message.caption or ""
        await _process_text_query(message, text)   # <- без bc_id

    @dp.business_message(F.voice | F.audio | F.video_note)
    async def on_biz_voice(message: types.Message):
        await voice_handler(message)    

    async def _process_text_query(message: types.Message, text: str):
        if not text.strip():
            return
        
        with contextlib.suppress(Exception):
            await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING, **_bc_kwargs(message))

        # 1) учёт/кошелёк
        try:
            allowance = await month_token_allowance(owner_id)
            await ensure_current_wallet(owner_id, allowance)
        except Exception as e:
            logging.warning("ensure_current_wallet failed: %s", e)

        est_min_cost = rough_token_estimate(text, None)
        try:
            can = await can_spend(owner_id, est_min_cost)
        except Exception as e:
            logging.warning("can_spend failed: %s", e)
            can = True

        if not can:
            await message.answer("⛔️ Баланс токенов исчерпан. Пополните тариф в «Настройках» или уменьшите запрос.")
            return

        # 2) календарь
        try:
            if looks_calendar(text):
                uid = owner_id
                cal_id = await get_user_calendar_id(uid) or "primary"
                tz = await get_user_timezone_oauth(uid)
                start, end, label = parse_range_ru(text, tz)
                events = await list_events_between_oauth(uid, cal_id, start, end)
                if not events:
                    await message.answer(f"Событий {label} не найдено.")
                else:
                    await message.answer(f"События {label}:\n\n{fmt_events(events)}", disable_web_page_preview=True)
                return
        except Exception as e:
            logging.warning("Calendar branch failed: %s", e)
            await message.answer("⚠️ Не удалось обратиться к Календарю. Проверьте подключение Google и права Calendar.")

        # 3) Docs/Sheets + LLM
        try:
            if not (doc_id or "").strip():
                await reply(
                    message,
                    "ℹ️ Источник знаний не подключён.\nУкажите ссылку/ID Google Doc/Sheet командой /prompt.",
                    disable_web_page_preview=True,
                )
                return

            # достаем последние N реплик из памяти
            history = await get_memory_history(owner_id, message.chat.id, limit=10)

            bot_reply = await answer(
                text,
                doc_id,
                owner_id=owner_id,
                history=history,
            )
            if not str(bot_reply).strip():
                bot_reply = "🤖 (пустой ответ)"
        except FileNotFoundError:
            await reply(
                message,
                "⚠️ Документ/таблица не найдены или нет доступа. "
                "Проверьте ссылку/ID и права общего доступа.",
                disable_web_page_preview=True,
            )
            return
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", "?")
            logging.error("Google API HttpError %s (body suppressed)", status, exc_info=False)
            await reply(
                message,
                "⚠️ Ошибка Google API. Попробуйте позже.",
                disable_web_page_preview=True,
            )
            return
        except Exception as e:
            logging.error("answer() failed: %s", e.__class__.__name__, exc_info=False)
            await reply(message, "⚠️ Ошибка при обращении к модели. Попробуйте позже.")
            return

        # 4) списание
        try:
            est = rough_token_estimate(text, bot_reply)
            ok = await debit(
                owner_id,
                est,
                reason="llm-child-echo",
                request_id=str(message.message_id),
                meta={"bot_chat_id": message.chat.id},
            )
            if not ok:
                await reply(message, "ℹ️ Достигнут лимит токенов на месяц.")
        except Exception as e:
            logging.warning("debit failed: %s", e.__class__.__name__)

        # 5) запись в память диалога
        try:
            await add_memory_message(owner_id, message.chat.id, "user", text)
            await add_memory_message(owner_id, message.chat.id, "assistant", bot_reply)
        except Exception as e:
            logging.warning("add_memory_message failed: %s", e.__class__.__name__)

        await reply(message, bot_reply, disable_web_page_preview=True)

    @dp.message(CommandStart())
    async def start_handler(message: types.Message):
        await message.answer(f"Привет, {message.from_user.full_name}!")

    @dp.message(F.voice | F.audio | F.video_note)
    async def voice_handler(message: types.Message):
        obj = message.voice or message.audio or message.video_note
        duration = getattr(obj, "duration", 0) or 0
        max_sec = int(os.getenv("MAX_VOICE_SEC", "120"))
        if duration and duration > max_sec:
            await message.answer(f"🎙️ Голосовое слишком длинное ({duration} сек). Отправьте до {max_sec} сек.")
            return

        with tempfile.TemporaryDirectory(prefix="stt_") as tmp:
            tmpdir = Path(tmp)
            src_path = tmpdir / "input.ogg"
            try:
                await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VOICE, **_bc_kwargs(message))
                # прямой download
                await message.bot.download(obj, destination=src_path)
            except Exception:
                # fallback через get_file
                file = await message.bot.get_file(obj.file_id)
                await message.bot.download_file(file.file_path, destination=src_path)

            wav_path = tmpdir / "input.wav"
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", str(src_path), "-ac", "1", "-ar", "16000", str(wav_path),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
                )
                await proc.communicate()
                use_path = wav_path if wav_path.exists() else src_path
            except Exception:
                use_path = src_path

            try:
                await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING, **_bc_kwargs(message))
            except Exception:
                pass

            try:
                text = await transcribe_file(str(use_path), lang_hint="ru")
            except Exception as e:
                logging.exception("STT failed: %s", e)
                await message.answer("⚠️ Не удалось распознать голос. Попробуйте ещё раз.")
                return

        if not text.strip():
            await message.answer("Не удалось распознать речь 😕")
            return

        await _process_text_query(message, text)

    @dp.message()
    async def echo_handler(message: types.Message):
        text = (message.text or "").strip()
        if not text:
            return
        await _process_text_query(message, text)

    log.info("bot_worker(%s…): start_polling()", bot_token[:10])
    try:
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message",
                "edited_message",
                "callback_query",
                "business_connection",
                "business_message",
                "edited_business_message",
                "deleted_business_messages",
            ],
        )
    except asyncio.CancelledError:
        log.info("bot_worker(%s…): CancelledError, выходим", bot_token[:10])
        raise
    except Exception as e:
        log.error("bot_worker(%s…): ошибка во время polling: %s", bot_token[:10], e)
    finally:
        with contextlib.suppress(Exception):
            await bot.session.close()
        log.info("bot_worker(%s…): session closed, завершение", bot_token[:10])
