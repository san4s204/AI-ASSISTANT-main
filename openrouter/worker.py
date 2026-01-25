import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from __future__ import annotations
import logging, os, tempfile, asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode, ChatAction
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from googleapiclient.errors import HttpError
import contextlib
from hashsss import answer
from providers.google_calendar_oauth_provider import (
    get_user_timezone_oauth,
    list_events_between_oauth,
    create_event_oauth,
    update_event_oauth,
    delete_event_oauth,
)
from bot.services.db import get_user_calendar_id
from bot.services.token_wallet import ensure_current_wallet, can_spend, debit, rough_token_estimate
from bot.services.limits import month_token_allowance
from bot.services.memory import get_memory_history, add_memory_message
from .calendar_utils import parse_range_ru, fmt_events
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
    pending_calendar: dict[str, dict] = {}  # token -> payload

    DEFAULT_TZ = ZoneInfo("Europe/Berlin")

    CAL_PLAN_SYSTEM_TEMPLATE = """
    Дополнение: ты должен определить, требуется ли действие с Google Calendar.
    В конце ответа ОБЯЗАТЕЛЬНО добавь блок:

    <calendar_plan>{{JSON}}</calendar_plan>

    JSON строго валидный (без комментариев). Схема:
    {{
    "action": "none" | "list" | "create" | "update" | "delete",
    "needs_confirmation": true|false,
    "missing_fields": [строки],

    "range": {{"start": "...", "end": "..."}},  // для list (опционально)
    "event": {{"summary": "...", "start": "...", "end": "...", "location": null, "description": null}}, // create
    "match": {{"strategy": "nearest", "range_days": 14, "query": "токены|поиска"}}, // update/delete
    "patch": {{
        "start": "...",
        "end": "...",
        "shift_minutes": 60,
        "summary": "...",
        "location": "...",
        "description": "..."
    }} // update
    }}

    Правила:
    - Если пользователь не просит показать/создать/перенести/удалить запись — action="none".
    - Для create/update/delete: needs_confirmation=true.
    - Времена указывай ISO-8601 с таймзоной {tz}. Сейчас: {now}.
    - Если пользователь говорит "на час позже/раньше" — используй patch.shift_minutes (например 60 или -60).
    - Если не хватает данных — заполни missing_fields и НЕ выдумывай.
    """

    _PLAN_RE = re.compile(r"<calendar_plan>\s*(\{.*?\})\s*</calendar_plan>", re.S)

    def _extract_plan(raw: str) -> tuple[str, dict | None]:
        txt = str(raw or "")
        matches = list(_PLAN_RE.finditer(txt))
        if not matches:
            return txt.strip(), None
        m = matches[-1]  # берём последний блок
        plan_raw = m.group(1)
        try:
            plan = json.loads(plan_raw)
        except Exception:
            plan = None
        cleaned = (txt[:m.start()] + txt[m.end():]).strip()
        return cleaned, plan

    def _parse_iso(s: str) -> datetime | None:
        try:
            return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        except Exception:
            return None

    def _kbd_confirm(token: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"cal:ok:{token}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"cal:no:{token}"),
        ]])

    def _kbd_pick(token: str, n: int) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=str(i + 1), callback_data=f"cal:pick:{token}:{i}")] for i in range(n)]
        rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"cal:no:{token}")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _event_bounds(ev: dict, tz) -> tuple[datetime | None, datetime | None]:
        s = (ev.get("start") or {})
        e = (ev.get("end") or {})
        s_iso = s.get("dateTime") or s.get("date")
        e_iso = e.get("dateTime") or e.get("date")
        start = _parse_iso(s_iso) if s_iso else None
        end = _parse_iso(e_iso) if e_iso else None
        # all-day date -> трактуем как 00:00
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=tz)
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=tz)
        return start, end

    def _format_candidates(cands: list[dict]) -> str:
        lines = []
        for i, ev in enumerate(cands, 1):
            title = ev.get("summary") or "Без названия"
            s = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date") or ""
            lines.append(f"{i}) {title} — {s}")
        return "\n".join(lines)

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
        handled_by_calendar = False
        bot_reply = ""
        assistant_text_for_debit_and_memory = ""
        
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

        

        # 3) Docs/Sheets + LLM
        try:

            # достаем последние N реплик из памяти
            history = await get_memory_history(owner_id, message.chat.id, limit=10)
            now = datetime.now(DEFAULT_TZ).isoformat()
            extra_system = CAL_PLAN_SYSTEM_TEMPLATE.format(now=now, tz=str(DEFAULT_TZ))

            raw = await answer(
                text,
                doc_id,
                owner_id=owner_id,
                history=history,
                extra_system=extra_system,   # ✅ важное отличие
            )
            if not str(raw).strip():
                raw = "🤖 (пустой ответ)"

            bot_reply, plan = _extract_plan(str(raw))

            assistant_text_for_debit_and_memory = bot_reply or ""

            if isinstance(plan, dict) and plan.get("action") in {"list", "create", "update", "delete"}:
                action = plan.get("action")
                uid = owner_id
                cal_id = await get_user_calendar_id(uid) or "primary"

                if action == "list":
                    try:
                        tz = await get_user_timezone_oauth(uid)
                    except Exception:
                        tz = DEFAULT_TZ

                    r = plan.get("range") or {}
                    start = _parse_iso(r.get("start")) if isinstance(r, dict) else None
                    end = _parse_iso(r.get("end")) if isinstance(r, dict) else None
                    if not start or not end:
                        start, end, _ = parse_range_ru(text, tz)

                    try:
                        events = await list_events_between_oauth(uid, cal_id, start, end)
                        out = fmt_events(events)
                        msg = (bot_reply + "\n\n" if bot_reply else "") + out
                        await reply(message, msg, disable_web_page_preview=True)
                        handled_by_calendar = True
                        assistant_text_for_debit_and_memory = msg
                    except Exception:
                        await reply(message, "⚠️ Не удалось обратиться к Календарю. Проверьте подключение Google и права Calendar.")
                        handled_by_calendar = True
                        assistant_text_for_debit_and_memory = "⚠️ Не удалось обратиться к Календарю."

                elif action in {"create", "update", "delete"}:
                    token = secrets.token_urlsafe(8)
                    pending_calendar[token] = {
                        "plan": plan,
                        "uid": uid,
                        "cal_id": cal_id,
                        "chat_id": message.chat.id,
                        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
                    }

                    prompt = (bot_reply or "").strip() or "Подтвердите действие с календарём."
                    await reply(message, prompt, reply_markup=_kbd_confirm(token), disable_web_page_preview=True)
                    handled_by_calendar = True
                    assistant_text_for_debit_and_memory = prompt

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
            est = rough_token_estimate(text, assistant_text_for_debit_and_memory)
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
            await add_memory_message(owner_id, message.chat.id, "assistant", assistant_text_for_debit_and_memory)
        except Exception as e:
            logging.warning("add_memory_message failed: %s", e.__class__.__name__)

        if handled_by_calendar:
            return

        await reply(message, bot_reply, disable_web_page_preview=True)


    @dp.callback_query(F.data.startswith("cal:"))
    async def on_calendar_cb(callback: types.CallbackQuery):
        try:
            data = callback.data or ""
            parts = data.split(":")
            if len(parts) < 3:
                await callback.answer()
                return

            op = parts[1]  # ok/no/pick
            token = parts[2]

            item = pending_calendar.get(token)
            if not item:
                await callback.answer("Операция устарела", show_alert=True)
                return

            if callback.message and callback.message.chat.id != item["chat_id"]:
                await callback.answer("Недоступно в этом чате", show_alert=True)
                return

            if datetime.now(timezone.utc) > item["expires_at"]:
                pending_calendar.pop(token, None)
                await callback.answer("Истекло время подтверждения", show_alert=True)
                return

            if op == "no":
                pending_calendar.pop(token, None)
                if callback.message:
                    await callback.message.answer("Ок, отменено.")
                await callback.answer()
                return

            uid = item["uid"]
            cal_id = item["cal_id"]
            plan = item["plan"]
            act = plan.get("action")

            # pick: пользователь выбирает одно событие из кандидатов
            if op == "pick" and len(parts) == 4:
                idx = int(parts[3])
                cands = item.get("candidates") or []
                if idx < 0 or idx >= len(cands):
                    await callback.answer("Неверный выбор", show_alert=True)
                    return
                chosen = cands[idx]
                event_id = chosen.get("id")

                tz = await get_user_timezone_oauth(uid)

                if act == "delete":
                    ok = await delete_event_oauth(uid, event_id=event_id, calendar_id=cal_id)
                    pending_calendar.pop(token, None)
                    await callback.message.answer("✅ Событие удалено." if ok else "⚠️ Не удалось удалить событие.")
                    await callback.answer()
                    return

                if act == "update":
                    patch = plan.get("patch") or {}
                    patch_body: dict = {}

                    # 1) shift_minutes (универсально для "на час позже")
                    shift = patch.get("shift_minutes")
                    if isinstance(shift, (int, float)):
                        old_s, old_e = _event_bounds(chosen, tz)
                        if old_s and old_e and old_e > old_s:
                            new_s = old_s + timedelta(minutes=float(shift))
                            new_e = old_e + timedelta(minutes=float(shift))
                            patch_body["start"] = {"dateTime": new_s.isoformat(), "timeZone": tz.key}
                            patch_body["end"] = {"dateTime": new_e.isoformat(), "timeZone": tz.key}

                    # 2) абсолютные start/end (если заданы)
                    new_start = _parse_iso(patch.get("start")) if patch.get("start") else None
                    new_end = _parse_iso(patch.get("end")) if patch.get("end") else None
                    if new_start:
                        old_s, old_e = _event_bounds(chosen, tz)
                        if new_end is None and old_s and old_e and old_e > old_s:
                            new_end = new_start + (old_e - old_s)
                        if new_end:
                            patch_body["start"] = {"dateTime": new_start.isoformat(), "timeZone": tz.key}
                            patch_body["end"] = {"dateTime": new_end.isoformat(), "timeZone": tz.key}

                    for k in ("summary", "location", "description"):
                        if k in patch and patch[k] is not None:
                            patch_body[k] = patch[k]

                    if not patch_body:
                        pending_calendar.pop(token, None)
                        await callback.message.answer("Не вижу, что именно менять. Уточните новые детали.")
                        await callback.answer()
                        return

                    updated = await update_event_oauth(uid, event_id=event_id, patch=patch_body, calendar_id=cal_id)
                    pending_calendar.pop(token, None)
                    link = updated.get("htmlLink")
                    msg = "✅ Событие обновлено."
                    if link:
                        msg += f"\n{link}"
                    await callback.message.answer(msg, disable_web_page_preview=True)
                    await callback.answer()
                    return

                await callback.answer()
                return

            # ok: подтверждение операции
            if op == "ok":
                # CREATE
                if act == "create":
                    ev = plan.get("event") or {}
                    summary = (ev.get("summary") or "").strip()
                    start = _parse_iso(ev.get("start"))
                    end = _parse_iso(ev.get("end"))

                    if not summary or not start or not end:
                        pending_calendar.pop(token, None)
                        await callback.message.answer("Не хватает данных для записи. Уточните дату/время/услугу.")
                        await callback.answer()
                        return

                    created = await create_event_oauth(
                        uid,
                        summary=summary,
                        start=start,
                        end=end,
                        calendar_id=cal_id,
                        description=ev.get("description"),
                        location=ev.get("location"),
                    )
                    pending_calendar.pop(token, None)
                    link = created.get("htmlLink")
                    msg = "✅ Запись создана."
                    if link:
                        msg += f"\n{link}"
                    await callback.message.answer(msg, disable_web_page_preview=True)
                    await callback.answer()
                    return

                # UPDATE/DELETE -> сначала ищем кандидатов, если >1 — просим выбрать
                if act in {"update", "delete"}:
                    tz = await get_user_timezone_oauth(uid)
                    match = plan.get("match") or {}
                    range_days = int(match.get("range_days") or 14)
                    q = str(match.get("query") or "").lower().strip()
                    tokens = [t for t in re.split(r"[|,\s]+", q) if t]

                    start = datetime.now(tz)
                    end = start + timedelta(days=range_days)

                    events = await list_events_between_oauth(uid, cal_id, start, end)

                    def _fits(ev: dict) -> bool:
                        if not tokens:
                            return True
                        title = (ev.get("summary") or "").lower()
                        return any(t in title for t in tokens)

                    cands = [ev for ev in (events or []) if _fits(ev)]
                    cands.sort(key=lambda ev: _event_bounds(ev, tz)[0] or datetime.max.replace(tzinfo=timezone.utc))
                    cands = cands[:5]

                    if not cands:
                        pending_calendar.pop(token, None)
                        await callback.message.answer("Не нашёл подходящее событие. Уточните дату/время/название.")
                        await callback.answer()
                        return

                    if len(cands) == 1:
                        # сразу исполняем через pick-ветку
                        item["candidates"] = cands
                        pending_calendar[token] = item
                        await callback.message.answer(
                            "Нашёл одно событие, применяю…",
                            disable_web_page_preview=True,
                        )
                        # симулировать callback не будем — просто попросим нажать 1
                        await callback.message.answer(
                            "Подтвердите выбор события: 1",
                            reply_markup=_kbd_pick(token, 1),
                            disable_web_page_preview=True,
                        )
                        await callback.answer()
                        return

                    item["candidates"] = cands
                    pending_calendar[token] = item
                    await callback.message.answer(
                        "Какое событие выбрать?\n\n" + _format_candidates(cands),
                        reply_markup=_kbd_pick(token, len(cands)),
                        disable_web_page_preview=True,
                    )
                    await callback.answer()
                    return

            await callback.answer()

        except Exception:
            with contextlib.suppress(Exception):
                await callback.answer("Ошибка при обработке", show_alert=True)

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
