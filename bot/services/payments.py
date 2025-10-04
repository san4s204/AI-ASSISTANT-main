from __future__ import annotations
import asyncio
from typing import Optional

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import PRICE_premium, AMOUNT_premium, ASSET, MANAGER_GROUP
from keyboards import (
    keyboard_yookassa, keyboard_crypto_bot,
    keyboard_sub, keyboard_subscribe, keyboard_return
)
from payments import create, check, cp  # cp = CryptoPay(...)
from bot.services.db import get_subscription_until, set_subscription_active

# Константы проверки
MAX_ATTEMPTS = 200            # попыток проверки статуса
SLEEP_SECONDS = 3             # пауза между проверками, сек

class PaymentStates(StatesGroup):
    waiting_for_yookassa = State()
    waiting_for_crypto_bot = State()
    payment_verified = State()     # финальное состояние (коротко используем и очищаем)
    attempts = State()             # (необязательно; оставлено для совместимости)

async def _safe_edit_text(message, text: str, reply_markup=None) -> None:
    """Безопасная правка текста: игнорирует мелкие ошибки типа MessageNotModified."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        # Например, если текст/markup не изменились или сообщение уже удалено.
        pass

# -------- YooKassa --------

async def start_yookassa(callback, state: FSMContext, bot: Bot) -> None:
    """Создать счёт YooKassa и запустить проверку оплаты."""
    current = await state.get_state()
    if current in (PaymentStates.waiting_for_yookassa.state,
                   PaymentStates.waiting_for_crypto_bot.state):
        await callback.answer("Вы уже в процессе оплаты. Подождите завершения.")
        return

    payment_url, payment_id = create(PRICE_premium, callback.from_user.id)
    await _safe_edit_text(
        callback.message,
        "💳 Оплата на сумму 599.00 ₽\n\nСсылка на оплату действительна в течение 10 минут",
        reply_markup=keyboard_yookassa(payment_url)
    )
    await state.set_state(PaymentStates.waiting_for_yookassa)
    await state.update_data(payment_id=payment_id)

    await verify_yookassa(state, bot, callback.from_user.id, callback.from_user.username)

async def verify_yookassa(
    state: FSMContext,
    bot: Bot,
    chatid: int,
    username: Optional[str],
) -> bool:
    """Циклически проверяет оплату YooKassa до таймаута."""
    try:
        user_data = await state.get_data()
        payment_id = user_data.get("payment_id")
        attempts = 0

        while attempts < MAX_ATTEMPTS:
            # Если подписка уже вручную/раньше активна — выходим
            if await get_subscription_until(chatid):
                await bot.send_message(chatid, "Кажется, Вы уже оплатили подписку", reply_markup=keyboard_sub(chatid))
                return True

            # Проверяем YooKassa (синхронная функция — оборачиваем просто вызовом)
            try:
                paid = bool(check(payment_id))
            except Exception:
                paid = False

            if paid:
                await state.set_state(PaymentStates.payment_verified)
                await set_subscription_active(chatid, username, days=30)
                await bot.send_message(chatid, "✅ Оплата прошла успешно, подписка активирована!", reply_markup=keyboard_subscribe())
                await state.clear()
                return True

            attempts += 1
            await asyncio.sleep(SLEEP_SECONDS)

        # Таймаут
        await bot.send_message(chatid, "Время оплаты истекло, повторите попытку заново", reply_markup=keyboard_return())
        await state.clear()
        return False

    except Exception as e:
        try:
            if MANAGER_GROUP and int(MANAGER_GROUP) != 0:
                await bot.send_message(
                    MANAGER_GROUP,
                    text=f"Ошибка {e} с оплатой (YooKassa)\n<b>ID: {chatid}\n@{username}</b>",
                    parse_mode="HTML"
                )
        except Exception:
            pass
        return False

# -------- Crypto Bot --------

async def start_cryptobot(callback, state: FSMContext, bot: Bot) -> None:
    """Создать счёт Crypto Bot и запустить проверку оплаты."""
    current = await state.get_state()
    if current in (PaymentStates.waiting_for_yookassa.state,
                   PaymentStates.waiting_for_crypto_bot.state):
        await callback.answer("Вы уже в процессе оплаты. Подождите завершения.")
        return

    invoice = await cp.create_invoice(asset=ASSET, amount=AMOUNT_premium)
    invoice_url = str(getattr(invoice, "bot_invoice_url", invoice))
    invoice_id = str(getattr(invoice, "invoice_id", ""))

    await _safe_edit_text(
        callback.message,
        "💸 Оплата на сумму 7.2 USDT \n\nСсылка на оплату действительна в течение 10 минут",
        reply_markup=keyboard_crypto_bot(invoice_url)
    )
    await state.set_state(PaymentStates.waiting_for_crypto_bot)
    await state.update_data(invoice_id=invoice_id)

    await verify_cryptobot(state, bot, callback.from_user.id, callback.from_user.username)

async def verify_cryptobot(
    state: FSMContext,
    bot: Bot,
    chatid: int,
    username: Optional[str],
) -> bool:
    """Циклически проверяет оплату Crypto Bot до таймаута."""
    try:
        from payments import cript  # async check(invoice_id) -> bool/“Yes”

        user_data = await state.get_data()
        invoice_id = user_data.get("invoice_id")
        attempts = 0

        while attempts < MAX_ATTEMPTS:
            if await get_subscription_until(chatid):
                await bot.send_message(chatid, "Кажется, Вы уже оплатили подписку", reply_markup=keyboard_sub(chatid))
                return True

            try:
                res = await cript(invoice_id)
                paid = (res is True) or (isinstance(res, str) and res.lower() in {"yes", "true", "paid"})
            except Exception:
                paid = False

            if paid:
                await state.set_state(PaymentStates.payment_verified)
                await set_subscription_active(chatid, username, days=30)
                await bot.send_message(chatid, "✅ Оплата прошла успешно, подписка активирована!", reply_markup=keyboard_subscribe())
                await state.clear()
                return True

            attempts += 1
            await asyncio.sleep(SLEEP_SECONDS)

        # Таймаут
        await bot.send_message(chatid, "Время оплаты истекло, повторите попытку заново", reply_markup=keyboard_return())
        await state.clear()
        return False

    except Exception as e:
        try:
            if MANAGER_GROUP and int(MANAGER_GROUP) != 0:
                await bot.send_message(
                    MANAGER_GROUP,
                    text=f"Ошибка {e} с оплатой (Crypto Bot)\n<b>ID: {chatid}\n@{username}</b>",
                    parse_mode="HTML"
                )
        except Exception:
            pass
        return False
