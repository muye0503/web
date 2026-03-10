import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright
import json
import logging
import os
import random

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

load_dotenv()
USERNAME = os.getenv("APP_USERNAME")
PASSWORD = os.getenv("APP_PASSWORD")
STORAGE_FILE = "storage_state.json"

state = {"logged_in": False, "browser": None, "context": None}


async def is_logged_in():
    try:
        page = await state["context"].new_page()
        await page.goto(
            "https://register.ccopyright.com.cn/account.html?current=soft_register",
            timeout=60000, wait_until="domcontentloaded"
        )
        try:
            await page.wait_for_function(
                "localStorage.getItem('webUserInfo') !== null", timeout=10000
            )
        except Exception:
            pass
        current_url = page.url
        raw = await page.evaluate("localStorage.getItem('webUserInfo')")
        await page.close()
        log.info(f"is_logged_in: url={current_url}, webUserInfo={'有' if raw else '无'}")
        return raw is not None
    except Exception as e:
        log.warning(f"is_logged_in异常：{e}")
        return False


async def keepalive_loop():
    while True:
        interval = random.randint(60, 300)  # 1-5分钟随机
        log.info(f"下次保活间隔：{interval}秒")
        await asyncio.sleep(interval)
        if not state["context"]:
            continue
        try:
            page = await state["context"].new_page()
            await page.goto(
                "https://register.ccopyright.com.cn/account.html?current=soft_register",
                timeout=60000, wait_until="domcontentloaded"
            )
            await page.wait_for_timeout(2000)
            raw = await page.evaluate("localStorage.getItem('webUserInfo')")
            if not raw:
                raise Exception("webUserInfo为空")
            user_info = json.loads(raw)
            token = user_info["authorization_token"]
            key = user_info["authorization_key"]
            user_id = user_info["id"]

            # 主动调用API续期session
            api = f"https://gateway.ccopyright.com.cn/registerQuerySoftServer/userCenter/statusSummary/{user_id}"
            resp = await page.request.get(api, headers={
                "authorization": f"Bearer {token}",
                "authorization_key": key,
                "authorization_token": token,
                "device": "pc"
            })
            result = await resp.json()
            await page.close()
            if result.get("returnCode") != "SUCCESS":
                raise Exception(f"API返回：{result.get('msg')}")
            await state["context"].storage_state(path=STORAGE_FILE)
            state["logged_in"] = True
            log.info("保活成功，session有效")
        except Exception as e:
            state["logged_in"] = False
            log.warning(f"session已过期：{e}，请重新登录")


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
    if state["context"]:
        state["logged_in"] = await is_logged_in()
    return {"logged_in": state["logged_in"]}


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
    # 等待Vue应用初始化并写入webUserInfo，最多等10秒
    try:
        await page.wait_for_function(
            "localStorage.getItem('webUserInfo') !== null",
            timeout=10000
        )
    except Exception:
        log.warning("等待webUserInfo超时")

    raw = await page.evaluate("localStorage.getItem('webUserInfo')")
    log.info(f"webUserInfo: {raw[:100] if raw else 'None'}")
    await page.close()
    if not raw:
        state["logged_in"] = False
        return {"error": "session已过期，请重新登录"}

    user_info = json.loads(raw)
    token = user_info["authorization_token"]
    key = user_info["authorization_key"]
    user_id = user_info["id"]

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
