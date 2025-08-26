# providers/google_calendar_oauth_provider.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from googleapiclient.discovery import build

from bot.services.google_oauth import load_user_credentials

DEFAULT_TZ = ZoneInfo("Europe/Berlin")  # можно вынести в .env

def _rfc3339(dt: datetime) -> str:
    # всегда с таймзоной
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.isoformat()

async def get_user_timezone_oauth(user_id: int) -> ZoneInfo:
    """Берём TZ из настроек аккаунта Google; если недоступно — локальная tz процесса."""
    creds = await load_user_credentials(user_id)
    service = build("calendar", "v3", credentials=creds)

    def _get():
        return service.settings().get(setting="timezone").execute()

    try:
        tzname = (await asyncio.to_thread(_get)).get("value") or ""
        try:
            return ZoneInfo(tzname)
        except ZoneInfoNotFoundError:
            return datetime.now().astimezone().tzinfo  # fallback
    except Exception:
        return datetime.now().astimezone().tzinfo  # fallback

def _iso(dt: datetime) -> str:
    # Google API принимает локальный ISO8601 с таймзоной
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=DEFAULT_TZ)
    return dt.isoformat()

async def _svc(user_id: int):
    creds = await load_user_credentials(user_id)
    # v3 — актуальная для Calendar
    return build("calendar", "v3", credentials=creds)

async def list_upcoming_events_oauth(
    user_id: int,
    *,
    days: int = 7,
    calendar_id: str = "primary",
    now: Optional[datetime] = None,
    max_results: int = 20,
) -> List[Dict[str, Any]]:
    """
    Возвращает список ближайших событий за `days` дней.
    """
    now = (now or datetime.now(DEFAULT_TZ)).astimezone(DEFAULT_TZ)
    time_min = _iso(now)
    time_max = _iso(now + timedelta(days=days))

    service = await _svc(user_id)

    def _fetch():
        return service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=max_results,
        ).execute()

    data = await asyncio.to_thread(_fetch)
    items = data.get("items", [])
    result: List[Dict[str, Any]] = []
    for it in items:
        start = it.get("start", {}).get("dateTime") or it.get("start", {}).get("date")
        end = it.get("end", {}).get("dateTime") or it.get("end", {}).get("date")
        result.append({
            "id": it.get("id"),
            "summary": it.get("summary", "(без названия)"),
            "location": it.get("location"),
            "htmlLink": it.get("htmlLink"),
            "start": start,
            "end": end,
        })
    return result

async def create_event_oauth(
    user_id: int,
    *,
    summary: str,
    start: datetime,
    end: datetime,
    calendar_id: str = "primary",
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,  # список email'ов
) -> Dict[str, Any]:
    """
    Создаёт событие в календаре пользователя. Возвращает созданный объект (включая htmlLink).
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=DEFAULT_TZ)
    if end.tzinfo is None:
        end = end.replace(tzinfo=DEFAULT_TZ)

    body: Dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": e} for e in attendees]

    service = await _svc(user_id)

    def _insert():
        return service.events().insert(calendarId=calendar_id, body=body).execute()

    return await asyncio.to_thread(_insert)

async def list_calendars_oauth(user_id: int) -> List[Dict[str, Any]]:
    creds = await load_user_credentials(user_id)
    service = build("calendar", "v3", credentials=creds)

    def _list():
        return service.calendarList().list().execute()
    data = await asyncio.to_thread(_list)
    items = data.get("items", []) or []
    # Оставим только нужное
    return [
        {
            "id": it.get("id"),
            "summary": it.get("summary", "(без названия)"),
            "primary": it.get("primary", False),
        }
        for it in items
    ]

async def list_events_between_oauth(
    user_id: int,
    calendar_id: str,
    time_min: datetime,
    time_max: datetime,
) -> List[Dict[str, Any]]:
    creds = await load_user_credentials(user_id)
    service = build("calendar", "v3", credentials=creds)

    def _list():
        return service.events().list(
            calendarId=calendar_id,
            timeMin=_rfc3339(time_min),
            timeMax=_rfc3339(time_max),
            singleEvents=True,       # разворачиваем повторяющиеся
            orderBy="startTime",
        ).execute()

    data = await asyncio.to_thread(_list)
    return data.get("items", []) or []