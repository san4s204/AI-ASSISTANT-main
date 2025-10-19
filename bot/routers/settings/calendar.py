from __future__ import annotations
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.states import Form
from keyboards import keyboard_calendar_menu, keyboard_setting_bot
from providers.google_calendar_oauth_provider import list_calendars_oauth
from bot.services.db import set_user_calendar_id, get_user_calendar_id, clear_user_calendar_id
from .helpers import render_prompt_preview

router = Router(name="settings.calendar")

@router.callback_query(F.data == "calendar_menu")
async def calendar_menu(callback: types.CallbackQuery):
    is_linked = bool(await get_user_calendar_id(callback.from_user.id))
    await callback.message.edit_text("Настройки календаря:", reply_markup=keyboard_calendar_menu(is_linked))

@router.callback_query(F.data == "change_CAL")
async def change_calendar(callback: types.CallbackQuery, state: FSMContext):
    try:
        calendars = await list_calendars_oauth(callback.from_user.id)
    except Exception:
        await callback.answer("Не могу получить список календарей.\nПроверь подключение Google (OAuth) и что включён Calendar API.", show_alert=True)
        return

    if not calendars:
        await callback.answer("Календари не найдены.", show_alert=True)
        return

    calendars = calendars[:20]
    await state.update_data(cal_list=calendars)
    await state.set_state(Form.waiting_for_calendar_pick)

    kb = InlineKeyboardBuilder()
    for i, it in enumerate(calendars):
        title = it.get("summary") or "(без названия)"
        if it.get("primary"):
            title = f"⭐ {title}"
        kb.add(InlineKeyboardButton(text=title[:32], callback_data=f"pick_cal:{i}"))
    kb.add(InlineKeyboardButton(text="↩️ Назад", callback_data="return"))
    kb.adjust(1, 1, 1, 1)
    await callback.message.edit_text("Выбери календарь:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("pick_cal:"), Form.waiting_for_calendar_pick)
async def pick_calendar(callback: types.CallbackQuery, state: FSMContext):
    try:
        idx = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer("Неверный выбор.", show_alert=True)
        return

    data = await state.get_data()
    cal_list = data.get("cal_list") or []
    if idx < 0 or idx >= len(cal_list):
        await callback.answer("Элемент не найден.", show_alert=True)
        return

    cal_id = cal_list[idx]["id"]
    try:
        await set_user_calendar_id(callback.from_user.id, cal_id)
    finally:
        await state.clear()

    await callback.answer("✅ Календарь привязан.", show_alert=False)
    await callback.message.edit_text("Настройка бота:", reply_markup=keyboard_setting_bot())

@router.callback_query(F.data == "cal_unlink")
async def cal_unlink(callback: types.CallbackQuery):
    ok = await clear_user_calendar_id(callback.from_user.id)
    if ok:
        await callback.answer("✅ Календарь отвязан.", show_alert=False)
        await render_prompt_preview(callback, callback.from_user.id)  # перерисуем превью источника
    else:
        await callback.answer("Нечего отвязывать — календарь не привязан.", show_alert=True)
