from __future__ import annotations
from aiogram import Router, types, F
from aiogram.filters import Command
from keyboards import keyboard_return, keyboard_terms
from .helpers import info_text, terms_text

router = Router(name="start.info_help")

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer("Если у вас появятся вопросы, всегда обращайтесь к @chess_it_manager", reply_markup=keyboard_return())

@router.message(Command("info"))
async def info_cmd(message: types.Message):
    await message.answer(info_text(), reply_markup=keyboard_return())

@router.message(F.text == "📖 Информация")
async def info_reply(message: types.Message):
    await message.answer(info_text(), reply_markup=keyboard_return())

@router.message(F.text == "💬 Помощь")
async def help_reply(message: types.Message):
    await message.answer("Если у вас появятся вопросы, всегда обращайтесь к @chess_it_manager", reply_markup=keyboard_return())

@router.callback_query(F.data == "info")
async def cq_info(callback: types.CallbackQuery):
    await callback.message.edit_text(info_text(), reply_markup=keyboard_return())

@router.callback_query(F.data == "help")
async def cq_help(callback: types.CallbackQuery):
    await callback.message.edit_text("Если у вас появятся вопросы, всегда обращайтесь к @chess_it_manager", reply_markup=keyboard_return())

# 2) Отдельная команда для юр-доков: /terms
@router.message(Command("terms"))
async def terms_handler(message: types.Message):
    await message.answer(
        terms_text(),
        disable_web_page_preview=False,
        reply_markup=keyboard_terms(),
    )