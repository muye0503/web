from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(storage_state="storage_state.json")
    page = context.new_page()

    def handle_request(request):
        if "statusList" in request.url:
            print("URL:", request.url)
            print("Headers:", request.headers)

    page.on("request", handle_request)

    page.goto("https://register.ccopyright.com.cn/account.html?current=soft_register")
    page.wait_for_load_state("networkidle")

    input("按回车退出...")
    browser.close()
