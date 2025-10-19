from __future__ import annotations
from aiogram import Router

from . import base, power, prompt, token, source, google_oauth, calendar

router = Router(name="settings")
router.include_router(base.router)
router.include_router(power.router)
router.include_router(prompt.router)
router.include_router(token.router)
router.include_router(source.router)
router.include_router(google_oauth.router)
router.include_router(calendar.router)
