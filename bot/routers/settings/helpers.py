from __future__ import annotations
import os, re
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from keyboards import (
    keyboard_setting_bot, keyboard_unsub,
    keyboard_attach_source, keyboard_prompt_controls
)
from bot.services.db import get_subscription_until, get_user_doc_id
from deepseek import doc

BASE_URL = os.getenv("BASE_URL", "https://example.com")
REQUIRE_GOOGLE = os.getenv("FORCE_GOOGLE_OAUTH", "1") == "1"

_DOC_RE = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")
_SHEET_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")

async def ensure_active_sub(ctx: types.Message | types.CallbackQuery, uid: int) -> bool:
    """True если подписка активна, иначе показываем предупреждение и главное меню без подписки."""
    if await get_subscription_until(uid):
        return True
    msg = "Подписка не активна. Продлите её через «💰 Оплата»."
    if isinstance(ctx, types.CallbackQuery):
        await ctx.answer(msg, show_alert=True)
        await ctx.message.edit_text("Главное меню:", reply_markup=keyboard_unsub())
    else:
        await ctx.answer(msg, reply_markup=keyboard_unsub())
    return False

def kb_connect_google(uid: int) -> InlineKeyboardMarkup:
    url = f"{BASE_URL}/oauth/google/start?uid={uid}"
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="🔗 Подключить Google", url=url))
    kb.add(InlineKeyboardButton(text="↩️ Назад", callback_data="return"))
    kb.adjust(1, 1)
    return kb.as_markup()

async def render_settings(ctx: types.Message | types.CallbackQuery, uid: int) -> None:
    if not await ensure_active_sub(ctx, uid):
        return
    if isinstance(ctx, types.CallbackQuery):
        await ctx.message.edit_text("Настройка бота:", reply_markup=keyboard_setting_bot())
    else:
        await ctx.answer("Настройка бота:", reply_markup=keyboard_setting_bot())

async def render_prompt_preview(ctx: types.Message | types.CallbackQuery, uid: int) -> None:
    if not await ensure_active_sub(ctx, uid):
        return

    link = await get_user_doc_id(uid)
    if not link:
        text = "Источник не привязан. Добавьте Документ или Таблицу:"
        if isinstance(ctx, types.CallbackQuery):
            await ctx.message.edit_text(text, reply_markup=keyboard_attach_source())
        else:
            await ctx.answer(text, reply_markup=keyboard_attach_source())
        return

    try:
        ans = await doc(link, owner_user_id=uid)
        if ans.get("kind") == "sheet":
            url = f"https://docs.google.com/spreadsheets/d/{ans['id']}/edit"
            src_name = "Google Sheets"
        else:
            url = f"https://docs.google.com/document/d/{ans['id']}/edit"
            src_name = "Google Docs"
        preview = (
            f"Источник: {src_name}\n"
            f"Название: {ans.get('title','')}\n"
            # f"Содержимое (превью):\n{ans.get('content','')}"
        )
        if isinstance(ctx, types.CallbackQuery):
            await ctx.message.edit_text(preview, reply_markup=keyboard_prompt_controls(url))
        else:
            await ctx.answer(preview, reply_markup=keyboard_prompt_controls(url))
    except Exception:
        warn = "Не удалось открыть источник.\nПопробуйте /settings → «🔗 Подключить Google»"
        if isinstance(ctx, types.CallbackQuery):
            await ctx.answer(warn, show_alert=True)
        else:
            await ctx.answer(warn)

def extract_source_id(link: str | None) -> str | None:
    if not link:
        return None
    m_doc = _DOC_RE.search(link)
    if m_doc:
        return m_doc.group(1)
    m_sheet = _SHEET_RE.search(link)
    if m_sheet:
        return m_sheet.group(1)
    return None
