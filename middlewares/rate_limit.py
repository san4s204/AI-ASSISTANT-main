from __future__ import annotations
from typing import Callable, Any, Dict, Awaitable, Optional
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from datetime import datetime, timezone, timedelta

def parse_admins(s: Optional[str]) -> set[int]:
    if not s:
        return set()
    out: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except Exception:
            continue
    return out

def _seconds_to_midnight_utc() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((tomorrow - now).total_seconds())

class RateLimitMiddleware(BaseMiddleware):
    """
    Простые лимиты per-user:
      - RPM (fixed window 60s)
      - RPD (fixed window до полуночи UTC)

    Redis-ключи:
      rl:{key}:m:{YYYYMMDDHHMM}
      rl:{key}:d:{YYYYMMDD}

    Где {key} — это идентификатор пользователя (по умолчанию event.from_user.id),
    либо то, что вернёт user_key_resolver(event), если он задан (например, owner_id).
    """
    def __init__(
        self,
        redis,
        rpm_map: Dict[str, int],
        rpd_map: Dict[str, int],
        plan_resolver: Callable[[int], Awaitable[str]],
        admin_ids: set[int] | None = None,
        metric_prefix: str = "rl",
        user_key_resolver: Optional[Callable[[Any], Optional[int]]] = None,
    ):
        super().__init__()
        self.redis = redis
        self.rpm_map = rpm_map
        self.rpd_map = rpd_map
        self.plan_resolver = plan_resolver
        self.admin_ids = admin_ids or set()
        self.metric_prefix = metric_prefix
        self.user_key_resolver = user_key_resolver

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any]
    ) -> Any:
        # определяем идентификатор для лимитов
        user_id: Optional[int] = None

        if self.user_key_resolver is not None:
            try:
                user_id = self.user_key_resolver(event)
            except Exception:
                user_id = None

        if user_id is None:
            if isinstance(event, Message) and event.from_user:
                user_id = event.from_user.id
            elif isinstance(event, CallbackQuery) and event.from_user:
                user_id = event.from_user.id

        if user_id is None:
            # системные апдейты или не определили ключ — пропускаем
            return await handler(event, data)

        if user_id in self.admin_ids:
            return await handler(event, data)

        # какой у пользователя план (free/premium...)
        plan = await self.plan_resolver(int(user_id))
        rpm = int(self.rpm_map.get(plan, self.rpm_map.get("free", 20)))
        rpd = int(self.rpd_map.get(plan, self.rpd_map.get("free", 500)))

        # ключи для минутного и суточного окна
        now = datetime.now(timezone.utc)
        minute_key = f"{self.metric_prefix}:{user_id}:m:{now.strftime('%Y%m%d%H%M')}"
        day_key    = f"{self.metric_prefix}:{user_id}:d:{now.strftime('%Y%m%d')}"

        # атомарно инкрементим и ставим TTL
        pipe = self.redis.pipeline()
        pipe.incr(minute_key)
        pipe.expire(minute_key, 60)
        pipe.incr(day_key)
        pipe.expire(day_key, _seconds_to_midnight_utc())
        m_count, _, d_count, _ = await pipe.execute()

        # проверяем лимиты
        if int(m_count) > rpm or int(d_count) > rpd:
            text = (
                "⛔️ Превышен лимит запросов.\n\n"
                f"Минутный лимит: {rpm}, сегодня: {int(d_count)}/{rpd}.\n"
                "Попробуйте позже или обновите тариф в «Настройках»."
            )
            try:
                if isinstance(event, Message):
                    await event.answer(text)
                elif isinstance(event, CallbackQuery):
                    await event.answer("Превышен лимит. Попробуйте позже.", show_alert=True)
                    await event.message.answer(text)
            except Exception:
                pass
            return  # блокируем

        return await handler(event, data)
