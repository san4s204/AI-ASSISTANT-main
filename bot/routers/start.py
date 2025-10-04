from __future__ import annotations
from aiogram import Router, types
from aiogram import F
from aiogram.filters import Command, CommandStart
from bot.services.db import get_subscription_until

from keyboards import (
    r_keyboard_sub, r_keyboard_unsub,
    keyboard_sub, keyboard_unsub, keyboard_return,
)


router = Router(name="start")

@router.message(CommandStart())
async def start_cmd(message: types.Message):
    res = await get_subscription_until(message.from_user.id)
    if res:
        await message.answer(
            f"Вы уже оплатили подписку! Она активна до {res}",
            reply_markup=r_keyboard_sub(message.from_user.id)
        )
        await message.answer("Главное меню:", reply_markup=keyboard_sub(message.from_user.id))
    else:
        await message.answer(
            "Привет, давай коротко расскажу о себе: \n ",
            "Через данный бот Вы можете за 5 минут подключить ИИ к своему Telegram-боту.\n",
            "Без программирования. Получите умного ассистента для поддержки клиентов, консультаций или развлечения.",
            reply_markup=r_keyboard_unsub()
        )
        await message.answer("Главное меню", reply_markup=keyboard_unsub())

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "Если у вас появятся вопросы, всегда обращайтесь к @chess_it_manager",
        reply_markup=keyboard_return()
    )

@router.message(Command("info"))
async def info_cmd(message: types.Message):
    await message.answer(
        "Подключите к своему боту искусственный интеллект с помощью нашего сервиса CHESS IT\n\nНастройте промпт, подключите календарь либо другие дополнения — и готово\nБот будет отвечать на вопросы клиентов, давать консультации и вести осмысленные диалоги. Как это работает:\n–Создайте бота в @BotFather\n–Подключите его в нашем сервисе\n–Выберите дополнения и настройте промпт. Запустите умного помощника!\n\nБольше не нужен разработчик — автоматизируйте общение с помощью искусственного интеллекта!",
        reply_markup=keyboard_return()
    )

@router.message(F.text == "📖 Информация")
async def info_reply(message: types.Message):
    await message.answer(
        "Подключите к своему боту искусственный интеллект с помощью нашего сервиса CHESS IT\n\nНастройте промпт, подключите календарь либо другие дополнения — и готово\nБот будет отвечать на вопросы клиентов, давать консультации и вести осмысленные диалоги. Как это работает:\n–Создайте бота в @BotFather\n–Подключите его в нашем сервисе\n–Выберите дополнения и настройте промпт. Запустите умного помощника!\n\nБольше не нужен разработчик — автоматизируйте общение с помощью искусственного интеллекта!",
        reply_markup=keyboard_return()
    )

@router.message(F.text == "💬 Помощь")
async def help_reply(message: types.Message):
    await message.answer(
        "Если у вас появятся вопросы, всегда обращайтесь к @chess_it_manager",
        reply_markup=keyboard_return()
    )

@router.message(F.text.lower().in_(["🧭 главное меню", "главное меню"]))
async def open_main_menu(message: types.Message):
    await message.answer("Главное меню:", reply_markup=keyboard_sub(message.from_user.id))

## Callbacks

@router.callback_query(F.data == "info")
async def cq_info(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Подключите к своему боту искусственный интеллект с помощью нашего сервиса CHESS IT\n\nНастройте промпт, подключите календарь либо другие дополнения — и готово\nБот будет отвечать на вопросы клиентов, давать консультации и вести осмысленные диалоги. Как это работает:\n–Создайте бота в @BotFather\n–Подключите его в нашем сервисе\n–Выберите дополнения и настройте промпт. Запустите умного помощника!\n\nБольше не нужен разработчик — автоматизируйте общение с помощью искусственного интеллекта!",
         reply_markup=keyboard_return()
    )

@router.callback_query(F.data == "help")
async def cq_help(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Если у вас появятся вопросы, всегда обращайтесь к @chess_it_manager",
        reply_markup=keyboard_return()
    )

@router.callback_query(F.data == "return")
async def cq_return(callback: types.CallbackQuery):
    # Раньше здесь ставили global attempts=500, теперь проверки платежей вынесены в сервис — это не нужно.
    res = await get_subscription_until(callback.from_user.id)
    if res:
        await callback.message.edit_text("Главное меню", reply_markup=keyboard_sub(callback.from_user.id))
    else:
        await callback.message.edit_text("Главное меню", reply_markup=keyboard_unsub())