# bot/services/subscription.py
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot
from bot.services.db import (
    find_users_to_expire,
    mark_subscriptions_expired,
    get_user_token_and_doc,
)
from openrouter import stop_bot  # твоя функция остановки дочерних ботов

CHECK_INTERVAL_SEC = 60 * 30  # каждые 30 мин; можно 5–10 мин

async def subscription_expirer(bot: Bot, interval: int = CHECK_INTERVAL_SEC):
    """
    Периодически помечает истёкшие подписки как неактивные,
    останавливает их "дочерние" боты и уведомляет пользователей.
    """
    while True:
        try:
            now = datetime.now()  # оставим naive, чтобы совпадало с форматом date_end
            to_expire = await find_users_to_expire(now)
            if to_expire:
                user_ids = [uid for uid, _ in to_expire]
                # 1) пометить истекшими
                await mark_subscriptions_expired(user_ids)

                # 2) остановить активных
                for uid, state in to_expire:
                    if state == "active":
                        token, _ = await get_user_token_and_doc(uid)
                        if token:
                            try:
                                await stop_bot(str(token))
                            except Exception:
                                logging.exception("stop_bot failed for %s", uid)

                # 3) уведомить
                for uid, _ in to_expire:
                    try:
                        await bot.send_message(
                            uid,
                            "⛔️ Ваша подписка закончилась. Доступ к боту приостановлен.\n"
                            "Нажмите «💰 Оплата» в меню, чтобы продлить.",
                        )
                    except Exception:
                        # без падений, если нельзя доставить
                        pass

        except Exception:
            logging.exception("subscription_expirer loop failed")

        await asyncio.sleep(interval)
