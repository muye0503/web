from playwright.sync_api import sync_playwright

USERNAME = "<your_username>"
PASSWORD = "<your_password>"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    page.goto("https://register.ccopyright.com.cn/login.html")
    page.wait_for_load_state("networkidle")

    page.fill('input[type="text"]', USERNAME, timeout=10000)
    page.fill('input[type="password"]', PASSWORD, timeout=10000)

    print("请手动完成验证码并点击登录...")
    page.wait_for_url(lambda url: "login" not in url, timeout=120000)

    # 保存完整浏览器状态（包含Session cookie）
    context.storage_state(path="storage_state.json")
    print("已保存到 storage_state.json")

    browser.close()
