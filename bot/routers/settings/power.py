from __future__ import annotations
import asyncio
import logging

from aiogram import Router, types, F

from keyboards import keyboard_sub, keyboard_return, keyboard_unsub, state_bot
from bot.services.db import (
    get_subscription_until,
    update_user_state,
    get_user_token_and_doc,
)
from bot.services.google_oauth import has_google_oauth
from .helpers import REQUIRE_GOOGLE, kb_connect_google
from openrouter import run_bot, stop_user_bots

router = Router(name="settings.power")


@router.callback_query(F.data == "turn_on_off")
async def turn_cb(callback: types.CallbackQuery):
    uid = callback.from_user.id
    current = state_bot(uid)

    # ► ВКЛЮЧИТЬ
    if current == "🤖❌ Бот выключен":
        # 1) проверяем подписку
        if not await get_subscription_until(uid):
            await callback.answer(
                "Подписка не активна. Продлите её через «💰 Оплата».",
                show_alert=True,
            )
            return

        # 2) проверяем Google OAuth (если обязателен)
        if REQUIRE_GOOGLE and not await has_google_oauth(uid):
            await callback.message.edit_text(
                "Чтобы включить бота, подключите Google-аккаунт:",
                reply_markup=kb_connect_google(uid),
            )
            await callback.answer()
            return

        # 3) токен бота
        token, word_file = await get_user_token_and_doc(uid)
        if not token:
            await callback.message.answer(
                "Не задан API-токен вашего Telegram-бота.\n"
                "Укажите его в «/settings → Изменить API-токен».",
                reply_markup=keyboard_return(),
            )
            await callback.answer()
            return

        # 4) на всякий случай гасим старые воркеры этого пользователя
        await stop_user_bots(uid)

        # 5) запускаем нового
        await callback.answer("Запускаю вашего бота ✅")
        await update_user_state(uid, "active")
        await callback.message.edit_reply_markup(reply_markup=keyboard_sub(uid))
        try:
            await asyncio.sleep(0)
            await run_bot(token, word_file, uid)
        except Exception as e:
            await update_user_state(uid, "stop")
            await callback.message.answer(
                f"Не удалось запустить бота: {e}", reply_markup=keyboard_return()
            )

    # ► ВЫКЛЮЧИТЬ
    elif current == "🤖✅ Бот включен":
        await callback.answer("Останавливаю вашего бота ❌")
        await update_user_state(uid, "stop")
        await callback.message.edit_reply_markup(reply_markup=keyboard_sub(uid))

        stopped = await stop_user_bots(uid)
        if not stopped:
            logging.info(
                "stop_user_bots: у uid=%s не найдено активных воркеров",
                uid,
            )

    # ► Неясное состояние — просто перерисуем меню
    else:
        await callback.message.edit_reply_markup(
            reply_markup=keyboard_sub(uid)
            if await get_subscription_until(uid)
            else keyboard_unsub()
        )
        await callback.answer("Обновил состояние, попробуйте ещё раз.")
