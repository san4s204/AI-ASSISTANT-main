# deepseek.py
from __future__ import annotations
from typing import Dict, Any
import asyncio
import os
import logging

from providers.google_docs_oauth_provider import get_document_oauth
from providers.google_sheets_oauth_provider import get_sheet_as_text_oauth
from googleapiclient.errors import HttpError
from providers.google_docs_provider import get_document as get_document_sa
from providers.google_sheets_provider import get_sheet_as_text as get_sheet_sa

FORCE_GOOGLE_OAUTH = os.getenv("FORCE_GOOGLE_OAUTH") == "1"


async def _read_via_oauth(owner_user_id: int, identifier: str) -> Dict[str, Any]:
    s = (identifier or "").strip()
    if not s:
        raise FileNotFoundError("Empty document identifier")

    is_sheet = "/spreadsheets/d/" in s or s.endswith("sheet")
    is_doc = "/document/d/" in s

    if is_sheet:
        try:
            res = await get_sheet_as_text_oauth(owner_user_id, s)
        except HttpError:
            raise FileNotFoundError("Sheets: not found or no access") from None
        res["kind"] = "sheet"
        return res

    if is_doc:
        try:
            res = await get_document_oauth(owner_user_id, s)
        except HttpError:
            raise FileNotFoundError("Docs: not found or no access") from None
        res["kind"] = "doc"
        return res

    # неизвестно — сначала Doc, затем Sheet
    try:
        res = await get_document_oauth(owner_user_id, s)
        res["kind"] = "doc"
        return res
    except HttpError:
        try:
            res = await get_sheet_as_text_oauth(owner_user_id, s)
            res["kind"] = "sheet"
            return res
        except HttpError:
            raise FileNotFoundError("Document not found or no access") from None


async def _read_via_service_account(identifier: str) -> Dict[str, Any]:
    """Фолбэк на сервис-аккаунт (если разрешено)."""
    s = (identifier or "").strip()
    is_sheet = "/spreadsheets/d/" in s
    is_doc = "/document/d/" in s

    if is_sheet:
        res = await asyncio.to_thread(get_sheet_sa, s)
        res["kind"] = "sheet"
        return res
    if is_doc:
        res = await asyncio.to_thread(get_document_sa, s)
        res["kind"] = "doc"
        return res

    try:
        res = await asyncio.to_thread(get_document_sa, s)
        res["kind"] = "doc"
        return res
    except Exception:
        res = await asyncio.to_thread(get_sheet_sa, s)
        res["kind"] = "sheet"
        return res


async def doc(identifier: str, owner_user_id: int | None = None) -> Dict[str, Any]:
    """
    Читает Google Doc/Sheet.
    1) Если есть owner_user_id — пробуем OAuth.
       - При FORCE_GOOGLE_OAUTH=1 не делаем фолбэк и отдаём реальную ошибку (чтобы не было 403 от SA).
       - Иначе логируем и пробуем сервис-аккаунт.
    2) Если owner_user_id нет — идём сразу в сервис-аккаунт.
    """
    if owner_user_id is not None:
        try:
            return await _read_via_oauth(owner_user_id, identifier)
        except Exception as e:
            if FORCE_GOOGLE_OAUTH:
                # важно видеть настоящую причину (нет токена/нет прав/не те scopes и т.д.)
                raise
            logging.warning("OAuth read failed, falling back to service account: %s", e)

    # сюда попадём если OAuth не задан или не обязателен
    return await _read_via_service_account(identifier)
