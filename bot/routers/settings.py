from __future__ import annotations
from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from aiogram import F
import asyncio
from bot.states import Form
from keyboards import keyboard_setting_bot, keyboard_sub, state_bot, keyboard_return, keyboard_prompt_controls, keyboard_confirm_delete_source, keyboard_attach_source, keyboard_calendar_menu
from bot.services.db import update_user_state, get_user_token_and_doc, get_user_doc_id, update_user_token, update_user_document, set_user_calendar_id, get_user_calendar_id, clear_user_calendar_id
from openrouter import run_bot, stop_bot
from providers.redis_provider import delete_by_pattern
from deepseek import doc
from providers.google_calendar_oauth_provider import list_calendars_oauth
import re
from config import BASE_URL
from bot.services.google_oauth import delete_refresh_token
from aiogram.types import  InlineKeyboardButton
from aiogram.utils.keyboard import  InlineKeyboardBuilder

_DOC_RE = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")
_SHEET_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")


router = Router(name="settings")

@router.callback_query(F.data == "setting_bot")
async def setting_bot_cb(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Настройка бота:",
        reply_markup=keyboard_setting_bot()
    )

@router.callback_query(F.data == "turn_on_off")
async def turn_cb(callback: types.CallbackQuery):
    # Что сейчас показывает кнопка в меню (текущее состояние)
    res = state_bot(callback.from_user.id)

    if res == "🤖❌ Бот выключен":
        await callback.answer(text="Запускаю Вашего бота ✅")
        # не блокируем event loop
        await asyncio.sleep(1)
        await update_user_state(callback.from_user.id, "active")
        await callback.message.edit_reply_markup(reply_markup=keyboard_sub(callback.from_user.id))
        token, word_file = await get_user_token_and_doc(callback.from_user.id)
        await run_bot(token, word_file, callback.from_user.id)

    elif res == "🤖✅ Бот включен":
        await callback.answer(text="Останавливаю Вашего бота ❌")
        await update_user_state(callback.from_user.id, "stop")
        await callback.message.edit_reply_markup(reply_markup=keyboard_sub(callback.from_user.id))
        token, _ = await get_user_token_and_doc(callback.from_user.id)
        await stop_bot(str(token))

@router.callback_query(F.data == "check_txt")
async def check_txt(callback: types.CallbackQuery):
    link = await get_user_doc_id(callback.from_user.id)
    if not link:
        await callback.message.edit_text(
            "Источник не привязан. Добавьте Документ или Таблицу:",
            reply_markup=keyboard_attach_source()
        )
        return

    try:
        ans = await doc(link, owner_user_id=callback.from_user.id)
        kind = ans.get("kind")
        if kind == "sheet":
            url = f"https://docs.google.com/spreadsheets/d/{ans['id']}/edit"
            src_name = "Google Sheets"
        else:
            url = f"https://docs.google.com/document/d/{ans['id']}/edit"
            src_name = "Google Docs"

        await callback.message.edit_text(
            f"Источник: {src_name}\n"
            f"Название: {ans.get('title','')}\n"
            f"Содержимое (превью):\n{ans.get('content','')}",
            reply_markup=keyboard_prompt_controls(url)
        )
    except Exception:
        await callback.answer(
            "Не удалось открыть источник. Проверьте доступ (OAuth/шаринг) и корректность ссылки.",
            show_alert=True
        )

@router.message(Form.waiting_for_api)
async def process_api(message: types.Message, state: FSMContext):
    user_api = message.text.strip()
    ok = await update_user_token(message.from_user.id, user_api)
    if ok:
        await message.answer("✅ Токен успешно обновлён!", reply_markup=keyboard_return())
    else:
        await message.answer("❌ Запись не найдена или нет подписки", reply_markup=keyboard_return())
    await state.clear()

@router.callback_query(F.data == "change_DOC")
async def change_doc(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Пришлите ссылку или ID Google **Документа** (Docs).",
        reply_markup=keyboard_return()
    )
    await state.set_state(Form.waiting_for_doc)

@router.message(Form.waiting_for_doc)
async def process_doc_link(message: types.Message, state: FSMContext):
    value = (message.text or "").strip()
    ok = await update_user_document(message.from_user.id, value)
    if ok:
        await message.answer("✅ Документ привязан.", reply_markup=keyboard_return())
    else:
        await message.answer("❌ Не удалось сохранить документ.", reply_markup=keyboard_return())
    await state.clear()

@router.callback_query(F.data == "change_SHEET")
async def change_sheet(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Пришлите ссылку или ID Google **Таблицы** (Sheets).\n"
        "Можно указать диапазон через параметр `?range=Лист1!A1:Z200`.",
        reply_markup=keyboard_return()
    )
    await state.set_state(Form.waiting_for_sheet)

@router.message(Form.waiting_for_sheet)
async def process_sheet_link(message: types.Message, state: FSMContext):
    value = (message.text or "").strip()
    ok = await update_user_document(message.from_user.id, value)
    if ok:
        await message.answer("✅ Таблица привязана.", reply_markup=keyboard_return())
    else:
        await message.answer("❌ Не удалось сохранить таблицу.", reply_markup=keyboard_return())
    await state.clear()

