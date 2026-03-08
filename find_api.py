from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(storage_state="storage_state.json")
    page = context.new_page()

    # 拦截网络请求，找到列表查询API
    api_calls = []
    def handle_response(response):
        if "json" in response.headers.get("content-type", "") and "ccopyright" in response.url:
            try:
                body = response.json()
                api_calls.append({"url": response.url, "body": body})
                print(f"API: {response.url}")
                print(json.dumps(body, ensure_ascii=False, indent=2)[:500])
                print("---")
            except:
                pass

    page.on("response", handle_response)

    page.goto("https://register.ccopyright.com.cn/account.html?current=soft_register")
    page.wait_for_load_state("networkidle")

    input("按回车退出...")
    browser.close()
