import os, sys, json, asyncio
from pathlib import Path

def ok(msg): print(f"[OK] {msg}")
def warn(msg): print(f"[WARN] {msg}")
def fail(msg): print(f"[FAIL] {msg}")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 1) Load config & env
try:
    import config
    ok("config.py импортирован")
except Exception as e:
    fail(f"config.py не импортируется: {e}")
    sys.exit(1)

# 2) Required env vars presence (non-strict)
required = ["BOT_TOKEN", "YOOKASSA_ACCOUNT_ID", "YOOKASSA_SECRET_KEY", "CRYPTO_TOKEN"]
missing = [k for k in required if not os.getenv(k)]
if missing:
    warn(f"В .env отсутствуют/пустые: {missing}")
else:
    ok("Ключевые переменные окружения присутствуют")

# 3) Redis connectivity
async def check_redis():
    try:
        import redis.asyncio as redis
        from providers.redis_provider import get_redis
        r = get_redis()
        pong = await r.ping()
        ok(f"Redis доступен (PING={pong})")
    except Exception as e:
        fail(f"Redis недоступен: {e}")

# 4) Google Docs client and service account file
def check_google():
    try:
        from providers.google_docs_provider import get_document
        ok("Импорт Google Docs провайдера успешен")
    except Exception as e:
        fail(f"Google провайдер не импортируется: {e}")
    p = Path(os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json"))
    if p.exists():
        ok(f"Файл сервисного аккаунта найден: {p}")
    else:
        warn(f"Файл сервисного аккаунта не найден: {p}")

# 5) Aiogram / aiosend imports
def check_imports():
    try:
        import aiogram
        ok(f"aiogram установлен: {aiogram.__version__ if hasattr(aiogram, '__version__') else 'ok'}")
    except Exception as e:
        fail(f"aiogram не установлен/ошибка импорта: {e}")

    try:
        import aiosend
        ok("aiosend установлен")
    except Exception as e:
        warn(f"aiosend не установлен или приватный: {e}")

async def main():
    check_imports()
    check_google()
    await check_redis()
    ok("Диагностика завершена")

if __name__ == "__main__":
    asyncio.run(main())
