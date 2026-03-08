# login.py
from playwright.sync_api import sync_playwright
import json

USERNAME = "<your_username>"
PASSWORD = "<your_password>"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    page.goto("https://register.ccopyright.com.cn/login.html")
    page.wait_for_load_state("networkidle")

    # 自动填入账号密码（Vue应用需用fill+delay模拟真实输入）
    # 先尝试常见选择器，按实际页面调整
    page.fill('input[type="text"]', USERNAME, timeout=10000)
    page.fill('input[type="password"]', PASSWORD, timeout=10000)

    print("账号密码已填入，请手动完成验证码，然后点击登录按钮...")
    print("等待页面跳转（最多2分钟）...")

    # 等待人工完成验证码并点击登录，检测到URL变化即成功
    page.wait_for_url(lambda url: "login" not in url, timeout=120000)

    print("登录成功！保存cookies...")
    cookies = context.cookies()
    with open("cookies.json", "w") as f:
        json.dump(cookies, f)
    print("cookies已保存到 cookies.json")

    input("按回车关闭浏览器...")
    browser.close()
