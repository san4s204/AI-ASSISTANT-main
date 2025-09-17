# bot/routers/reply_shortcuts.py
from __future__ import annotations
import asyncio
from aiogram import Router, types, F

from keyboards import (
    keyboard_sub,
    keyboard_setting_bot,
    keyboard_prompt_controls,
    keyboard_attach_source,
)
from bot.services.db import (
    update_user_state,
    get_user_token_and_doc,
    get_user_doc_id,
)
from openrouter import run_bot, stop_bot
from deepseek import doc

router = Router(name="reply_shortcuts")

# 1) Вкл/выкл «личного» бота (динамическая кнопка с текстом state_bot)
@router.message(F.text.in_(["🤖✅ Бот включен", "🤖❌ Бот выключен"]))
async def toggle_personal_bot(message: types.Message):
    label = (message.text or "").strip()

    if "выключен" in label:
        await message.answer("Запускаю Вашего бота ✅")
        await asyncio.sleep(0.5)
        await update_user_state(message.from_user.id, "active")
        await message.answer("Главное меню:", reply_markup=keyboard_sub(message.from_user.id))

        token, word_file = await get_user_token_and_doc(message.from_user.id)
        if token:
            try:
                await run_bot(token, word_file, message.from_user.id)
            except Exception:
                # не валимся с ошибкой — просто показываем меню
                pass
    else:
        await message.answer("Останавливаю Вашего бота ❌")
        await update_user_state(message.from_user.id, "stop")
        await message.answer("Главное меню:", reply_markup=keyboard_sub(message.from_user.id))

        token, _ = await get_user_token_and_doc(message.from_user.id)
        if token:
            try:
                await stop_bot(str(token))
            except Exception:
                pass


# 2) Открыть настройки (inline-меню)
@router.message(F.text == "🔧 Настройки Бота")
async def open_settings(message: types.Message):
    await message.answer("Настройка бота:", reply_markup=keyboard_setting_bot())


# 3) Просмотр и редактирование промпта (Docs/Sheets)
@router.message(F.text == "📝 Просмотр и редактирование промпта")
async def view_prompt_source(message: types.Message):
    link = await get_user_doc_id(message.from_user.id)
    if not link:
        await message.answer(
            "Источник не привязан. Добавьте Документ или Таблицу в настройках.",
            reply_markup=keyboard_attach_source(),
        )
        return

    try:
        ans = await doc(link, owner_user_id=message.from_user.id)  # {'id','title','content','kind'}
        kind = ans.get("kind")

        if kind == "sheet":
            url = f"https://docs.google.com/spreadsheets/d/{ans['id']}/edit"
            src_name = "Google Sheets"
        else:
            url = f"https://docs.google.com/document/d/{ans['id']}/edit"
            src_name = "Google Docs"

        await message.answer(
            f"Источник: {src_name}\n"
            f"Название: {ans.get('title','')}\n"
            f"Содержимое (превью):\n{ans.get('content','')}",
            reply_markup=keyboard_prompt_controls(url),
        )
    except Exception:
        await message.answer(
            "Не удалось открыть источник. Проверьте доступы (OAuth/шаринг), включённые API и корректность ссылки/ID."
        )
