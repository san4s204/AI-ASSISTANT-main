from __future__ import annotations
import re
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from bot.states import Form
from keyboards import keyboard_return
from bot.services.db import update_user_token

router = Router(name="settings.token")

TOKEN_RE = re.compile(r"\d{9,11}:[A-Za-z0-9_-]{35}")

@router.callback_query(F.data == "change_API")
async def change_api(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Пришлите **API-токен вашего Telegram-бота**.\n\n"
        "Формат обычно такой: `1234567890:AA...`.\n"
        "Напишите *отмена*, чтобы вернуться.",
        reply_markup=keyboard_return(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.waiting_for_api)

@router.message(Form.waiting_for_api)
async def process_api_token(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if text.lower() in {"отмена", "cancel"}:
        await state.clear()
        await message.answer("Отменено.", reply_markup=keyboard_return())
        return

    if not TOKEN_RE.fullmatch(text):
        await message.answer(
            "Похоже, токен в неверном формате. Проверьте и пришлите ещё раз.\n\nПример: `1234567890:AA...`",
            reply_markup=keyboard_return(),
            parse_mode="Markdown"
        )
        return

    ok = await update_user_token(message.from_user.id, text)
    await message.answer("✅ Токен успешно обновлён!" if ok else "❌ Запись не найдена или нет активной подписки.", reply_markup=keyboard_return())
    await state.clear()
