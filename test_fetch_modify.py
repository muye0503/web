"""测试 fetch_modify 模块"""
import asyncio
import json
from playwright.async_api import async_playwright
from fetch_modify import fetch_all_modify_notices

STORAGE_FILE = "storage_state.json"


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STORAGE_FILE)
        page = await context.new_page()

        # 从 localStorage 取 token
        await page.goto("https://register.ccopyright.com.cn/account.html?current=soft_register",
                        wait_until="domcontentloaded")
        try:
            await page.wait_for_function("localStorage.getItem('webUserInfo') !== null", timeout=10000)
        except Exception:
            pass

        raw = await page.evaluate("localStorage.getItem('webUserInfo')")
        if not raw:
            print("未登录，请先登录")
            return

        user_info = json.loads(raw)
        token = user_info["authorization_token"]
        key = user_info["authorization_key"]
        user_id = user_info["id"]

        results = await fetch_all_modify_notices(page, user_id, token, key)
        print(f"共获取 {len(results)} 条补正通知书")
        for r in results:
            print(f"流水号：{r['flow_number']}")
            print(f"补正原因：{r['content']}")
            print(f"日期：{r['date']}")
            print("---")

        with open("modify_notices.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("结果已保存到 modify_notices.json")

        await browser.close()


asyncio.run(main())
