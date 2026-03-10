import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright
import asyncio
import json
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

from dotenv import load_dotenv
import os
load_dotenv()
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
KEEPALIVE_INTERVAL = 300  # 先用5分钟测试，确认session不过期后再调大
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
        log.info(f"保活检查（间隔{KEEPALIVE_INTERVAL}秒）...")
        if state["context"] and await is_logged_in():
            await state["context"].storage_state(path=STORAGE_FILE)
            log.info("保活成功，session有效")
        else:
            state["logged_in"] = False
            log.warning("session已过期，请重新登录")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pw = await async_playwright().start()
    state["browser"] = await pw.chromium.launch(headless=True)
    try:
        state["context"] = await state["browser"].new_context(storage_state=STORAGE_FILE)
        state["logged_in"] = await is_logged_in()
        log.info(f"启动完成，登录状态：{'已登录' if state['logged_in'] else '未登录'}")
    except Exception:
        state["context"] = await state["browser"].new_context()
        log.warning("storage_state.json 不存在或无效，需要先登录")

    task = asyncio.create_task(keepalive_loop())
    yield
    task.cancel()
    await state["browser"].close()
    await pw.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse("index.html")


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
