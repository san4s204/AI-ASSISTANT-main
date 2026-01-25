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
    # Google Calendar API ожидает RFC3339 (ISO с tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=DEFAULT_TZ)
    return dt.isoformat()


def _iso(dt: datetime) -> str:
    # Google API принимает ISO8601 с таймзоной
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=DEFAULT_TZ)
    return dt.isoformat()


async def _svc(user_id: int):
    creds = await load_user_credentials(user_id)
    if creds is None:
        raise RuntimeError("Google OAuth not connected or expired")
    # cache_discovery=False — практичнее для прод-окружений/контейнеров
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


async def get_user_timezone_oauth(user_id: int) -> ZoneInfo:
    """Берём TZ из настроек аккаунта Google; если недоступно — tz процесса."""
    try:
        service = await _svc(user_id)
    except Exception:
        return datetime.now().astimezone().tzinfo  # fallback

    def _get():
        return service.settings().get(setting="timezone").execute()

    try:
        tzname = (await asyncio.to_thread(_get)).get("value") or ""
        try:
            return ZoneInfo(tzname)
        except ZoneInfoNotFoundError:
            return datetime.now().astimezone().tzinfo
    except Exception:
        return datetime.now().astimezone().tzinfo


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
    attendees: Optional[List[str]] = None,
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


async def update_event_oauth(
    user_id: int,
    *,
    event_id: str,
    patch: Dict[str, Any],
    calendar_id: str = "primary",
) -> Dict[str, Any]:
    """
    Частично обновляет событие (PATCH) по event_id.
    patch — тело, которое вы хотите применить (например start/end/summary/location/description).
    """
    service = await _svc(user_id)

    def _patch():
        return service.events().patch(
            calendarId=calendar_id,
            eventId=event_id,
            body=patch,
        ).execute()

    return await asyncio.to_thread(_patch)


async def delete_event_oauth(
    user_id: int,
    *,
    event_id: str,
    calendar_id: str = "primary",
) -> bool:
    """Удаляет событие по event_id."""
    service = await _svc(user_id)

    def _delete():
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return True

    return await asyncio.to_thread(_delete)


async def list_calendars_oauth(user_id: int) -> List[Dict[str, Any]]:
    service = await _svc(user_id)

    def _list():
        return service.calendarList().list().execute()

    data = await asyncio.to_thread(_list)
    items = data.get("items", []) or []
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
    service = await _svc(user_id)

    def _list():
        return service.events().list(
            calendarId=calendar_id,
            timeMin=_rfc3339(time_min),
            timeMax=_rfc3339(time_max),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

    data = await asyncio.to_thread(_list)
    return data.get("items", []) or []
