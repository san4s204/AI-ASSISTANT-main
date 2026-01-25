# bot/calendar_flow.py
from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Callable, Tuple

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


@dataclass
class PendingCalendar:
    plan: Dict[str, Any]
    uid: int
    cal_id: str
    chat_id: int
    expires_at: datetime
    candidates: Optional[List[Dict[str, Any]]] = None


class CalendarFlow:
    def __init__(
        self,
        *,
        default_tz,
        parse_range_ru: Callable,
        fmt_events: Callable,
        reply: Callable,  # ваш reply(message, ...)
        get_user_timezone_oauth: Callable,
        list_events_between_oauth: Callable,
        create_event_oauth: Callable,
        update_event_oauth: Callable,
        delete_event_oauth: Callable,
    ):
        self.default_tz = default_tz
        self.parse_range_ru = parse_range_ru
        self.fmt_events = fmt_events
        self.reply = reply

        self.get_user_timezone_oauth = get_user_timezone_oauth
        self.list_events_between_oauth = list_events_between_oauth
        self.create_event_oauth = create_event_oauth
        self.update_event_oauth = update_event_oauth
        self.delete_event_oauth = delete_event_oauth

        self.pending: Dict[str, PendingCalendar] = {}

        self._plan_re = re.compile(r"<calendar_plan>\s*(\{.*?\})\s*</calendar_plan>", re.S)

        self.CAL_PLAN_SYSTEM_TEMPLATE = (
            "Дополнение: ты должен определить, требуется ли действие с Google Calendar.\n"
            "В конце ответа ОБЯЗАТЕЛЬНО добавь блок:\n\n"
            "<calendar_plan>{JSON}</calendar_plan>\n\n"
            "JSON строго валидный (без комментариев). Схема:\n"
            "{\n"
            '  "action": "none" | "list" | "create" | "update" | "delete",\n'
            '  "needs_confirmation": true|false,\n'
            '  "missing_fields": [строки],\n'
            '  "range": {"start": "...", "end": "..."},\n'
            '  "event": {"summary": "...", "start": "...", "end": "...", "location": null, "description": null},\n'
            '  "match": {"strategy": "nearest", "range_days": 14, "query": "токены|поиска"},\n'
            '  "patch": {"start": "...", "end": "...", "shift_minutes": 60, "summary": "...", "location": "...", "description": "..."}\n'
            "}\n\n"
            "Правила:\n"
            "- Если пользователь не просит показать/создать/перенести/удалить запись — action=\"none\".\n"
            "- Для create/update/delete: needs_confirmation=true.\n"
            "- Времена указывай ISO-8601 с таймзоной {tz}. Сейчас: {now}.\n"
            "- Если пользователь говорит \"на час позже/раньше\" — используй patch.shift_minutes (60 или -60).\n"
            "- Если не хватает данных — заполни missing_fields и НЕ выдумывай.\n"
        )

    def build_extra_system(self) -> str:
        now = datetime.now(self.default_tz).isoformat()
        return self.CAL_PLAN_SYSTEM_TEMPLATE.format(now=now, tz=str(self.default_tz))

    def extract_plan(self, raw: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        txt = str(raw or "")
        matches = list(self._plan_re.finditer(txt))
        if not matches:
            return txt.strip(), None
        m = matches[-1]
        plan_raw = m.group(1)
        try:
            plan = json.loads(plan_raw)
        except Exception:
            plan = None
        cleaned = (txt[:m.start()] + txt[m.end():]).strip()
        return cleaned, plan

    @staticmethod
    def parse_iso(s: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def kbd_confirm(token: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"cal:ok:{token}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"cal:no:{token}"),
        ]])

    @staticmethod
    def kbd_pick(token: str, n: int) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=str(i + 1), callback_data=f"cal:pick:{token}:{i}")] for i in range(n)]
        rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"cal:no:{token}")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _event_bounds(self, ev: Dict[str, Any], tz):
        s = (ev.get("start") or {})
        e = (ev.get("end") or {})
        s_iso = s.get("dateTime") or s.get("date")
        e_iso = e.get("dateTime") or e.get("date")
        start = self.parse_iso(s_iso) if s_iso else None
        end = self.parse_iso(e_iso) if e_iso else None
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=tz)
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=tz)
        return start, end

    @staticmethod
    def _format_candidates(cands: List[Dict[str, Any]]) -> str:
        lines = []
        for i, ev in enumerate(cands, 1):
            title = ev.get("summary") or "Без названия"
            s = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date") or ""
            lines.append(f"{i}) {title} — {s}")
        return "\n".join(lines)

    async def handle_plan(
        self,
        *,
        message: types.Message,
        text: str,
        bot_reply: str,
        plan: Optional[Dict[str, Any]],
        uid: int,
        cal_id: str,
    ) -> Tuple[bool, str]:
        """
        Возвращает (handled_by_calendar, assistant_text_for_debit_and_memory).
        Если handled_by_calendar=True — ответ уже отправлен (или показано подтверждение).
        """
        assistant_text = bot_reply or ""

        if not (isinstance(plan, dict) and plan.get("action") in {"list", "create", "update", "delete"}):
            return False, assistant_text

        action = plan.get("action")

        if action == "list":
            try:
                try:
                    tz = await self.get_user_timezone_oauth(uid)
                except Exception:
                    tz = self.default_tz

                r = plan.get("range") or {}
                start = self.parse_iso(r.get("start")) if isinstance(r, dict) else None
                end = self.parse_iso(r.get("end")) if isinstance(r, dict) else None
                if not start or not end:
                    start, end, _ = self.parse_range_ru(text, tz)

                events = await self.list_events_between_oauth(uid, cal_id, start, end)
                out = self.fmt_events(events)
                msg = (bot_reply + "\n\n" if bot_reply else "") + out
                await self.reply(message, msg, disable_web_page_preview=True)
                return True, msg
            except Exception:
                msg = "⚠️ Не удалось обратиться к Календарю. Проверьте подключение Google и права Calendar."
                await self.reply(message, msg, disable_web_page_preview=True)
                return True, msg

        # create/update/delete -> confirm
        token = secrets.token_urlsafe(8)
        self.pending[token] = PendingCalendar(
            plan=plan,
            uid=uid,
            cal_id=cal_id,
            chat_id=message.chat.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        prompt = (bot_reply or "").strip() or "Подтвердите действие с календарём."
        await self.reply(message, prompt, reply_markup=self.kbd_confirm(token), disable_web_page_preview=True)
        return True, prompt

    async def handle_callback(self, callback: types.CallbackQuery) -> None:
        data = callback.data or ""
        parts = data.split(":")
        if len(parts) < 3:
            await callback.answer()
            return

        op = parts[1]
        token = parts[2]
        item = self.pending.get(token)
        if not item:
            await callback.answer("Операция устарела", show_alert=True)
            return

        if callback.message and callback.message.chat.id != item.chat_id:
            await callback.answer("Недоступно в этом чате", show_alert=True)
            return

        if datetime.now(timezone.utc) > item.expires_at:
            self.pending.pop(token, None)
            await callback.answer("Истекло время подтверждения", show_alert=True)
            return

        if op == "no":
            self.pending.pop(token, None)
            if callback.message:
                await callback.message.answer("Ок, отменено.")
            await callback.answer()
            return

        uid = item.uid
        cal_id = item.cal_id
        plan = item.plan
        act = plan.get("action")

        # pick
        if op == "pick" and len(parts) == 4:
            idx = int(parts[3])
            cands = item.candidates or []
            if idx < 0 or idx >= len(cands):
                await callback.answer("Неверный выбор", show_alert=True)
                return
            chosen = cands[idx]
            event_id = chosen.get("id")

            try:
                tz = await self.get_user_timezone_oauth(uid)
            except Exception:
                tz = self.default_tz

            if act == "delete":
                ok = await self.delete_event_oauth(uid, event_id=event_id, calendar_id=cal_id)
                self.pending.pop(token, None)
                await callback.message.answer("✅ Событие удалено." if ok else "⚠️ Не удалось удалить событие.")
                await callback.answer()
                return

            if act == "update":
                patch = plan.get("patch") or {}
                patch_body: Dict[str, Any] = {}

                shift = patch.get("shift_minutes")
                if isinstance(shift, (int, float)):
                    old_s, old_e = self._event_bounds(chosen, tz)
                    if old_s and old_e and old_e > old_s:
                        new_s = old_s + timedelta(minutes=float(shift))
                        new_e = old_e + timedelta(minutes=float(shift))
                        patch_body["start"] = {"dateTime": new_s.isoformat(), "timeZone": tz.key}
                        patch_body["end"] = {"dateTime": new_e.isoformat(), "timeZone": tz.key}

                new_start = self.parse_iso(patch.get("start")) if patch.get("start") else None
                new_end = self.parse_iso(patch.get("end")) if patch.get("end") else None
                if new_start:
                    old_s, old_e = self._event_bounds(chosen, tz)
                    if new_end is None and old_s and old_e and old_e > old_s:
                        new_end = new_start + (old_e - old_s)
                    if new_end:
                        patch_body["start"] = {"dateTime": new_start.isoformat(), "timeZone": tz.key}
                        patch_body["end"] = {"dateTime": new_end.isoformat(), "timeZone": tz.key}

                for k in ("summary", "location", "description"):
                    if k in patch and patch[k] is not None:
                        patch_body[k] = patch[k]

                if not patch_body:
                    self.pending.pop(token, None)
                    await callback.message.answer("Не вижу, что именно менять. Уточните новые детали.")
                    await callback.answer()
                    return

                updated = await self.update_event_oauth(uid, event_id=event_id, patch=patch_body, calendar_id=cal_id)
                self.pending.pop(token, None)
                link = updated.get("htmlLink")
                msg = "✅ Событие обновлено."
                if link:
                    msg += f"\n{link}"
                await callback.message.answer(msg, disable_web_page_preview=True)
                await callback.answer()
                return

            await callback.answer()
            return

        # ok
        if op == "ok":
            if act == "create":
                ev = plan.get("event") or {}
                summary = (ev.get("summary") or "").strip()
                start = self.parse_iso(ev.get("start"))
                end = self.parse_iso(ev.get("end"))
                if not summary or not start or not end:
                    self.pending.pop(token, None)
                    await callback.message.answer("Не хватает данных для записи. Уточните дату/время/услугу.")
                    await callback.answer()
                    return

                created = await self.create_event_oauth(
                    uid,
                    summary=summary,
                    start=start,
                    end=end,
                    calendar_id=cal_id,
                    description=ev.get("description"),
                    location=ev.get("location"),
                )
                self.pending.pop(token, None)
                link = created.get("htmlLink")
                msg = "✅ Запись создана."
                if link:
                    msg += f"\n{link}"
                await callback.message.answer(msg, disable_web_page_preview=True)
                await callback.answer()
                return

            if act in {"update", "delete"}:
                try:
                    tz = await self.get_user_timezone_oauth(uid)
                except Exception:
                    tz = self.default_tz

                match = plan.get("match") or {}
                range_days = int(match.get("range_days") or 14)
                q = str(match.get("query") or "").lower().strip()
                tokens = [t for t in re.split(r"[|,\s]+", q) if t]

                start = datetime.now(tz)
                end = start + timedelta(days=range_days)
                events = await self.list_events_between_oauth(uid, cal_id, start, end)

                def _fits(ev: Dict[str, Any]) -> bool:
                    if not tokens:
                        return True
                    title = (ev.get("summary") or "").lower()
                    return any(t in title for t in tokens)

                cands = [ev for ev in (events or []) if _fits(ev)]
                cands.sort(key=lambda ev: self._event_bounds(ev, tz)[0] or datetime.max.replace(tzinfo=timezone.utc))
                cands = cands[:5]

                if not cands:
                    self.pending.pop(token, None)
                    await callback.message.answer("Не нашёл подходящее событие. Уточните дату/время/название.")
                    await callback.answer()
                    return

                item.candidates = cands
                self.pending[token] = item
                await callback.message.answer(
                    "Какое событие выбрать?\n\n" + self._format_candidates(cands),
                    reply_markup=self.kbd_pick(token, len(cands)),
                    disable_web_page_preview=True,
                )
                await callback.answer()
                return

        await callback.answer()
