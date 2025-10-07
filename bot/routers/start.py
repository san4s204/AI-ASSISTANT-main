from __future__ import annotations
from aiogram import Router, types
from aiogram import F
from aiogram.filters import Command, CommandStart
from bot.services.db import get_subscription_until, has_accepted_terms, set_terms_accepted
from aiogram.fsm.context import FSMContext
import os

from keyboards import (
    keyboard_sub, keyboard_unsub, keyboard_return, keyboard_terms
)




router = Router(name="start")

# ссылки можно держать в .env (если нет — подставятся заглушки)
PRIVACY_URL = os.getenv("TERMS_PRIVACY_URL", "https://example.com/privacy")
PD_URL      = os.getenv("TERMS_PD_URL",      "https://example.com/pd")
OFFER_URL   = os.getenv("TERMS_OFFER_URL",   "https://example.com/offer")
DEMO_VIDEO_FILE_ID = os.getenv("DEMO_VIDEO_FILE_ID", "")  # file_id/URL — если будет


def info_text() -> str:
    return (
        "Подключите к своему Telegram боту 🤖 искусственный интеллект с помощью нашего сервиса CHESS IT !\n\n"
        "Настройте промпт 📝, подключите календарь 📅 либо другие дополнения — и готово.\n"
        "Бот будет отвечать на вопросы клиентов 👨‍💻, давать консультации и вести осмысленные диалоги.\n\n"
        "Как это работает:\n"
        "– Создайте бота в @BotFather\n"
        "– Подключите его в нашем сервисе\n"
        "– Выберите дополнения и настройте промпт. Запустите умного помощника!\n\n"
        "Больше не нужен разработчик — автоматизируйте общение с помощью искусственного интеллекта!\n\n"
        "📎 Инструкция для подключения бота к Telegram аккаунту (ссылка будет)\n"
        "📎 Инструкция для подключения и настройки промпта (ссылка будет)"
    )

def terms_text() -> str:
    return (
        "👋 Добро пожаловать в CHESS IT !\n\n"
        "Для использования бота необходимо принять:\n\n"
        f"• <a href=\"{PRIVACY_URL}\">Политику конфиденциальности</a>\n"
        f"• <a href=\"{PD_URL}\">Согласие на обработку персональных данных</a>\n"
        f"• <a href=\"{OFFER_URL}\">Договор оферты</a>\n\n"
        "Нажимая кнопку «Принимаю», вы подтверждаете, что ознакомились и согласны с условиями указанных документов."
    )

def welcome_text() -> str:
    return (
        "👋 Добро пожаловать в CHESS IT !\n\n"
        "🙏 Для Вас доступно 2 варианта подключения:\n\n"
        "1. Через Telegram-бота. Общение происходит внутри бота Telegram. Подходит под индивидуальных ИИ-помощников. "
        "Из минусов — временно нет истории сообщений.\n"
        "2. Через Telegram аккаунт (нужен TG Premium). Плюсы — контроль переписки и возможность отключать бота в конкретных диалогах. "
        "Подробнее — в инструкции (ссылка будет добавлена).\n\n"
        "🧱 Создайте своего бота через @BotFather\n"
        "🤖 Подключите своего бота через команду /settings\n"
        "📝 Подключите свой промпт через команду /prompt\n"
        "📅 При необходимости подключите Google Календарь\n"
        "🔔 Запустите своего бота в главном меню"
    )

async def _send_demo_video_if_any(message: types.Message) -> None:
    vid = DEMO_VIDEO_FILE_ID.strip()
    if not vid:
        return
    try:
        await message.answer_video(video=vid, caption="Короткая демонстрация работы")
    except Exception:
        # если это не валидный file_id/URL — просто молча пропустим
        pass

@router.message(CommandStart())
async def start_cmd(message: types.Message):
    uid = message.from_user.id
    # 1) если пользователь ещё не принял соглашение — показываем его и останавливаемся
    if not await has_accepted_terms(uid):
        await message.answer(
            text=terms_text(),
            reply_markup=keyboard_terms(),
            disable_web_page_preview=True,
            parse_mode="HTML",
        )
        return

    # 2) обычный сценарий (после принятия): показываем привет и меню
    res = await get_subscription_until(uid)
    await _send_demo_video_if_any(message)
    if res:
        await message.answer(
            text="Главное меню:",
            reply_markup=keyboard_sub(uid),
        )
    else:
        await message.answer(
            text=welcome_text(),
            disable_web_page_preview=True,
        )
        await message.answer(
            text="Главное меню:",
            reply_markup=keyboard_unsub(),
        )

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "Если у вас появятся вопросы, всегда обращайтесь к @chess_it_manager",
        reply_markup=keyboard_return()
    )

@router.message(Command("info"))
async def info_cmd(message: types.Message):
    await message.answer(
        info_text(),
        reply_markup=keyboard_return()
    )

@router.message(F.text == "📖 Информация")
async def info_reply(message: types.Message):
    await message.answer(
        info_text(),
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
        info_text(),
         reply_markup=keyboard_return()
    )

@router.callback_query(F.data == "help")
async def cq_help(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Если у вас появятся вопросы, всегда обращайтесь к @chess_it_manager",
        reply_markup=keyboard_return()
    )

@router.callback_query(F.data == "return")
async def cq_return(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    uid = callback.from_user.id

    # 🔑 если соглашение ещё не принято — возвращаем на экран соглашения
    if not await has_accepted_terms(uid):
        await callback.message.edit_text(
            terms_text(),
            reply_markup=keyboard_terms(),
            disable_web_page_preview=True,
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Раньше здесь ставили global attempts=500, теперь проверки платежей вынесены в сервис — это не нужно.
    res = await get_subscription_until(callback.from_user.id)
    if res:
        await callback.message.edit_text("Главное меню:", reply_markup=keyboard_sub(callback.from_user.id))
    else:
        await callback.message.edit_text("Главное меню:", reply_markup=keyboard_unsub())

@router.callback_query(F.data == "terms_decline")
async def cq_terms_decline(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "❌ Для использования бота необходимо принять пользовательское соглашение.\n\n"
        "Если вы передумаете, используйте команду /start для повторного просмотра соглашения.",
        reply_markup=keyboard_return(),
        parse_mode="HTML",
    )
    await callback.answer()

@router.callback_query(F.data == "terms_accept")
async def cq_terms_accept(callback: types.CallbackQuery):
    uid = callback.from_user.id
    first_time = not await has_accepted_terms(uid)
    await set_terms_accepted(uid)

    # показываем видео (если есть)
    if DEMO_VIDEO_FILE_ID:
        try:
            await callback.message.answer_video(video=DEMO_VIDEO_FILE_ID, caption="Короткая демонстрация работы")
        except Exception:
            pass

    # сообщение «Спасибо!» — только при первом подтверждении
    if first_time:
        await callback.message.answer("✅ Спасибо! Соглашение принято.")

    # дальше стандартный welcome + меню
    res = await get_subscription_until(uid)
    if res:
        await callback.message.answer(
            text="Главное меню:",
            reply_markup=keyboard_sub(uid),
        )
    else:
        await callback.message.answer(
            text=welcome_text(),
            disable_web_page_preview=True,
        )
        await callback.message.answer(
            text="Главное меню:",
            reply_markup=keyboard_unsub(),
        )
    await callback.answer()