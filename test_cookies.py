from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    # 加载完整浏览器状态
    context = browser.new_context(storage_state="storage_state.json")
    page = context.new_page()
    page.goto("https://register.ccopyright.com.cn/")
    page.wait_for_load_state("networkidle")

    if "login" in page.url:
        print("❌ 已失效，需要重新登录")
    else:
        print("✅ 有效，当前页面：", page.url)

    browser.close()
