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
OPENROUTER_REFERER = os.getenv("OPEN_ROUTER_REFERER")
OPENROUTER_TITLE = os.getenv("OPEN_ROUTER_TITLE")

MODEL = "anthropic/claude-3.5-sonnet"
TTL_SECONDS = 3600  # 1 час


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def _system_hash(system_content: str) -> str:
    return _md5(system_content)[:16]


def build_system_prompt(ans: dict | None) -> str:
    """
    ans может быть None, если doc_id не задан или источник недоступен.
    """
    if not ans:
        # fallback system prompt без каталога
        return (
            "Ты ИИ-менеджер. Если у тебя нет данных каталога/услуг, честно скажи, что источник знаний не подключён/недоступен, "
            "и предложи пользователю подключить Google Doc/Sheet через /prompt. "
            "Не выдумывай услуги, цены и условия.\n"
            "Отвечай по-русски, дружелюбно и профессионально, без воды. 1–4 предложения."
        )

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


async def answer(
    text: str,
    doc_id: str,
    owner_id: int | None = None,
    history: list[tuple[str, str]] | None = None,
    extra_system: str | None = None,   # ✅ добавили
) -> str:
    ans = None
    source_error = None

    # ✅ больше НЕ делаем ранний return при пустом doc_id
    if (doc_id or "").strip():
        try:
            ans = await doc(doc_id, owner_user_id=owner_id)  # {'id','title','content','kind'}
        except FileNotFoundError:
            source_error = "Документ/таблица не найдены или нет доступа."
        except Exception as e:
            source_error = f"Ошибка чтения источника: {e.__class__.__name__}"

    system_content = build_system_prompt(ans)

    if source_error:
        system_content += (
            "\n\nВАЖНО: Источник знаний сейчас недоступен: "
            f"{source_error} "
            "Если вопрос пользователя требует данных из источника — честно сообщи об этом."
        )

    # ✅ добавляем системные инструкции календаря (если передали)
    if extra_system and extra_system.strip():
        system_content += "\n\n" + extra_system.strip()

    sys_hash = _system_hash(system_content)

    # --- КЭШ ТОЛЬКО БЕЗ ИСТОРИИ ---
    cache_key = None
    if not history:
        doc_key = (doc_id or "").strip() or "no-doc"
        cache_key = f"openrouter:{doc_key}:{sys_hash}:{_md5(text)}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached
    # --- конец блока кэша ---

    if not OPEN_ROUTER_API_KEY:
        raise RuntimeError("OPEN_ROUTER_API_KEY is not set (add it to .env).")

    messages = [{"role": "system", "content": system_content}]

    if history:
        for role, msg in history:
            role = "assistant" if role == "assistant" else "user"
            msg = (msg or "").strip()
            if not msg:
                continue
            messages.append({"role": role, "content": msg})

    messages.append({"role": "user", "content": text})

    payload = {"model": MODEL, "messages": messages}
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
    async with aiohttp.ClientSession(timeout=timeout,
                                     connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        async with session.post(OPENROUTER_URL, json=payload, headers=headers) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                hint = " (Invalid key OR missing HTTP-Referer for Project Key)" if resp.status == 401 else ""
                raise RuntimeError(f"OpenRouter error {resp.status}{hint}: {data}")
            try:
                result = data["choices"][0]["message"]["content"]
            except Exception:
                raise RuntimeError(f"Unexpected OpenRouter response shape: {data}")

    if cache_key:
        await cache_setex(cache_key, TTL_SECONDS, result)

    return result
