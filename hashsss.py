# hashsss.py
from __future__ import annotations
from typing import Optional
import os
import hashlib
import aiohttp
import ssl
import certifi
from dotenv import load_dotenv

from providers.redis_provider import cache_get, cache_setex, delete_by_pattern
from deepseek import doc
import logging
logging.basicConfig(level=logging.INFO)


load_dotenv(override=True)

OPEN_ROUTER_API_KEY = os.getenv("OPEN_ROUTER_API_KEY") or os.getenv("OR_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER")
OPENROUTER_TITLE = os.getenv("OPENROUTER_TITLE")


MODEL = "openai/gpt-4o"
TTL_SECONDS = 3600  # 1 час

def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def _system_hash(system_content: str) -> str:
    return _md5(system_content)[:16]

def build_system_prompt(ans: dict) -> str:
    kind = ans.get("kind", "doc")
    title = ans.get("title", "")
    content = ans.get("content", "")

    header = (
        "Ты ассистент, отвечающий ТОЛЬКО по данным ниже. "
        "Данные уже извлечены из Google "
        + ("Sheets (таблица)." if kind == "sheet" else "Docs (документ).")
        + " Не фантазируй. Если ответа в данных нет — так и скажи. "
        "Отвечай по-русски, кратко и по делу."
    )

    return (
        f"{header}\n\n"
        f"=== ИСТОЧНИК ===\n"
        f"Заголовок: {title}\n"
        f"Тип: {('Таблица' if kind=='sheet' else 'Документ')}\n"
        f"--- НАЧАЛО ДАННЫХ ---\n"
        f"{content}\n"
        f"--- КОНЕЦ ДАННЫХ ---"
    )

async def answer(text: str, doc_id: str, owner_id: int | None = None) -> str:
    ans = await doc(doc_id, owner_user_id=owner_id)  # {'id','title','content'}
    system_content = build_system_prompt(ans)
    logging.info(
        "system_prompt kind=%s title=%r len=%d head=%r",
        ans.get("kind"), ans.get("title"), len(system_content),
        system_content[:160].replace("\n"," ")  # в лог — первые ~160 символов
    )

    sys_hash = _system_hash(system_content)

    cache_key = f"openrouter:{doc_id}:{sys_hash}:{_md5(text)}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    if not OPEN_ROUTER_API_KEY:
        raise RuntimeError(
            "OPEN_ROUTER_API_KEY is not set (add it to .env). "
            "Get a key at https://openrouter.ai/keys"
        )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": text},
        ],
    }
    headers = {
        "Authorization": f"Bearer {OPEN_ROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    # Project Keys требуют HTTP-Referer
    if OPENROUTER_REFERER:
        headers["HTTP-Referer"] = OPENROUTER_REFERER
    if OPENROUTER_TITLE:
        headers["X-Title"] = OPENROUTER_TITLE

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        async with session.post(OPENROUTER_URL, json=payload, headers=headers) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                # Подсказка для 401
                if resp.status == 401:
                    hint = " (Invalid key OR missing HTTP-Referer for Project Key)"
                else:
                    hint = ""
                raise RuntimeError(f"OpenRouter error {resp.status}{hint}: {data}")
            try:
                result = data["choices"][0]["message"]["content"]
            except Exception:
                raise RuntimeError(f"Unexpected OpenRouter response shape: {data}")

    await cache_setex(cache_key, TTL_SECONDS, result)
    return result

# Для очистки кэша
async def clean(system_hash: str, doc_id: Optional[str] = None) -> int:
    """
    Удаляет кэш по системному промпту.
    Если указан doc_id — чистим только его ключи.
    """
    pattern = f"openrouter:{doc_id}:{system_hash}:*" if doc_id else f"openrouter:*:{system_hash}:*"
    return await delete_by_pattern(pattern)
