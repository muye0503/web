from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()

    cookies = json.load(open('cookies.json'))
    context.add_cookies(cookies)

    page = context.new_page()
    page.goto("https://register.ccopyright.com.cn/account.html?current=soft_register")
    page.wait_for_load_state("networkidle")

    if "login" in page.url:
        print("❌ cookies已失效，需要重新登录")
    else:
        print("✅ cookies有效，当前页面：", page.url)

    browser.close()
