from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")

CAL_TRIGGERS = ("календар", "событ", "встреч", "созвон", "мит", "митап")

def looks_calendar(text: str) -> bool:
    s = (text or "").lower()
    return any(t in s for t in CAL_TRIGGERS) or any(
        k in s for k in ("сегодня", "завтр", "недел", "выходн")
    )

def parse_range_ru(text: str, tz) -> tuple[datetime, datetime, str]:
    """Вернёт (start, end, label) в TZ пользователя."""
    s = (text or "").lower()
    now = datetime.now(tz)

    def day_bounds(d: datetime):
        start = d.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)

    if "сегодня" in s:
        a, b = day_bounds(now);  return a, b, "сегодня"
    if "завтр" in s:
        a, b = day_bounds(now + timedelta(days=1));  return a, b, "завтра"
    if "выходн" in s:
        wd = now.weekday()  # 0=Mon
        days_to_sat = (5 - wd) % 7
        start = (now + timedelta(days=days_to_sat)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=2)
        return start, end, "на выходных"
    if "недел" in s:
        return now, now + timedelta(days=7), "на неделю"

    return now, now + timedelta(days=1), "на сутки"

def fmt_events(items: list[dict]) -> str:
    """Красивый вывод списка событий; учитывает all-day и dateTime."""
    if not items:
        return "Событий не найдено."
    out = []
    for ev in items[:20]:
        title = ev.get("summary") or "Без названия"
        start = ev.get("start", {}) or {}
        end = ev.get("end", {}) or {}

        if "date" in start:   # all-day
            when = f"{start['date']} → {end.get('date', start['date'])}"
        else:
            def _fmt(s: str) -> str:
                from datetime import datetime as dti
                try:
                    dt = dti.fromisoformat((s or "").replace("Z", "+00:00"))
                    return dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    return s or ""
            when = f"{_fmt(start.get('dateTime',''))} → {_fmt(end.get('dateTime',''))}"

        location = ev.get("location")
        link = ev.get("htmlLink")
        block = f"• <b>{title}</b>\n{when}"
        if location:
            block += f"\n{location}"
        if link:
            block += f"\n{link}"
        out.append(block)
    return "\n\n".join(out)