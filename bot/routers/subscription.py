from __future__ import annotations
from aiogram import Router, types
from aiogram import F
from aiogram.fsm.context import FSMContext
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from keyboards import keyboard_sub, keyboard_subscribe, keyboard_change_ai
from bot.services.db import get_subscription_until

TZ_MOSCOW = ZoneInfo("Europe/Moscow")

router = Router(name="subscription")

def format_sub_until(raw) -> str:
    """Принимает ISO-строку или datetime и отдаёт '09:15:49 ⌛️ 04.11.2025'."""
    if raw is None:
        return ""
    if isinstance(raw, datetime):
        dt = raw
    else:
        s = str(raw).strip()
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except Exception:
                    pass
            else:
                # если формат неизвестен — вернём как есть
                return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(TZ_MOSCOW)
    return f"{local:%H:%M:%S} ⌛️ {local:%d.%m.%Y}"

# "⏳ Подписка" (reply-кнопка)
@router.message(F.text == "⏳ Подписка")
async def check_sub_message(message: types.Message):
    sub_until = await get_subscription_until(message.from_user.id)  
    if sub_until:
        await message.answer(f"Подписка действительна до: {format_sub_until(sub_until)}")
    else:
        await message.answer("Произошла ошибка, обратитесь в поддержку")

# "💰 Оплата" (reply-кнопка)
@router.message(F.text == "💰 Оплата")
async def mes_payment(message: types.Message):
    res = await get_subscription_until(message.from_user.id)
    if res:
        # Просто шлём два сообщения пользователю — без chat_id/message_id, aiogram v3 сам подставит
        await message.answer("Главное меню", reply_markup=keyboard_sub(message.from_user.id))
        await message.answer("Выберите действие в главном меню:", reply_markup=keyboard_subscribe())
    else:
        await message.answer(
            "Выберите своего ИИ-Агента\nПодробное описание каждого в нашем канале:",
            reply_markup=keyboard_change_ai()
        )


@router.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    res = await get_subscription_until(callback.from_user.id)
    if res:
        await callback.answer(f"Подписка действительна до: {format_sub_until(res)}")
    else:
        await callback.answer("Произошла ошибка, обратитесь в поддержку")