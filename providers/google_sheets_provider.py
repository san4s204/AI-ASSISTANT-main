from __future__ import annotations
from typing import Dict, Any, List, Optional
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import SERVICE_ACCOUNT_FILE

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

_SHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
# Необязательная поддержка !A1:Z999 в ссылке
_RANGE_IN_URL_RE = re.compile(r"[#?&]range=([^&]+)", re.IGNORECASE)

def _normalize_spreadsheet_id_and_range(url_or_id: str) -> tuple[str, Optional[str]]:
    s = (url_or_id or "").strip()
    m = _SHEET_ID_RE.search(s)
    sheet_id = m.group(1) if m else s

    # Пытаемся извлечь range из ссылок вида ...?range=Лист1!A1:Z999
    rm = _RANGE_IN_URL_RE.search(s)
    rng = rm.group(1) if rm else None
    return sheet_id, rng

def _build_sheets_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('sheets', 'v4', credentials=creds)

def _values_to_markdown(values: List[List[Any]], max_rows: int = 50, max_chars: int = 4000) -> str:
    """Грубая конвертация в markdown-таблицу: заголовок + до max_rows."""
    if not values:
        return "Пустая таблица."
    head = [str(x) for x in values[0]]
    rows = [[str(x) for x in r] for r in values[1:max_rows+1]]

    def row_line(cells: List[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    lines = [
        row_line(head),
        row_line(["---"] * len(head)),
    ]
    for r in rows:
        lines.append(row_line(r))

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n… (обрезано)"
    return text

def get_sheet_as_text(spreadsheet_id_or_url: str, value_range: Optional[str] = None) -> Dict[str, Any]:
    """
    Возвращает {'id','title','content','range'}.
    content — markdown (короткий превью каталога).
    """
    service = _build_sheets_service()
    sheet_id, rng_in_url = _normalize_spreadsheet_id_and_range(spreadsheet_id_or_url)
    rng = value_range or rng_in_url or "A1:Z200"

    # Заголовок файла
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    title = meta.get("properties", {}).get("title", "")

    # Значения
    resp = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=rng
    ).execute()
    values = resp.get("values", [])

    content = _values_to_markdown(values)
    return {"id": sheet_id, "title": title, "content": content, "range": rng}
