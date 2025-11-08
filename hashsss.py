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


MODEL = "anthropic/claude-3.5-sonnet"
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
        "Ты ИИ-менеджер по продажам. Отвечаешь ТОЛЬКО на основе данных ниже. "
        "Данные уже извлечены из Google "
        + ("Sheets (таблица)." if kind == "sheet" else "Docs (документ). ")
        + "Это одновременно и каталог товаров/услуг, и инструкция по общению с клиентами. "
        "Если внутри данных есть специальные инструкции для ассистента, сценарии, описание тона общения, имени менеджера и т.п. — строго им следуй. "
        "Ничего не выдумывай: не придумывай товары, характеристики, цены, акции или условия, которых нет в данных. "
        "Если нужной информации нет, честно скажи об этом и предложи ближайшие по параметрам варианты только из доступных данных. "
        "Твоя задача — вести диалог как профессиональный продажник: выяснять потребности, подбирать 1–3 подходящих варианта, "
        "обрабатывать возражения и мягко подводить к следующему целевому шагу (заявка, запись, оплата — как описано в данных). "
        "Отвечай по-русски, дружелюбно и профессионально, без воды. Сообщения делай короткими: 1–4 предложения, списки только по делу."
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
    # 0) нет источника — сразу дружелюбный ответ
    if not (doc_id or "").strip():
        return (
            "ℹ️ Источник знаний не подключён.\n\n"
            "Отправьте ссылку/ID Google Doc или Sheet командой /prompt, "
            "или добавьте документ в настройках."
        )

    try:
        ans = await doc(doc_id, owner_user_id=owner_id)  # {'id','title','content','kind'}
    except FileNotFoundError:
        return (
            "⚠️ Документ/таблица не найдены или нет доступа.\n"
            "Проверьте ссылку/ID и права общего доступа (как минимум «Просмотр по ссылке»), затем попробуйте снова."
        )
    except Exception as e:
        # любые прочие ошибки Google/сетевые — коротко
        return f"⚠️ Ошибка при чтении источника: {e.__class__.__name__}. Попробуйте позже."

    system_content = build_system_prompt(ans)
    logging.info(
        "system_prompt kind=%s title=%r len=%d head=%r",
        ans.get("kind"), ans.get("title"), len(system_content),
        system_content[:160].replace("\n", " ")
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
                hint = " (Invalid key OR missing HTTP-Referer for Project Key)" if resp.status == 401 else ""
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
