from __future__ import annotations

import asyncio
import os
import ssl
from dataclasses import dataclass
from typing import Any

import aiohttp
import certifi

DEFAULT_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-5.4-mini"
TRANSIENT_STATUSES = {408, 429, 502, 503, 504}


@dataclass(frozen=True, slots=True)
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float | None = None


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    model: str
    usage: LLMUsage = LLMUsage()
    provider: str | None = None
    finish_reason: str | None = None
    cached: bool = False


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        error_type: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error_type = error_type
        self.retryable = retryable


def current_model() -> str:
    return (
        os.getenv("LLM_MODEL")
        or os.getenv("OPENROUTER_MODEL")
        or DEFAULT_MODEL
    ).strip()


def _api_key() -> str:
    return (
        os.getenv("LLM_API_KEY")
        or os.getenv("OPEN_ROUTER_API_KEY")
        or os.getenv("OR_API_KEY")
        or ""
    ).strip()


def _api_url() -> str:
    return (
        os.getenv("LLM_API_URL")
        or os.getenv("OPENROUTER_URL")
        or DEFAULT_API_URL
    ).strip()


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _extract_error(data: Any, status: int | None) -> LLMProviderError:
    error: Any = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        error = {}

    metadata = error.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    resolved_status = status if status is not None and status >= 400 else error.get("code") or status
    try:
        resolved_status = int(resolved_status) if resolved_status is not None else None
    except (TypeError, ValueError):
        resolved_status = status

    error_type = metadata.get("error_type") or error.get("error_type")
    raw_message = str(error.get("message") or "LLM provider request failed")
    retryable = resolved_status in TRANSIENT_STATUSES or error_type in {
        "rate_limit_exceeded",
        "provider_overloaded",
        "provider_unavailable",
        "timeout",
    }
    return LLMProviderError(
        raw_message,
        status=resolved_status,
        error_type=str(error_type) if error_type else None,
        retryable=retryable,
    )


def _extract_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts).strip()
    return ""


def parse_chat_completion(data: Any, *, status: int = 200) -> LLMResponse:
    if status >= 400:
        raise _extract_error(data, status)
    if not isinstance(data, dict):
        raise LLMProviderError("LLM provider returned non-object JSON")
    if isinstance(data.get("error"), dict):
        raise _extract_error(data, status)

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMProviderError("LLM provider returned no choices", retryable=True)

    choice = choices[0]
    if not isinstance(choice, dict):
        raise LLMProviderError("LLM provider returned an invalid choice")
    if isinstance(choice.get("error"), dict):
        raise _extract_error({"error": choice["error"]}, status)

    message = choice.get("message")
    if not isinstance(message, dict):
        raise LLMProviderError("LLM provider returned no assistant message")

    text = _extract_content(message.get("content"))
    if not text:
        raise LLMProviderError("LLM provider returned an empty response", retryable=True)

    usage_data = data.get("usage")
    if not isinstance(usage_data, dict):
        usage_data = {}
    prompt_tokens = int(usage_data.get("prompt_tokens") or 0)
    completion_tokens = int(usage_data.get("completion_tokens") or 0)
    total_tokens = int(
        usage_data.get("total_tokens") or prompt_tokens + completion_tokens
    )
    raw_cost = usage_data.get("cost")
    try:
        cost = float(raw_cost) if raw_cost is not None else None
    except (TypeError, ValueError):
        cost = None

    return LLMResponse(
        text=text,
        model=str(data.get("model") or current_model()),
        provider=str(data["provider"]) if data.get("provider") else None,
        finish_reason=(
            str(choice["finish_reason"])
            if choice.get("finish_reason") is not None
            else None
        ),
        usage=LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
        ),
    )


async def complete_chat(messages: list[dict[str, str]]) -> LLMResponse:
    api_key = _api_key()
    if not api_key:
        raise LLMProviderError(
            "LLM API key is not configured",
            status=401,
            error_type="authentication",
        )

    api_url = _api_url()
    model = current_model()
    max_tokens = _env_int(
        "LLM_MAX_OUTPUT_TOKENS",
        _env_int("OPENROUTER_MAX_TOKENS", 700),
    )
    timeout_seconds = _env_int("LLM_TIMEOUT_SECONDS", 90)
    max_attempts = _env_int("LLM_MAX_ATTEMPTS", 2)

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if "openrouter.ai" in api_url:
        referer = os.getenv("OPENROUTER_REFERER")
        title = os.getenv("OPENROUTER_TITLE")
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-OpenRouter-Title"] = title

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        last_error: LLMProviderError | None = None
        for attempt in range(max_attempts):
            retry_delay: float | None = None
            try:
                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                ) as response:
                    try:
                        data = await response.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError):
                        body = (await response.text())[:500]
                        data = {
                            "error": {
                                "code": response.status,
                                "message": body or "LLM provider returned non-JSON data",
                            }
                        }
                    raw_retry_after = response.headers.get("Retry-After")
                    if raw_retry_after:
                        try:
                            retry_delay = min(max(float(raw_retry_after), 0.0), 30.0)
                        except ValueError:
                            retry_delay = None
                    result = parse_chat_completion(data, status=response.status)
                    return result
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = LLMProviderError(
                    f"LLM provider network error: {exc.__class__.__name__}",
                    retryable=True,
                )
            except LLMProviderError as exc:
                last_error = exc

            if not last_error.retryable or attempt + 1 >= max_attempts:
                raise last_error
            await asyncio.sleep(
                retry_delay if retry_delay is not None else min(2**attempt, 4)
            )

    raise last_error or LLMProviderError("LLM provider request failed")
