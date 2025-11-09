# providers/google_docs_oauth_provider.py
from __future__ import annotations
from typing import Dict, Any
import asyncio
import re

from googleapiclient.discovery import build
from bot.services.google_oauth import load_user_credentials


def _extract_doc_id(identifier: str) -> str:
    """
    Принимает либо голый documentId, либо полный URL,
    возвращает чистый ID.
    """
    s = (identifier or "").strip()
    m = re.search(r"/document/d/([a-zA-Z0-9_-]+)", s)
    if m:
        return m.group(1)
    return s


def _read_structural_elements(elements: list[dict]) -> str:
    """
    Классическая функция разворачивания структуры Google Docs в обычный текст.
    """
    parts: list[str] = []

    for value in elements:
        # Обычные абзацы
        para = value.get("paragraph")
        if para:
            for elem in para.get("elements", []):
                tr = elem.get("textRun")
                if tr:
                    text = tr.get("content", "")
                    if text:
                        parts.append(text)
            continue

        # Таблицы
        table = value.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    parts.append(_read_structural_elements(cell.get("content", [])))
            continue

        # Оглавление
        toc = value.get("tableOfContents")
        if toc:
            parts.append(_read_structural_elements(toc.get("content", [])))
            continue

    return "".join(parts)


async def get_document_oauth(user_id: int, identifier: str) -> Dict[str, Any]:
    """
    Читает Google Doc от имени конкретного пользователя (OAuth).
    Возвращает dict: {"id": ..., "title": ..., "content": ...}
    """
    doc_id = _extract_doc_id(identifier)

    creds = await load_user_credentials(user_id)
    if creds is None:
        raise RuntimeError("No Google OAuth credentials for this user")

    def _fetch() -> Dict[str, Any]:
        service = build(
            "docs",
            "v1",
            credentials=creds,
            cache_discovery=False,
        )
        document = service.documents().get(documentId=doc_id).execute()
        title = document.get("title", "")
        body = document.get("body", {}).get("content", [])
        content = _read_structural_elements(body)
        return {
            "id": doc_id,
            "title": title,
            "content": content,
        }

    # Google API блокирующий → уносим в отдельный поток
    return await asyncio.to_thread(_fetch)
