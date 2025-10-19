from __future__ import annotations
from aiogram import Router, types, F
from bot.services.google_oauth import delete_refresh_token
from .helpers import kb_connect_google

router = Router(name="settings.google")

@router.callback_query(F.data == "connect_google")
async def connect_google(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Откройте ссылку и дайте доступ (Docs/Sheets Read-only).\nПосле подтверждения вернитесь в Telegram.",
        reply_markup=kb_connect_google(callback.from_user.id)
    )

@router.callback_query(F.data == "disconnect_google")
async def disconnect_google(callback: types.CallbackQuery):
    await delete_refresh_token(callback.from_user.id)
    await callback.answer("Google отключён.", show_alert=False)
    # Обновлять сам экран можно из base.menu, оставим как есть
