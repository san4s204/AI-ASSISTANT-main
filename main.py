import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram import Router
from aiosend import CryptoPay, TESTNET

from config import TOKEN, CRYPTOTOKEN
from bot.web.oauth_app import start_oauth_webserver

# Если реально используешь этот cp в коде — оставь; если нет, можно убрать
cp = CryptoPay(CRYPTOTOKEN, TESTNET)

bot = Bot(TOKEN)
dp = Dispatcher()
router = Router(name="core")  # если в нём нет хендлеров — можно удалить

# Роутеры
from bot.routers.start import router as start_router
from bot.routers.subscription import router as subscription_router
from bot.routers.payments import router as payments_router
from bot.routers.settings import router as settings_router

# Регистрируем роутеры ДО старта polling
dp.include_router(start_router)
dp.include_router(subscription_router)
dp.include_router(payments_router)
dp.include_router(settings_router)
dp.include_router(router)  # если нужен

async def _run():
    # 1) поднимаем OAuth веб-сервер
    try:
        await start_oauth_webserver(bot)
    except Exception as e:
        logging.exception("Failed to start OAuth webserver: %s", e)
        # по желанию: не падать, а продолжить только с polling

    # 2) запускаем polling
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())
