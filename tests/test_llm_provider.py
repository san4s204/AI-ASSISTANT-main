from __future__ import annotations

import unittest

from providers.llm_provider import LLMProviderError, parse_chat_completion


class ParseChatCompletionTests(unittest.TestCase):
    def test_parses_text_and_real_usage(self) -> None:
        response = parse_chat_completion(
            {
                "model": "openai/gpt-5.4-mini",
                "provider": "OpenAI",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Готово"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 8,
                    "total_tokens": 128,
                    "cost": 0.001,
                },
            }
        )

        self.assertEqual(response.text, "Готово")
        self.assertEqual(response.usage.total_tokens, 128)
        self.assertEqual(response.usage.cost, 0.001)
        self.assertEqual(response.provider, "OpenAI")

    def test_parses_content_blocks(self) -> None:
        response = parse_chat_completion(
            {
                "model": "test/model",
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "Первая "},
                                {"type": "text", "text": "часть"},
                            ]
                        }
                    }
                ],
            }
        )
        self.assertEqual(response.text, "Первая часть")

    def test_preserves_typed_payment_error(self) -> None:
        with self.assertRaises(LLMProviderError) as raised:
            parse_chat_completion(
                {
                    "error": {
                        "code": 402,
                        "message": "Insufficient credits",
                        "metadata": {"error_type": "payment_required"},
                    }
                },
                status=402,
            )

        self.assertEqual(raised.exception.status, 402)
        self.assertEqual(raised.exception.error_type, "payment_required")
        self.assertFalse(raised.exception.retryable)

    def test_marks_rate_limit_as_retryable(self) -> None:
        with self.assertRaises(LLMProviderError) as raised:
            parse_chat_completion(
                {
                    "error": {
                        "code": 429,
                        "message": "Rate limited",
                        "metadata": {"error_type": "rate_limit_exceeded"},
                    }
                },
                status=429,
            )

        self.assertTrue(raised.exception.retryable)

    def test_detects_error_inside_successful_completion(self) -> None:
        with self.assertRaises(LLMProviderError):
            parse_chat_completion(
                {
                    "choices": [
                        {
                            "message": {"content": "partial"},
                            "finish_reason": "error",
                            "error": {
                                "code": 502,
                                "message": "Provider unavailable",
                                "metadata": {
                                    "error_type": "provider_unavailable"
                                },
                            },
                        }
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()
