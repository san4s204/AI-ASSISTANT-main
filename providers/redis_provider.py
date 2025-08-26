from __future__ import annotations
from typing import Optional
import redis.asyncio as redis
from config import REDIS_HOST, REDIS_PORT, REDIS_DB  # при желании добавь REDIS_PASSWORD / REDIS_URL

_redis: Optional[redis.Redis] = None

def get_redis() -> redis.Redis:
    """Ленивая инициализация async Redis-клиента (без коннекта на import)."""
    global _redis
    if _redis is None:
        # decode_responses=False -> r.get() возвращает bytes; декодируем вручную в cache_get
        _redis = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=False,
            # password=REDIS_PASSWORD,  # если есть
            # ssl=True,                 # если нужно TLS
        )
    return _redis

async def cache_get(key: str) -> Optional[str]:
    r = get_redis()
    val = await r.get(key)
    if val is None:
        return None
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except Exception:
            return None
    return str(val)

async def cache_setex(key: str, ttl: int, value: str) -> bool:
    r = get_redis()
    return bool(await r.setex(key, ttl, value))

async def cache_delete(key: str) -> int:
    r = get_redis()
    return int(await r.delete(key))

async def delete_by_pattern(pattern: str, count_hint: int = 1000) -> int:
    """Удалить все ключи по шаблону. Возвращает количество удалённых."""
    r = get_redis()
    deleted = 0
    async for key in r.scan_iter(match=pattern, count=count_hint):
        deleted += int(await r.delete(key))
    return deleted

async def close_redis() -> None:
    """Корректно закрыть клиент и освободить пул соединений."""
    global _redis
    if _redis is None:
        return
    r = _redis
    _redis = None
    try:
        # redis>=5
        await r.aclose()
    except AttributeError:
        # более старые версии: close() синхронный
        try:
            r.close()  # type: ignore[func-returns-value]
        except Exception:
            pass
        try:
            # на всякий случай разорвём пул (sync)
            r.connection_pool.disconnect()  # type: ignore[attr-defined]
        except Exception:
            pass