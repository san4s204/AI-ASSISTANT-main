from __future__ import annotations
from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from bot.services.payments import start_yookassa, start_cryptobot
from aiogram import F

from keyboards import (
    keyboard_payment_premium,
    keyboard_sub, keyboard_unsub, keyboard_change_ai,
    r_keyboard_sub,
)

from bot.services.db import get_subscription_until

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
            "Выберите своего ИИ-Агента",
            reply_markup=keyboard_change_ai()
        )

@router.callback_query(F.data == "ai_premium")
async def cq_ai_premium(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Стоимость подписки:\n\n1 месяц - 599 ₽ (7.2 USDT)",
        reply_markup=keyboard_payment_premium()
    )

@router.callback_query(F.data == "yookassa_premium")
async def cq_yookassa(callback: types.CallbackQuery, state: FSMContext):
    await start_yookassa(callback, state, callback.bot)

@router.callback_query(F.data == "cryptobot_premium")
async def cq_crypto_bot(callback: types.CallbackQuery, state: FSMContext):
    await start_cryptobot(callback, state, callback.bot)

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
