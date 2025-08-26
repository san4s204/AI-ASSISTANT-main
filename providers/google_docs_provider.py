from __future__ import annotations
from typing import Dict, Any, List
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import SERVICE_ACCOUNT_FILE

SCOPES = ['https://www.googleapis.com/auth/documents.readonly']

_DOC_ID_RE = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")

def _normalize_document_id(document_id_or_url: str) -> str:
    """
    Принимает ID или полную ссылку на Google Doc и возвращает чистый ID.
    Примеры:
      - '1abcDEF...' -> '1abcDEF...'
      - 'https://docs.google.com/document/d/1abcDEF.../edit?tab=t.0' -> '1abcDEF...'
    """
    s = (document_id_or_url or "").strip()
    m = _DOC_ID_RE.search(s)
    return m.group(1) if m else s

def _build_docs_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    # Если в окружении бывают проблемы с discovery-кэшем, можно добавить cache_discovery=False
    return build('docs', 'v1', credentials=creds)

def _extract_text(elements: List[Dict[str, Any]]) -> str:
    # Минимальный плоский парсер текста из структуры Google Docs
    chunks: List[str] = []
    for el in elements or []:
        if 'paragraph' in el:
            for pe in el['paragraph'].get('elements', []):
                text_run = pe.get('textRun', {})
                content = text_run.get('content')
                if content:
                    chunks.append(content)
        elif 'table' in el:
            table = el['table']
            for row in table.get('tableRows', []):
                for cell in row.get('tableCells', []):
                    chunks.append(_extract_text(cell.get('content', [])))
        elif 'tableOfContents' in el:
            toc = el['tableOfContents']
            chunks.append(_extract_text(toc.get('content', [])))
        # sectionBreak и прочее игнорируем
    return ''.join(chunks)

def get_document(document_id_or_url: str) -> Dict[str, Any]:
    """Забирает Google Doc и возвращает {'id', 'title', 'content'} (plain text)."""
    service = _build_docs_service()
    doc_id = _normalize_document_id(document_id_or_url)
    doc = service.documents().get(documentId=doc_id).execute()
    body = doc.get('body', {})
    content = _extract_text(body.get('content', []))
    return {'id': doc_id, 'title': doc.get('title', ''), 'content': content}
