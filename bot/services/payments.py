from __future__ import annotations
import asyncio
import contextlib
from typing import Optional
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import PRICE_premium, MANAGER_GROUP
from keyboards import (
    keyboard_yookassa,
    keyboard_sub,
    keyboard_subscribe,
    keyboard_return,
)
from payments import create, check
from bot.services.db import get_subscription_until, set_subscription_active

# Константы проверки
CHECKERS: dict[int, asyncio.Task] = {}
MAX_ATTEMPTS = 200
SLEEP_SECONDS = 3


async def _cancel_checker(chatid: int) -> None:
    t = CHECKERS.pop(chatid, None)
    if t and not t.done():
        t.cancel()
        with contextlib.suppress(Exception):
            await t

class PaymentStates(StatesGroup):
    waiting_for_yookassa = State()
    payment_verified = State()
    attempts = State()  # оставлено для совместимости, можно убрать если нигде не используется


async def _safe_edit_text(message, text: str, reply_markup=None) -> None:
    """Безопасная правка текста: игнорирует мелкие ошибки типа MessageNotModified."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        pass

# -------- YooKassa --------

async def start_yookassa(callback, state: FSMContext, bot: Bot) -> None:
    # если уже что-то крутится — гасим и начинаем новое
    await _cancel_checker(callback.from_user.id)

    payment_url, payment_id = create(float(PRICE_premium), callback.from_user.id)

    # чтобы текст не был захардкожен на 599
    price_text = f"{float(PRICE_premium):.2f}"

    await _safe_edit_text(
        callback.message,
        (
            f"💳 Оплата на сумму {price_text} ₽\n\n"
            "Ссылка на оплату действительна в течение 10 минут.\n"
            "После оплаты подписка обновится автоматически."
        ),
        reply_markup=keyboard_yookassa(payment_url),
    )
    await state.set_state(PaymentStates.waiting_for_yookassa)
    await state.update_data(payment_id=payment_id)

    task = asyncio.create_task(
        verify_yookassa(state, bot, callback.from_user.id, callback.from_user.username)
    )
    CHECKERS[callback.from_user.id] = task


async def verify_yookassa(
    state: FSMContext,
    bot: Bot,
    chatid: int,
    username: Optional[str],
) -> bool:
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
                await bot.send_message(
                    chatid,
                    "Кажется, Вы уже оплатили подписку",
                    reply_markup=keyboard_sub(chatid),
                )
                return True

            # ❸ спрашиваем YooKassa
            try:
                paid = bool(check(payment_id))
            except Exception:
                paid = False

            if paid:
                await state.set_state(PaymentStates.payment_verified)
                await set_subscription_active(chatid, username, days=30)
                await bot.send_message(
                    chatid,
                    "✅ Оплата прошла успешно, подписка активирована!",
                    reply_markup=keyboard_subscribe(),
                )
                await state.clear()
                return True

            attempts += 1
            await asyncio.sleep(SLEEP_SECONDS)

        # таймаут
        await bot.send_message(
            chatid,
            "Время оплаты истекло, повторите попытку заново",
            reply_markup=keyboard_return(),
        )
        await state.clear()
        return False

    except asyncio.CancelledError:
        return False
    except Exception as e:
        try:
            if MANAGER_GROUP and int(MANAGER_GROUP) != 0:
                await bot.send_message(
                    MANAGER_GROUP,
                    text=(
                        f"Ошибка {e} с оплатой (YooKassa)\n"
                        f"<b>ID: {chatid}\n@{username}</b>"
                    ),
                    parse_mode="HTML",
                )
        except Exception:
            pass
        return False
    finally:
        CHECKERS.pop(chatid, None)
