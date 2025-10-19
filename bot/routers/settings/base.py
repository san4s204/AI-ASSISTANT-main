from __future__ import annotations
from aiogram import Router, types, F
from aiogram.filters import Command
from .helpers import render_settings

router = Router(name="settings.base")

@router.callback_query(F.data == "setting_bot")
async def setting_bot_cb(callback: types.CallbackQuery):
    await render_settings(callback, callback.from_user.id)

@router.message(Command("settings"))
async def settings_cmd(message: types.Message):
    await render_settings(message, message.from_user.id)
