from __future__ import annotations
from aiogram import Router, types, F
from keyboards import keyboard_confirm_delete_source, keyboard_setting_bot
from providers.redis_provider import delete_by_pattern
from bot.services.db import get_user_doc_id, update_user_document
from .helpers import extract_source_id

router = Router(name="settings.source")

@router.callback_query(F.data == "delete_source")
async def delete_source(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Удалить текущий источник (Документ/Таблица)? Это действие нельзя отменить.",
        reply_markup=keyboard_confirm_delete_source()
    )

@router.callback_query(F.data == "confirm_delete_source")
async def confirm_delete_source(callback: types.CallbackQuery):
    link = await get_user_doc_id(callback.from_user.id)
    src_id = extract_source_id(link)
    if src_id:
        try:
            await delete_by_pattern(f"openrouter:{src_id}:*")
        except Exception:
            pass
    await update_user_document(callback.from_user.id, None)
    await callback.message.edit_text("Источник отвязан. Вы можете привязать новый в «Настройка бота».", reply_markup=keyboard_setting_bot())
