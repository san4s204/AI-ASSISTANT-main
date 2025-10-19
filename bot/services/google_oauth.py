from __future__ import annotations
import hmac, hashlib, base64
from typing import Optional, Dict
import datetime

import aiosqlite
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config import (
    GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, OAUTH_REDIRECT_URI,
    OAUTH_STATE_SECRET, DB_PATH
)

SCOPES = [
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",

]

def _client_config() -> Dict:
    return {
        "web": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "project_id": "ai-assistant",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uris": [OAUTH_REDIRECT_URI],
        }
    }

def _sign_state(payload: str) -> str:
    sig = hmac.new(OAUTH_STATE_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")

def make_state(user_id: int) -> str:
    # кодируем user_id + таймштамп
    ts = int(datetime.datetime.utcnow().timestamp())
    payload = f"{user_id}:{ts}"
    sig = _sign_state(payload)
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

def parse_state(state: str) -> Optional[int]:
    try:
        raw = base64.urlsafe_b64decode(state + "==").decode()
        user_id_str, ts_str, sig = raw.split(":")
        payload = f"{user_id_str}:{ts_str}"
        if hmac.compare_digest(sig, _sign_state(payload)):
            return int(user_id_str)
    except Exception:
        return None
    return None

def build_flow() -> Flow:
    return Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=OAUTH_REDIRECT_URI,
    )

async def build_auth_url(user_id: int) -> str:
    flow = build_flow()
    state = make_state(user_id)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return auth_url

async def exchange_code_for_tokens(code: str) -> Credentials:
    flow = build_flow()
    flow.fetch_token(code=code)
    return flow.credentials  # содержит refresh_token, access_token и т.д.

# ----- Хранилище токенов -----

async def save_refresh_token(user_id: int, creds: Credentials) -> None:
    # refresh_token может прийти только при первом согласии или при prompt=consent
    if not creds.refresh_token:
        raise RuntimeError("No refresh_token in OAuth response")
    scopes = " ".join(sorted(creds.scopes or SCOPES))
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO google_tokens (user_id, refresh_token, scopes)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              refresh_token=excluded.refresh_token,
              scopes=excluded.scopes
            """,
            (user_id, creds.refresh_token, scopes),
        )
        await conn.commit()

async def has_google_oauth(user_id: int | str) -> bool:
    """
    Возвращает True, если для пользователя есть OAuth-токены Google.
    Если таблицы нет — считаем, что не подключено.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            # название таблицы подставь своё, если другое
            async with conn.execute(
                "SELECT 1 FROM google_tokens WHERE user_id=? LIMIT 1", (user_id,)
            ) as cur:
                return (await cur.fetchone()) is not None
    except Exception:
        return False

async def delete_refresh_token(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("DELETE FROM google_tokens WHERE user_id = ?", (user_id,))
        await conn.commit()

async def load_user_credentials(user_id: int) -> Optional[Credentials]:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT refresh_token, scopes FROM google_tokens WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    refresh_token, scopes = row[0], (row[1] or "")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_OAUTH_CLIENT_ID,
        client_secret=GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=scopes.split(),
    )
    # освежим access_token при необходимости
    try:
        if not creds.valid:
            creds.refresh(Request())
    except Exception:
        # если refresh не удался — считаем, что токен протух
        return None
    return creds