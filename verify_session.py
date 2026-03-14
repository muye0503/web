import asyncio
import json
from playwright.async_api import async_playwright

async def verify():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(storage_state="storage_state.json")
        page = await context.new_page()

        # 访问登录后才能看到的页面
        await page.goto(
            "https://register.ccopyright.com.cn/account.html?current=soft_register",
            timeout=30000, wait_until="domcontentloaded"
        )

        try:
            await page.wait_for_function(
                "localStorage.getItem('webUserInfo') !== null", timeout=10000
            )
        except:
            pass

        current_url = page.url
        raw = await page.evaluate("localStorage.getItem('webUserInfo')")

        print(f"当前URL: {current_url}")
        print(f"webUserInfo: {'有效' if raw else '无效/为空'}")

        if raw:
            user_info = json.loads(raw)
            token = user_info["authorization_token"]
            key = user_info["authorization_key"]
            user_id = user_info["id"]

            resp = await page.request.get(
                f"https://gateway.ccopyright.com.cn/registerQuerySoftServer/userCenter/statusSummary/{user_id}",
                headers={
                    "authorization": f"Bearer {token}",
                    "authorization_key": key,
                    "authorization_token": token,
                    "device": "pc"
                }
            )
            result = await resp.json()
            print(f"API返回: {result.get('returnCode')} - {result.get('msg', '')}")

        await browser.close()

asyncio.run(verify())
