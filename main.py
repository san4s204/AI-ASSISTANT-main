# main.py
import asyncio
import logging
from contextlib import suppress
import signal

from aiogram import Bot, Dispatcher, Router
from aiosend import CryptoPay, TESTNET

from config import TOKEN, CRYPTOTOKEN
from bot.web.oauth_app import start_oauth_webserver

# Необязательно, но полезно: фоновая задача, которая гасит истёкшие подписки
# Если файла нет — можно временно закомментировать импорт и запуск.
from bot.services.subscription import subscription_expirer

# === Инициализация ===
cp = CryptoPay(CRYPTOTOKEN, TESTNET)  # если не используешь здесь — можно удалить
bot = Bot(TOKEN)
dp = Dispatcher()
router = Router(name="core")  # если пустой — можно не подключать

# Роутеры
from bot.routers.start import router as start_router
from bot.routers.subscription import router as subscription_router
from bot.routers.payments import router as payments_router
from bot.routers.settings import router as settings_router
from bot.routers.reply_shortcuts import router as reply_router

dp.include_router(start_router)
dp.include_router(subscription_router)
dp.include_router(payments_router)
dp.include_router(settings_router)
dp.include_router(reply_router)
dp.include_router(router)


async def _run():
    """
    Поднимаем OAuth веб-сервер, запускаем фоновые задачи и polling.
    Корректно закрываемся на SIGINT/SIGTERM/KeyboardInterrupt.
    """
    oauth_runner = None
    tasks: list[asyncio.Task] = []

    # перехват сигналов (на Windows SIGTERM может быть недоступен — игнорируем)
    stop_event = asyncio.Event()

    def _stop():
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _stop)

    try:
        # 1) OAuth веб-сервер
        try:
            oauth_runner = await start_oauth_webserver(bot)
            logging.info("OAuth webserver started")
        except Exception:
            logging.exception("Failed to start OAuth webserver")

        # 2) фоновые задачи (по желанию)
        try:
            tasks.append(asyncio.create_task(subscription_expirer(bot), name="subscription-expirer"))
        except Exception:
            logging.exception("Failed to start subscription_expirer task")

        # 3) polling (блокирующе, до Ctrl+C/сигнала)
        await dp.start_polling(bot, skip_updates=True)

    except (asyncio.CancelledError, KeyboardInterrupt):
        # обычное завершение
        pass
    finally:
        # 1) останавливаем фоновые задачи
        for t in tasks:
            t.cancel()
        for t in tasks:
            with suppress(asyncio.CancelledError):
                await t

        # 2) закрываем OAuth сервер
        if oauth_runner is not None:
            with suppress(Exception):
                await oauth_runner.cleanup()

        # 3) корректно закрываем ресурсы aiogram
        with suppress(Exception):
            await dp.storage.close()      # если используется FSM хранилище
        with suppress(Exception):
            await bot.session.close()

        logging.info("Shutdown complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())