@router.callback_query(F.data == "delete_source")
async def delete_source(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Удалить текущий источник (Документ/Таблица)? Это действие нельзя отменить.",
        reply_markup=keyboard_confirm_delete_source()
    )

@router.callback_query(F.data == "confirm_delete_source")
async def confirm_delete_source(callback: types.CallbackQuery):
    # достаём текущую ссылку
    link = await get_user_doc_id(callback.from_user.id)

    # попытка зачистить кэш ответов по этому источнику
    if link:
        m_doc = _DOC_RE.search(link)
        m_sheet = _SHEET_RE.search(link)
        src_id = m_doc.group(1) if m_doc else (m_sheet.group(1) if m_sheet else None)
        if src_id:
            try:
                # наши ключи: openrouter:{doc_id}:{system_hash}:{md5(text)}
                await delete_by_pattern(f"openrouter:{src_id}:*")
            except Exception:
                pass

    # отвязываем источник у пользователя
    await update_user_document(callback.from_user.id, None)

    await callback.message.edit_text(
        "Источник отвязан. Вы можете привязать новый в «Настройка бота».",
        reply_markup=keyboard_setting_bot()
    )

@router.callback_query(F.data == "connect_google")
async def connect_google(callback: types.CallbackQuery):
    # даём ссылку стартера
    url = f"{BASE_URL}/oauth/google/start?uid={callback.from_user.id}"
    await callback.message.edit_text(
        "Откройте ссылку и дайте доступ (Docs/Sheets Read-only).\n"
        "После подтверждения вернитесь в Telegram.",
        reply_markup=InlineKeyboardBuilder()
            .add(InlineKeyboardButton(text="🔗 Подключить Google", url=url))
            .add(InlineKeyboardButton(text="↩️ Назад", callback_data="return"))
            .adjust(1,1)
            .as_markup()
    )

@router.callback_query(F.data == "disconnect_google")
async def disconnect_google(callback: types.CallbackQuery):
    await delete_refresh_token(callback.from_user.id)
    await callback.answer("Google отключён.", show_alert=False)
    await callback.message.edit_reply_markup(reply_markup=keyboard_setting_bot())

@router.callback_query(F.data == "calendar_menu")
async def calendar_menu(callback: types.CallbackQuery):
    is_linked = bool(await get_user_calendar_id(callback.from_user.id))
    await callback.message.edit_text(
        "Настройки календаря:",
        reply_markup=keyboard_calendar_menu(is_linked)
    )



@router.callback_query(F.data == "change_CAL")
async def change_calendar(callback: types.CallbackQuery, state: FSMContext):
    try:
        calendars = await list_calendars_oauth(callback.from_user.id)
    except Exception:
        await callback.answer(
            "Не могу получить список календарей.\n"
            "Проверь подключение Google (OAuth) и что включён Calendar API.",
            show_alert=True,
        )
        return

    if not calendars:
        await callback.answer("Календари не найдены.", show_alert=True)
        return

    # Обрежем до 20 и сохраним в FSM (id будут храниться здесь)
    calendars = calendars[:20]
    await state.update_data(cal_list=calendars)
    await state.set_state(Form.waiting_for_calendar_pick)

    kb = InlineKeyboardBuilder()
    for i, it in enumerate(calendars):
        title = it.get("summary") or "(без названия)"
        if it.get("primary"):
            title = f"⭐ {title}"
        # В callback_data кладём только маленький индекс
        kb.add(types.InlineKeyboardButton(text=title[:32], callback_data=f"pick_cal:{i}"))
    kb.add(types.InlineKeyboardButton(text="↩️ Назад", callback_data="return"))
    kb.adjust(1, 1, 1, 1)

    await callback.message.edit_text("Выбери календарь:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("pick_cal:"), Form.waiting_for_calendar_pick)
async def pick_calendar(callback: types.CallbackQuery, state: FSMContext):
    # Достаём индекс из callback_data
    try:
        idx = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer("Неверный выбор.", show_alert=True)
        return

    data = await state.get_data()
    cal_list = data.get("cal_list") or []
    if idx < 0 or idx >= len(cal_list):
        await callback.answer("Элемент не найден.", show_alert=True)
        return

    cal_id = cal_list[idx]["id"]
    try:
        await set_user_calendar_id(callback.from_user.id, cal_id)
    finally:
        await state.clear()

    await callback.answer("✅ Календарь привязан.", show_alert=False)
    await callback.message.edit_text("Настройка бота:", reply_markup=keyboard_setting_bot())

@router.callback_query(F.data == "cal_unlink")
async def cal_unlink(callback: types.CallbackQuery):
    ok = await clear_user_calendar_id(callback.from_user.id)
    if ok:
        await callback.answer("✅ Календарь отвязан.", show_alert=False)
        # Перерисуем текущий экран без кнопки «Отвязать календарь»
        await check_txt(callback)
    else:
        await callback.answer("Нечего отвязывать — календарь не привязан.", show_alert=True)