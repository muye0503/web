import asyncio
import json
import os
from playwright.async_api import async_playwright

STORAGE_FILE = "storage_state.json"


async def login_and_save():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://register.ccopyright.com.cn/login.html")
        print("请手动完成登录，完成后按 Enter...")
        await asyncio.get_event_loop().run_in_executor(None, input)
        await context.storage_state(path=STORAGE_FILE)
        await browser.close()
        print(f"session 已保存到 {STORAGE_FILE}")


async def capture_apis():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(storage_state=STORAGE_FILE)
        page = await context.new_page()

        captured = []

        def on_request(request):
            if "gateway.ccopyright.com.cn" in request.url:
                captured.append({
                    "url": request.url,
                    "method": request.method,
                })

        async def on_response(response):
            if "gateway.ccopyright.com.cn" in response.url:
                try:
                    body = await response.json()
                except Exception:
                    body = None
                print(f"\nAPI: {response.url}")
                if body:
                    print(json.dumps(body, ensure_ascii=False, indent=2)[:500])

        page.on("request", on_request)
        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        await page.goto("https://register.ccopyright.com.cn/account.html?current=soft_register")

        print("请手动操作页面（点待补正 → 查看详情 → 查看补正通知书），完成后按 Enter...")
        await asyncio.get_event_loop().run_in_executor(None, input)

        with open("captured_apis.json", "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        print(f"\n已保存 {len(captured)} 个 API 到 captured_apis.json")

        await browser.close()


async def main():
    if not os.path.exists(STORAGE_FILE):
        print("未找到 storage_state.json，先进行登录...")
        await login_and_save()
    await capture_apis()


asyncio.run(main())
