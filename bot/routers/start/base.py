from __future__ import annotations
from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from bot.services.db import get_subscription_until, has_accepted_terms
from keyboards import keyboard_sub, keyboard_unsub, keyboard_terms
from .helpers import terms_text, welcome_text, send_demo_video_if_any

router = Router(name="start.base")

@router.message(CommandStart())
async def start_cmd(message: types.Message):
    uid = message.from_user.id

    # сначала — соглашение
    if not await has_accepted_terms(uid):
        await message.answer(
            text=terms_text(),
            reply_markup=keyboard_terms(),
            disable_web_page_preview=True,
            parse_mode="HTML",
        )
        return

    # после принятия — обычный сценарий
    res = await get_subscription_until(uid)
    await send_demo_video_if_any(message)
    if res:
        await message.answer(text="Главное меню:", reply_markup=keyboard_sub(uid))
    else:
        await message.answer(text=welcome_text(), parse_mode="HTML", disable_web_page_preview=True)
        await message.answer(text="Главное меню:", reply_markup=keyboard_unsub())

@router.callback_query(F.data == "return")
async def cq_return(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    uid = callback.from_user.id

    # если соглашение не принято — снова показываем его
    if not await has_accepted_terms(uid):
        await callback.message.edit_text(
            terms_text(),
            reply_markup=keyboard_terms(),
            disable_web_page_preview=True,
            parse_mode="HTML",
        )
        await callback.answer()
        return

    res = await get_subscription_until(uid)
    if res:
        await callback.message.edit_text("Главное меню:", reply_markup=keyboard_sub(uid))
    else:
        await callback.message.edit_text("Главное меню:", reply_markup=keyboard_unsub())
    await callback.answer()

@router.message(F.text.lower().in_(["🧭 главное меню", "главное меню"]))
async def open_main_menu(message: types.Message):
    uid = message.from_user.id
    res = await get_subscription_until(uid)
    kb = keyboard_sub(uid) if res else keyboard_unsub()
    await message.answer("Главное меню:", reply_markup=kb)
