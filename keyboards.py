from __future__ import annotations
import sqlite3
from aiogram.types import KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from config import MANAGER_URL, CRYPTO_ENABLED
from config import DB_PATH

# ---------------- Reply keyboards ----------------
CB_CANCEL = "pay_cancel"

def r_keyboard_unsub():
    builder = ReplyKeyboardBuilder()
    builder.add(
        KeyboardButton(text="💰 Оплата"),
        KeyboardButton(text="📖 Информация"),
        KeyboardButton(text="💬 Помощь"),
    )
    builder.adjust(1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def r_keyboard_sub(user_id: int = None):
    builder = ReplyKeyboardBuilder()
    builder.add(
        KeyboardButton(text="🧭 Главное меню"),   # ← было: "🔔 Подключить личный кабинет"
        KeyboardButton(text="🔧 Настройки Бота"),
        KeyboardButton(text="📝 Просмотр и редактирование промпта"),
        KeyboardButton(text="⏳ Подписка"),
        KeyboardButton(text="📖 Информация"),
        KeyboardButton(text="💬 Помощь"),
    )
    builder.adjust(1, 1, 2, 2)
    return builder.as_markup(resize_keyboard=True)


# ---------------- Inline keyboards ----------------

def keyboard_sub(user_id: int):
    """
    Главное меню для подписчиков.
    Первая кнопка показывает текущее состояние бота по пользователю.
    """
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text=state_bot(user_id), callback_data="turn_on_off"),
        InlineKeyboardButton(text="🔧 Настройка Бота ", callback_data="setting_bot"),
        InlineKeyboardButton(text="📝 Просмотр и редактирование промпта", callback_data="prompt"),
        InlineKeyboardButton(text="⏳ Подписка", callback_data="check_sub"),
        InlineKeyboardButton(text="📖 Информация", callback_data="info"),
        InlineKeyboardButton(text="💬 Помощь", callback_data="help"),
    )
    # Итого 6 кнопок → сделаем 4 ряда: 1, 1, 2, 2
    builder.adjust(1, 1, 2, 2)
    return builder.as_markup()


def keyboard_unsub():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="💰 Оплата", callback_data="payment"),
        InlineKeyboardButton(text="📖 Информация", callback_data="info"),
        InlineKeyboardButton(text="💬 Помощь", callback_data="help"),
    )
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def keyboard_return():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="↩️ Назад", callback_data="return"))
    return builder.as_markup()


def keyboard_payment_bot():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="💳 ЮКасса", callback_data="yookassa_bot"),
    )
    if CRYPTO_ENABLED:
        builder.add(InlineKeyboardButton(text="💸 Crypto Bot", callback_data="cryptobot_bot"))
    builder.add(InlineKeyboardButton(text="↩️ Назад", callback_data="payment"))
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def keyboard_payment_premium():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="💳 ЮКасса", callback_data="yookassa_premium"),
    )
    if CRYPTO_ENABLED:
        builder.add(InlineKeyboardButton(text="💸 Crypto Bot", callback_data="cryptobot_premium"))
    builder.add(InlineKeyboardButton(text="↩️ Назад", callback_data="payment"))
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def keyboard_crypto_bot(url: str):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="💸 Оплатить", url=url),
        InlineKeyboardButton(text="❔ Проблема с оплатой?", url=MANAGER_URL),
        InlineKeyboardButton(text="✖️ Отменить оплату", callback_data=CB_CANCEL),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def keyboard_yookassa(url: str):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="💳 Оплатить", url=url),
        InlineKeyboardButton(text="❔ Проблема с оплатой?", url=MANAGER_URL),
        InlineKeyboardButton(text="✖️ Отменить оплату", callback_data=CB_CANCEL),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def keyboard_subscribe():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="➡️ Перейти к функционалу", callback_data="subscribe"))
    return builder.as_markup()


def keyboard_again():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔄 Повторить оплату", callback_data="payment"))
    return builder.as_markup()


def keyboard_change_ai():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🤖ИИ-Бот", callback_data="ai_premium"),
        InlineKeyboardButton(text="↩️ Назад", callback_data="return"),
    )
    builder.adjust(1, 1)
    return builder.as_markup()


def keyboard_setting_bot():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🤖Изменить API Ключ", callback_data="change_API"),
        InlineKeyboardButton(text='📄 Привязать Google Документ', callback_data='change_DOC'),
        InlineKeyboardButton(text='📊 Привязать Google Таблицу', callback_data='change_SHEET'),
        InlineKeyboardButton(text="🗓 Календарь", callback_data="calendar_menu"),
        InlineKeyboardButton(text='🔗 Подключить Google', callback_data='connect_google'),
        InlineKeyboardButton(text='🚪 Отключить Google', callback_data='disconnect_google'),
        InlineKeyboardButton(text="↩️ Назад", callback_data="return"),
    )
    builder.adjust(1, 1, 1, 1, 1, 1, 1)
    return builder.as_markup()


# ---------------- Helpers ----------------

def state_bot(user_id: int) -> str:
    """
    Синхронная проверка состояния бота пользователя.
    Оставляем синхронной, чтобы не менять сигнатуры остальных функций.
    В случае ошибки — безопасно возвращаем «выключен».
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT state_bot FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        conn.close()
        state = (row[0] if row else None) or "stop"
        return "🤖✅ Бот включен" if state == "active" else "🤖❌ Бот выключен"
    except Exception:
        # лог можно добавить на вкус
        return "🤖❌ Бот выключен"

def keyboard_calendar_menu(is_linked: bool):
    kb = InlineKeyboardBuilder()
    if is_linked:
        kb.add(InlineKeyboardButton(text="🚪 Отвязать календарь", callback_data="cal_unlink"))
    else:
        kb.add(InlineKeyboardButton(text="📎 Привязать календарь", callback_data="change_CAL"))
    kb.add(InlineKeyboardButton(text="↩️ Назад", callback_data="setting_bot"))
    kb.adjust(1, 1)
    return kb.as_markup()

def keyboard_prompt_controls(url: str):
    """
    Кнопки под превью источника: открыть/удалить/назад.
    """
    b = InlineKeyboardBuilder()
    if url:
        b.add(InlineKeyboardButton(text="🔗 Открыть", url=url))
    b.add(InlineKeyboardButton(text="🗑️ Удалить источник", callback_data="delete_source"))
    b.add(InlineKeyboardButton(text="↩️ Назад", callback_data="return"))
    b.adjust(1, 1, 1)
    return b.as_markup()

def keyboard_attach_source():
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="📄 Привязать Google Документ", callback_data="change_DOC"))
    kb.add(InlineKeyboardButton(text="📊 Привязать Google Таблицу",  callback_data="change_SHEET"))
    kb.add(InlineKeyboardButton(text="↩️ Назад",                    callback_data="return"))
    kb.adjust(1, 1, 1)
    return kb.as_markup()

def keyboard_confirm_delete_source():
    """
    Подтверждение удаления источника.
    """
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_delete_source"))
    b.add(InlineKeyboardButton(text="↩️ Отмена", callback_data="prompt"))
    b.adjust(1, 1)
    return b.as_markup()

def keyboard_terms():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Принимаю ✅", callback_data="terms_accept"),
        InlineKeyboardButton(text="Не принимаю ❌", callback_data="terms_decline"),
    ]])
