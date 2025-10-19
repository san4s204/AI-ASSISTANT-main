# stt/provider.py
from __future__ import annotations
import os, asyncio
from typing import Optional

_BACKEND = os.getenv("STT_BACKEND", "faster_whisper").lower()

# ---------- faster-whisper ----------
_MODEL = None
def _fw_get_model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        name = os.getenv("WHISPER_MODEL", "small")
        compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        _MODEL = WhisperModel(name, device="cpu", compute_type=compute)
    return _MODEL

def _fw_transcribe_sync(path: str, lang_hint: Optional[str] = "ru") -> str:
    model = _fw_get_model()
    segments, info = model.transcribe(
        path,
        language=lang_hint,  # можно None — автоопределение
        beam_size=1,
        vad_filter=True,
    )
    return " ".join(seg.text for seg in segments).strip()

async def transcribe_file(path: str, lang_hint: Optional[str] = "ru") -> str:
    """
    Распознаёт аудио-файл и возвращает текст.
    По умолчанию backend=faster_whisper (локально, CPU).
    """
    if _BACKEND == "faster_whisper":
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _fw_transcribe_sync, path, lang_hint)

    # Тут легко добавить другие бэкенды (OpenAI, Deepgram и т.п.)
    # raise NotImplementedError("STT backend not configured")
    # Для простоты пока fallback к faster-whisper:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fw_transcribe_sync, path, lang_hint)
