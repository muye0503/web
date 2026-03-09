from contextlib import asynccontextmanager
from fastapi import FastAPI
from playwright.async_api import async_playwright
import asyncio
import json

USERNAME = "<your_username>"
PASSWORD = "<your_password>"
KEEPALIVE_INTERVAL = 1800  # 30分钟
STORAGE_FILE = "storage_state.json"
async def get_user_id(page):
    user_info = json.loads(await page.evaluate("localStorage.getItem('webUserInfo')"))
    return user_info["id"]

state = {"logged_in": False, "browser": None, "context": None}


async def is_logged_in():
    try:
        page = await state["context"].new_page()
        await page.goto(
            "https://register.ccopyright.com.cn/account.html?current=soft_register",
            timeout=60000, wait_until="domcontentloaded"
        )
        await page.wait_for_timeout(2000)
        result = "login" not in page.url
        await page.close()
        return result
    except Exception:
        return False


async def keepalive_loop():
    while True:
        await asyncio.sleep(KEEPALIVE_INTERVAL)
        if state["context"] and await is_logged_in():
            await state["context"].storage_state(path=STORAGE_FILE)
            print("保活成功")
        else:
            state["logged_in"] = False
            print("session过期，请重新登录")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pw = await async_playwright().start()
    state["browser"] = await pw.chromium.launch(headless=True)
    try:
        state["context"] = await state["browser"].new_context(storage_state=STORAGE_FILE)
        state["logged_in"] = await is_logged_in()
    except Exception:
        state["context"] = await state["browser"].new_context()

    task = asyncio.create_task(keepalive_loop())
    yield
    task.cancel()
    await state["browser"].close()
    await pw.stop()


app = FastAPI(lifespan=lifespan)


@app.post("/login")
async def login():
    """触发人工登录（需有头浏览器环境）"""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()

    await page.goto("https://register.ccopyright.com.cn/login.html")
    await page.wait_for_load_state("networkidle")
    await page.fill('input[type="text"]', USERNAME, timeout=10000)
    await page.fill('input[type="password"]', PASSWORD, timeout=10000)

    await page.wait_for_url(lambda url: "login" not in url, timeout=120000)
    await context.storage_state(path=STORAGE_FILE)

    state["context"] = await state["browser"].new_context(storage_state=STORAGE_FILE)
    state["logged_in"] = True

    await browser.close()
    await pw.stop()
    return {"status": "ok", "message": "登录成功"}


@app.get("/status")
async def status():
    """查询当前登录状态"""
    logged_in = await is_logged_in() if state["context"] else False
    state["logged_in"] = logged_in
    return {"logged_in": logged_in}


@app.get("/query")
async def query(status: str = "FILL", page_num: int = 1, page_size: int = 10):
    """查询项目列表，status: ALL/FILL/AUDIT/ADMIT/MODIFY/DONE/DISTRIBUTE"""
    if not state["context"]:
        return {"error": "未登录"}

    page = await state["context"].new_page()
    await page.goto(
        "https://register.ccopyright.com.cn/account.html?current=soft_register",
        timeout=60000, wait_until="domcontentloaded"
    )
    await page.wait_for_timeout(2000)

    user_info = json.loads(await page.evaluate("localStorage.getItem('webUserInfo')"))
    token = user_info["authorization_token"]
    key = user_info["authorization_key"]
    user_id = user_info["id"]
    await page.close()

    api = f"https://gateway.ccopyright.com.cn/registerQuerySoftServer/userCenter/statusList/{user_id}"
    page = await state["context"].new_page()
    response = await page.request.get(api, params={
        "keyWord": "", "applyDate": "ALL", "status": status,
        "applyType": "", "createUser": user_id,
        "pageNum": str(page_num), "pageSize": str(page_size)
    }, headers={
        "authorization": f"Bearer {token}",
        "authorization_key": key,
        "authorization_token": token,
        "device": "pc"
    })
    data = await response.json()
    await page.close()
    return data
