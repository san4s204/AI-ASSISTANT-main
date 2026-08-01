# hashsss.py

from __future__ import annotations

import hashlib

from dotenv import load_dotenv

from deepseek import doc
from providers.redis_provider import cache_get, cache_setex
from providers.llm_provider import (
    LLMResponse,
    LLMUsage,
    complete_chat,
    current_model,
)

load_dotenv(override=True)

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
    extra_system: str | None = None,
) -> LLMResponse:
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
        cache_key = f"llm:{doc_key}:{sys_hash}:{_md5(text)}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return LLMResponse(
                text=cached,
                model=current_model(),
                usage=LLMUsage(),
                cached=True,
            )
    # --- конец блока кэша ---

    messages = [{"role": "system", "content": system_content}]

    if history:
        for role, msg in history:
            role = "assistant" if role == "assistant" else "user"
            msg = (msg or "").strip()
            if not msg:
                continue
            messages.append({"role": role, "content": msg})

    messages.append({"role": "user", "content": text})

    result = await complete_chat(messages)

    if cache_key:
        await cache_setex(cache_key, TTL_SECONDS, result.text)

    return result
