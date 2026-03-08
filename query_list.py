from playwright.sync_api import sync_playwright
import json

USER_ID = "830815867913814016"
API = f"https://gateway.ccopyright.com.cn/registerQuerySoftServer/userCenter/statusList/{USER_ID}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state="storage_state.json")
    page = context.new_page()

    page.goto("https://register.ccopyright.com.cn/account.html?current=soft_register",
              timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 从webUserInfo中取token
    user_info = json.loads(page.evaluate("localStorage.getItem('webUserInfo')"))
    token = user_info["authorization_token"]
    key = user_info["authorization_key"]

    response = page.request.get(API, params={
        "keyWord": "",
        "applyDate": "ALL",
        "status": "FILL",
        "applyType": "",
        "createUser": USER_ID,
        "pageNum": "1",
        "pageSize": "10"
    }, headers={
        "authorization": f"Bearer {token}",
        "authorization_key": key,
        "authorization_token": token,
        "device": "pc"
    })

    data = response.json()
    items = data["data"]["list"]
    print(f"待提交项目数：{data['data']['paging']['total']}")
    for item in items:
        print(f"- 申请人：{item.get('applyPeople')}  状态：{item.get('status')}  软件名：{item.get('softName', '')}")

    browser.close()
