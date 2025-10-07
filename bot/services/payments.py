from __future__ import annotations
import asyncio
from typing import Optional
import contextlib
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import os
from config import PRICE_premium, AMOUNT_premium, ASSET, MANAGER_GROUP
from keyboards import (
    keyboard_yookassa, keyboard_crypto_bot,
    keyboard_sub, keyboard_subscribe, keyboard_return
)
from payments import create, check, cp  # cp = CryptoPay(...)
from bot.services.db import get_subscription_until, set_subscription_active

# Константы проверки
CHECKERS: dict[int, asyncio.Task] = {}
MAX_ATTEMPTS = 200            # попыток проверки статуса
SLEEP_SECONDS = 3             # пауза между проверками, сек



async def _cancel_checker(chatid: int) -> None:
    t = CHECKERS.pop(chatid, None)
    if t and not t.done():
        t.cancel()
        with contextlib.suppress(Exception):
            await t

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
    # если уже что-то крутится — гасим и начинаем новое
    await _cancel_checker(callback.from_user.id)

    payment_url, payment_id = create(PRICE_premium, callback.from_user.id)
    await _safe_edit_text(
        callback.message,
        "💳 Оплата на сумму 599.00 ₽\n\nСсылка на оплату действительна в течение 10 минут",
        reply_markup=keyboard_yookassa(payment_url)
    )
    await state.set_state(PaymentStates.waiting_for_yookassa)
    await state.update_data(payment_id=payment_id)

    # ЗАПУСК В ФОНЕ (не await!)
    task = asyncio.create_task(
        verify_yookassa(state, bot, callback.from_user.id, callback.from_user.username)
    )
    CHECKERS[callback.from_user.id] = task

async def verify_yookassa(state: FSMContext, bot: Bot, chatid: int, username: Optional[str]) -> bool:
    try:
        user_data = await state.get_data()
        payment_id = user_data.get("payment_id")
        attempts = 0

        while attempts < MAX_ATTEMPTS:
            # ❶ если пользователь отменил/переключился — выходим сразу
            if (await state.get_state()) != PaymentStates.waiting_for_yookassa.state:
                return False

            # ❷ подписка уже активна — выходим
            if await get_subscription_until(chatid):
                await bot.send_message(chatid, "Кажется, Вы уже оплатили подписку", reply_markup=keyboard_sub(chatid))
                return True

            # ❸ спрашиваем YooKassa
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

        # таймаут
        await bot.send_message(chatid, "Время оплаты истекло, повторите попытку заново", reply_markup=keyboard_return())
        await state.clear()
        return False

    except asyncio.CancelledError:
        # отменили вручную — молча выходим
        return False
    except Exception as e:
        # уведомление менеджеру — как у вас
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
    finally:
        # снимаем таск из реестра
        CHECKERS.pop(chatid, None)

# -------- Crypto Bot --------

async def start_cryptobot(callback, state: FSMContext, bot: Bot) -> None:
    await _cancel_checker(callback.from_user.id)

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

    task = asyncio.create_task(
        verify_cryptobot(state, bot, callback.from_user.id, callback.from_user.username)
    )
    CHECKERS[callback.from_user.id] = task


async def verify_cryptobot(state: FSMContext, bot: Bot, chatid: int, username: Optional[str]) -> bool:
    try:
        from payments import cript

        user_data = await state.get_data()
        invoice_id = user_data.get("invoice_id")
        attempts = 0

        while attempts < MAX_ATTEMPTS:
            if (await state.get_state()) != PaymentStates.waiting_for_crypto_bot.state:
                return False

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

        await bot.send_message(chatid, "Время оплаты истекло, повторите попытку заново", reply_markup=keyboard_return())
        await state.clear()
        return False

    except asyncio.CancelledError:
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
    finally:
        CHECKERS.pop(chatid, None)
