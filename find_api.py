from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state="storage_state.json")
    page = context.new_page()

    page.goto("https://register.ccopyright.com.cn/account.html?current=soft_register")
    page.wait_for_load_state("networkidle")

    # 打印所有localStorage内容
    storage = page.evaluate("JSON.stringify(localStorage)")
    print("localStorage:", storage)

    browser.close()
