# bot/web/oauth_app.py
from __future__ import annotations
from aiohttp import web
from aiogram import Bot

from config import OAUTH_HOST, OAUTH_PORT
from bot.services.google_oauth import (
    build_auth_url, parse_state, exchange_code_for_tokens, save_refresh_token,
)

routes = web.RouteTableDef()

def make_app(bot: Bot) -> web.Application:
    app = web.Application()

    async def start(request: web.Request) -> web.Response:
        # ?uid=123
        try:
            uid = int(request.query.get("uid", ""))
        except Exception:
            return web.Response(text="Missing or invalid uid", status=400)
        url = await build_auth_url(uid)
        raise web.HTTPFound(url)

    async def callback(request: web.Request) -> web.Response:
        params = request.rel_url.query
        state = params.get("state")
        code = params.get("code")
        if not state or not code:
            return web.Response(text="Missing state or code", status=400)
        user_id = parse_state(state)
        if not user_id:
            return web.Response(text="Bad state", status=400)

        try:
            creds = await exchange_code_for_tokens(code)
            await save_refresh_token(user_id, creds)
            # уведомим пользователя в TG
            try:
                await bot.send_message(user_id, "✅ Google подключён. Можно использовать Docs/Sheets без шаринга.")
            except Exception:
                pass
            return web.Response(text="Success! You can return to Telegram.")
        except Exception as e:
            return web.Response(text=f"OAuth error: {e}", status=500)

    app.router.add_get("/oauth/google/start", start)
    app.router.add_get("/oauth/google/callback", callback)
    app.add_routes(routes)
    return app

async def start_oauth_webserver(bot: Bot):
    app = make_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=OAUTH_HOST, port=int(OAUTH_PORT))
    await site.start()
    return runner  # можно хранить, чтобы останавливать при shutdown

@routes.get("/oauth/health")
async def health(_):
    return web.Response(text="ok")