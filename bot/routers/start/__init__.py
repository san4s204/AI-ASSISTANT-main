from __future__ import annotations
from aiogram import Router
from . import base, info_help, terms

router = Router(name="start")
router.include_router(base.router)
router.include_router(info_help.router)
router.include_router(terms.router)