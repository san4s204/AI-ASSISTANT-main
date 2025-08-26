# providers/google_docs_oauth_provider.py
from __future__ import annotations
from typing import Dict, Any
from googleapiclient.discovery import build
from bot.services.google_oauth import load_user_credentials
import asyncio

async def get_document_oauth(user_id: int, document_id_or_url: str) -> Dict[str, Any]:
    creds = await load_user_credentials(user_id)
    if not creds:
        raise RuntimeError("Google OAuth не подключён для пользователя")
    def _run():
        service = build("docs", "v1", credentials=creds)
        doc_id = document_id_or_url
        if "/document/d/" in doc_id:
            doc_id = doc_id.split("/document/d/")[1].split("/")[0]
        doc = service.documents().get(documentId=doc_id).execute()
        # можно переиспользовать твой _extract_text
        return {"id": doc_id, "title": doc.get("title", "")}
    return await asyncio.to_thread(_run)
