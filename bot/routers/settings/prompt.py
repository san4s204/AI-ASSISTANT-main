from __future__ import annotations
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from bot.states import Form
from keyboards import keyboard_return
from bot.services.db import update_user_document
from .helpers import render_prompt_preview

router = Router(name="settings.prompt")

@router.callback_query(F.data == "prompt")
async def prompt_cb(callback: types.CallbackQuery):
    await render_prompt_preview(callback, callback.from_user.id)

@router.message(Command("prompt"))
async def prompt_cmd(message: types.Message):
    await render_prompt_preview(message, message.from_user.id)

@router.callback_query(F.data == "change_DOC")
async def change_doc(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Пришлите ссылку или ID Google **Документа** (Docs).", reply_markup=keyboard_return())
    await state.set_state(Form.waiting_for_doc)

@router.message(Form.waiting_for_doc)
async def process_doc_link(message: types.Message, state: FSMContext):
    value = (message.text or "").strip()
    ok = await update_user_document(message.from_user.id, value)
    await message.answer("✅ Документ привязан." if ok else "❌ Не удалось сохранить документ.", reply_markup=keyboard_return())
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
    await message.answer("✅ Таблица привязана." if ok else "❌ Не удалось сохранить таблицу.", reply_markup=keyboard_return())
    await state.clear()
