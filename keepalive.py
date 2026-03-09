from playwright.sync_api import sync_playwright
import time

USERNAME = "<your_username>"
PASSWORD = "<your_password>"
KEEPALIVE_INTERVAL = 1800  # 每30分钟保活一次


def login(context):
    page = context.new_page()
    page.goto("https://register.ccopyright.com.cn/login.html")
    page.wait_for_load_state("networkidle")
    page.fill('input[type="text"]', USERNAME, timeout=10000)
    page.fill('input[type="password"]', PASSWORD, timeout=10000)
    print("请手动完成验证码并点击登录...")
    page.wait_for_url(lambda url: "login" not in url, timeout=120000)
    context.storage_state(path="storage_state.json")
    print("登录成功，已保存 storage_state.json")
    page.close()


def is_logged_in(page):
    page.goto("https://register.ccopyright.com.cn/account.html?current=soft_register",
              timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    return "login" not in page.url


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(storage_state="storage_state.json")

    # 验证初始登录状态
    page = context.new_page()
    if not is_logged_in(page):
        print("session已过期，重新登录...")
        page.close()
        context = browser.new_context()
        login(context)
    else:
        print("session有效，开始保活...")
        page.close()

    # 保活循环
    while True:
        time.sleep(KEEPALIVE_INTERVAL)
        page = context.new_page()
        if is_logged_in(page):
            context.storage_state(path="storage_state.json")
            print("保活成功，已更新 storage_state.json")
        else:
            print("session过期，重新登录...")
            page.close()
            context = browser.new_context()
            login(context)
            continue
        page.close()
