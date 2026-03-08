from playwright.sync_api import sync_playwright

USER_ID = "830815867913814016"
API = f"https://gateway.ccopyright.com.cn/registerQuerySoftServer/userCenter/statusList/{USER_ID}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state="storage_state.json")
    page = context.new_page()

    # 先访问主页建立session
    page.goto("https://register.ccopyright.com.cn/account.html?current=soft_register")
    page.wait_for_load_state("networkidle")

    # 查询待提交列表（status=FILL 表示待提交）
    response = page.request.get(API, params={
        "keyWord": "",
        "applyDate": "ALL",
        "status": "FILL",
        "applyType": "",
        "createUser": USER_ID,
        "pageNum": "1",
        "pageSize": "10"
    })

    data = response.json()
    items = data["data"]["list"]
    print(f"待提交项目数：{data['data']['paging']['total']}")
    for item in items:
        print(f"- 申请人：{item.get('applyPeople')}  状态：{item.get('status')}  ID：{item.get('createUser')}")

    browser.close()
