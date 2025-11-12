from __future__ import annotations
from aiogram import Router, types, F
from bot.services.db import has_accepted_terms, set_terms_accepted, get_subscription_until
from keyboards import keyboard_return, keyboard_sub, keyboard_unsub
from .helpers import  welcome_text, DEMO_VIDEO_FILE_ID

router = Router(name="start.terms")

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

    # Видео (если настроено)
    if DEMO_VIDEO_FILE_ID:
        try:
            await callback.message.answer_video(video=DEMO_VIDEO_FILE_ID, caption="Короткая демонстрация работы")
        except Exception:
            pass

    if first_time:
        await callback.message.answer("✅ Спасибо! Соглашение принято.")

    res = await get_subscription_until(uid)
    if res:
        await callback.message.answer(text="Главное меню:", reply_markup=keyboard_sub(uid))
    else:
        await callback.message.answer(text=welcome_text(), disable_web_page_preview=True)
        await callback.message.answer(text="Главное меню:", reply_markup=keyboard_unsub())
    await callback.answer()
