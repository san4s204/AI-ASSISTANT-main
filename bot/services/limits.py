from __future__ import annotations
import os
import aiosqlite
from typing import Dict

DB_PATH = os.getenv("DB_PATH", "db.db")

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

RPM_MAP: Dict[str, int] = {
    "free":    _env_int("LIMITS_RPM_FREE", 20),
    "premium": _env_int("LIMITS_RPM_PREMIUM", 60),
}

RPD_MAP: Dict[str, int] = {
    "free":    _env_int("LIMITS_RPD_FREE", 500),
    "premium": _env_int("LIMITS_RPD_PREMIUM", 5000),
}

async def resolve_plan(user_id: int) -> str:
    """
    Возвращает "premium" если у пользователя активная подписка,
    иначе "free".
    Совместимо с текущей схемой: subscribe='subscribe' + проверка date_end.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute(
                "SELECT subscribe, date_end FROM users WHERE id = ? LIMIT 1",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return "free"
        subscribe, date_end = row[0], row[1]
        if str(subscribe or "").lower() != "subscribe":
            return "free"
        if date_end:
            import datetime as dt
            try:
                if dt.datetime.now() >= dt.datetime.fromisoformat(str(date_end)):
                    return "free"
            except Exception:
                # если формат странный — трактуем как активную (как в get_subscription_until)
                pass
        return "premium"
    except Exception:
        return "free"

# === Месячные квоты токенов по планам ===
TOKEN_ALLOWANCE_MAP: Dict[str, int] = {
    "free":    _env_int("LIMITS_TOKENS_FREE",    400),   # ~малые объемы
    "premium": _env_int("LIMITS_TOKENS_PREMIUM", 80000), # побольше
}

async def month_token_allowance(user_id: int) -> int:
    plan = await resolve_plan(user_id)
    return int(TOKEN_ALLOWANCE_MAP.get(plan, TOKEN_ALLOWANCE_MAP["free"]))