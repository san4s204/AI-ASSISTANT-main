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
required = ["BOT_TOKEN", "YOOKASSA_ACCOUNT_ID", "YOOKASSA_SECRET_KEY"]
if os.getenv("CRYPTO_ENABLED", "0") == "1":
    required.append("CRYPTO_TOKEN")
missing = [k for k in required if not os.getenv(k)]
if missing:
    warn(f"В .env отсутствуют/пустые: {missing}")
else:
    ok("Ключевые переменные окружения присутствуют")

llm_key = os.getenv("LLM_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY") or os.getenv("OR_API_KEY")
if llm_key:
    ok(f"LLM API-ключ задан; модель: {os.getenv('LLM_MODEL', 'openai/gpt-5.4-mini')}")
else:
    fail("Не задан LLM_API_KEY/OPEN_ROUTER_API_KEY")

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


async def check_openrouter_auth():
    key = os.getenv("LLM_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY") or os.getenv("OR_API_KEY")
    api_url = os.getenv("LLM_API_URL") or os.getenv("OPENROUTER_URL") or "https://openrouter.ai/api/v1/chat/completions"
    if not key or "openrouter.ai" not in api_url:
        return
    try:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": f"Bearer {key}"},
            ) as response:
                payload = await response.json(content_type=None)
                if response.status == 200:
                    data = payload.get("data") if isinstance(payload, dict) else None
                    remaining = data.get("limit_remaining") if isinstance(data, dict) else None
                    suffix = f", доступный лимит: {remaining}" if remaining is not None else ""
                    ok(f"OpenRouter API-ключ действителен{suffix}")
                elif response.status == 401:
                    fail("OpenRouter отклонил API-ключ (401): ключ неверный или отозван")
                else:
                    fail(f"OpenRouter проверка ключа вернула HTTP {response.status}: {payload}")
    except Exception as e:
        fail(f"Не удалось проверить OpenRouter API-ключ: {e.__class__.__name__}: {e}")

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
    await check_openrouter_auth()
    ok("Диагностика завершена")

if __name__ == "__main__":
    asyncio.run(main())
