import os, aiohttp, asyncio
async def ping():
    key = os.getenv("OPEN_ROUTER_API_KEY")
    headers = {"Authorization": f"Bearer {key}"}
    # для Project Key полезно добавить:
    ref = os.getenv("OPENROUTER_REFERER")
    if ref: headers["HTTP-Referer"] = ref
    async with aiohttp.ClientSession() as s:
        r = await s.get("https://openrouter.ai/api/v1/models", headers=headers)
        print(r.status, await r.text())
asyncio.run(ping())