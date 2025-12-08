from __future__ import annotations
from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from bot.services.payments import start_yookassa, _cancel_checker, _safe_edit_text
from aiogram import F
from keyboards import (
    keyboard_payment_premium,
    keyboard_sub, keyboard_unsub, keyboard_change_ai,
    r_keyboard_sub, keyboard_return
)

from bot.services.db import get_subscription_until

CB_CANCEL = "pay_cancel"
CB_TO_YK = "pay_switch_yk"
CB_TO_CB = "pay_switch_cb"

router = Router(name="payments")

@router.callback_query(F.data == "payment")
async def cq_payment(callback: types.CallbackQuery):
    # показать главное меню оплаты / выбор агента
    res = await get_subscription_until(callback.from_user.id)
    if res:
        try:
            await callback.message.edit_text("Главное меню", reply_markup=keyboard_sub(callback.from_user.id))
        except Exception:
            pass
    else:
        await callback.message.edit_text(
            "Выберите продукт для оплаты:",
            reply_markup=keyboard_change_ai()
        )

@router.callback_query(F.data == "ai_premium")
async def cq_ai_premium(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💰 Выберите способ оплаты:\n\n1 месяц - 599 ₽ (7.4 USDT)",
        reply_markup=keyboard_payment_premium()
    )

@router.callback_query(F.data == "yookassa_premium")
async def cq_yookassa(callback: types.CallbackQuery, state: FSMContext):
    await start_yookassa(callback, state, callback.bot)


@router.callback_query(F.data == "subscribe")
async def subscribe(callback: types.CallbackQuery):
    res = await get_subscription_until(callback.from_user.id)
    if res:
        # как в твоём main.py: короткое подтверждение + переход в главное меню
        await callback.message.answer(
            text=f"Ваша подписка активна до {res}",
            reply_markup=r_keyboard_sub()
        )
        await callback.message.edit_text("Главное меню:", reply_markup=keyboard_sub(callback.from_user.id))
    else:
        await callback.message.edit_text("Главное меню:", reply_markup=keyboard_unsub())

@router.callback_query(F.data == CB_CANCEL)
async def pay_cancel(callback: types.CallbackQuery, state: FSMContext):
    await _cancel_checker(callback.from_user.id)  # погасим фоновые проверяльщики
    await state.clear()
    await _safe_edit_text(
        callback.message,
        "Оплата отменена. Выберите способ оплаты заново:",
        reply_markup=keyboard_return()
    )
    await callback.answer("Отменено")