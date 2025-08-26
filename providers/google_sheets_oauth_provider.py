# providers/google_sheets_oauth_provider.py
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple, List
import asyncio

from googleapiclient.discovery import build
from bot.services.google_oauth import load_user_credentials


def _parse_sheet_id_and_range(url_or_id: str) -> tuple[str, Optional[str]]:
    s = (url_or_id or "").strip()
    rng = None
    if "spreadsheets/d/" in s:
        sid = s.split("spreadsheets/d/", 1)[1].split("/", 1)[0]
        if "?range=" in s:
            rng = s.split("?range=", 1)[1].split("&", 1)[0]
    else:
        sid = s
    return sid, rng


def _to_col_letters(n: int) -> str:
    n = max(1, int(n))
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


async def get_sheet_as_text_oauth(
    user_id: int,
    url_or_id: str,
    *,
    max_rows_per_sheet: int = 200,   # сколько строк данных выводим в текст на лист
    max_scan_rows: int = 1000,       # сколько максимум строк запрашиваем у API
    max_cols: int = 26,              # до колонки Z
    include_empty: bool = False      # включать ли полностью пустые листы в вывод
) -> Dict[str, Any]:
    """Читает ВСЕ листы таблицы через OAuth пользователя и собирает плоский текст."""
    creds = await load_user_credentials(user_id)
    service = build("sheets", "v4", credentials=creds)

    sheet_id, rng = _parse_sheet_id_and_range(url_or_id)

    # --- метаданные
    def _fetch_meta():
        return service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    meta = await asyncio.to_thread(_fetch_meta)

    title = meta.get("properties", {}).get("title", "")
    sheets = meta.get("sheets", []) or []

    lines: List[str] = [f"[GOOGLE SHEETS] {title}"]


    async def _fetch_values(range_a1: str) -> List[List[str]]:
        def _inner():
            return service.spreadsheets().values().get(
                spreadsheetId=sheet_id, range=range_a1
            ).execute()
        vr = await asyncio.to_thread(_inner)
        return vr.get("values", []) or []

    # Если задан конкретный диапазон — уважаем его (историческое поведение).
    if rng:
        values = await _fetch_values(rng)
        lines.append(f"RANGE: {rng}")
        if values:
            headers = values[0]
            lines.append("COLUMNS: " + " | ".join(str(h) for h in headers))
            for i, row in enumerate(values[1:max_rows_per_sheet+1], start=1):
                row = list(row) + [""] * (len(headers) - len(row))
                lines.append(f"ROW {i}: " + " | ".join(str(c) for c in row))
        else:
            lines.append("(no values)")
        return {"id": sheet_id, "title": title, "content": "\n".join(lines)}

    # Иначе — обходим ВСЕ листы
    any_output = False
    for sh in sheets:
        props = sh.get("properties", {}) or {}
        name = props.get("title", "Sheet1")
        gp = props.get("gridProperties", {}) or {}

        row_count = int(gp.get("rowCount") or 500)
        col_count = int(gp.get("columnCount") or 26)
        # безопасные «сканы»
        row_scan = max(50, min(row_count, max_scan_rows))
        col_scan = max(5, min(col_count, max_cols))

        rng_try = f"{name}!A1:{_to_col_letters(col_scan)}{row_scan}"
        values = await _fetch_values(rng_try)

        # пустые листы по умолчанию пропускаем
        nonempty = sum(1 for r in values if any((c or "").strip() for c in r))
        if nonempty == 0 and not include_empty:
            continue

        any_output = True
        lines.append(f"\n## SHEET: {name}")
        lines.append(f"RANGE: {rng_try}")

        if values:
            headers = values[0]
            lines.append("COLUMNS: " + " | ".join(str(h) for h in headers))
            for i, row in enumerate(values[1:max_rows_per_sheet+1], start=1):
                row = list(row) + [""] * (len(headers) - len(row))
                lines.append(f"ROW {i}: " + " | ".join(str(c) for c in row))
        else:
            lines.append("(no values)")

    if not any_output:
        lines.append("(no values across all sheets)")

    return {"id": sheet_id, "title": title, "content": "\n".join(lines)}
