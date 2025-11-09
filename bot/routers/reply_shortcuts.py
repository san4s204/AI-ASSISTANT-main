# bot/routers/reply_shortcuts.py
from __future__ import annotations
from aiogram import Router, types, F

from keyboards import (
    keyboard_sub,
    keyboard_setting_bot,
    keyboard_prompt_controls,
    keyboard_attach_source,
)
from bot.services.db import get_user_doc_id
from deepseek import doc

router = Router(name="reply_shortcuts")

# 1) Вкл/выкл «личного» бота — ТЕПЕРЬ БЕЗ run_bot/stop_bot
@router.message(F.text.in_(["🤖✅ Бот включен", "🤖❌ Бот выключен"]))
async def toggle_personal_bot(message: types.Message):
    """
    Раньше здесь запускали/останавливали дочернего бота напрямую,
    из-за чего получались двойные polling'и.

    Теперь просто показываем главное меню с inline-кнопкой,
    которая уже ведёт на общий хендлер `turn_on_off`.
    """
    await message.answer(
        "Управление запуском бота теперь на кнопке в меню ниже 👇",
        reply_markup=keyboard_sub(message.from_user.id),
    )


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
