import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright
from pymongo import MongoClient
from datetime import datetime
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
if not USERNAME:
    raise ValueError("APP_USERNAME 环境变量未设置")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

state = {"logged_in": False, "browser": None, "context": None, "user_info": None}

_mongo_client = None
_login_lock: asyncio.Lock | None = None


def get_login_lock() -> asyncio.Lock:
    global _login_lock
    if _login_lock is None:
        _login_lock = asyncio.Lock()
    return _login_lock


def get_mongo_db():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return _mongo_client["wraxl"]


def load_session_from_mongo(username: str):
    try:
        doc = get_mongo_db()["sessions"].find_one({"username": username})
        return doc["session"] if doc else None
    except Exception as e:
        log.error(f"MongoDB 读取失败：{e}")
        return None


def save_session_to_mongo(username: str, session: dict):
    try:
        get_mongo_db()["sessions"].update_one(
            {"username": username},
            {"$set": {"session": session, "updated_at": datetime.now()}},
            upsert=True
        )
    except Exception as e:
        log.error(f"MongoDB 写入失败：{e}")


async def is_logged_in():
    try:
        page = await state["context"].new_page()
        try:
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
        finally:
            await page.close()

        log.info(f"is_logged_in: url={current_url}, webUserInfo={'有' if raw else '无'}")
        if "login" in current_url or not raw:
            return False, None
        return True, json.loads(raw)
    except Exception as e:
        log.warning(f"is_logged_in异常：{e}")
        return False, None


async def keepalive_loop():
    while True:
        interval = random.randint(60, 300)
        log.info(f"下次保活间隔：{interval}秒")
        await asyncio.sleep(interval)
        if not state["context"]:
            continue
        try:
            page = await state["context"].new_page()
            try:
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

                api = f"https://gateway.ccopyright.com.cn/registerQuerySoftServer/userCenter/statusSummary/{user_id}"
                resp = await page.request.get(api, headers={
                    "authorization": f"Bearer {token}",
                    "authorization_key": key,
                    "authorization_token": token,
                    "device": "pc"
                })
                result = await resp.json()
                if result.get("returnCode") != "SUCCESS":
                    raise Exception(f"API返回：{result.get('msg')}")
            finally:
                await page.close()

            session = await state["context"].storage_state()
            save_session_to_mongo(USERNAME, session)
            state["user_info"] = user_info
            state["logged_in"] = True
            log.info("保活成功，session有效")
        except Exception as e:
            state["logged_in"] = False
            state["user_info"] = None
            log.warning(f"session已过期：{e}，尝试从 MongoDB 重新加载")
            session = load_session_from_mongo(USERNAME)
            if session:
                new_context = await state["browser"].new_context(storage_state=session)
                old_context = state["context"]
                state["context"] = new_context
                if old_context:
                    await old_context.close()
                logged_in, user_info = await is_logged_in()
                state["logged_in"] = logged_in
                state["user_info"] = user_info
                if logged_in:
                    log.info("从 MongoDB 重新加载 session 成功")
                else:
                    log.warning("MongoDB 中的 session 也已过期，请重新运行 client_login.py")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pw = await async_playwright().start()
    state["browser"] = await pw.chromium.launch(headless=True)

    session = load_session_from_mongo(USERNAME)
    if session:
        state["context"] = await state["browser"].new_context(storage_state=session)
        logged_in, user_info = await is_logged_in()
        state["logged_in"] = logged_in
        state["user_info"] = user_info
        log.info(f"启动完成，登录状态：{'已登录' if logged_in else '未登录'}")
    else:
        state["context"] = await state["browser"].new_context()
        log.warning("MongoDB 中无 session，请先在客户机运行 client_login.py")

    task = asyncio.create_task(keepalive_loop())
    yield
    task.cancel()
    await state["browser"].close()
    await pw.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse("index.html")


@app.get("/status")
async def status():
    return {"logged_in": state["logged_in"]}


@app.post("/reload-session")
async def reload_session():
    """从 MongoDB 重新加载 session（客户机重新登录后调用）"""
    try:
        session = load_session_from_mongo(USERNAME)
        if not session:
            return {"error": "MongoDB 中无 session，请先运行 client_login.py"}
        new_context = await state["browser"].new_context(storage_state=session)
        old_context = state["context"]
        state["context"] = new_context
        if old_context:
            await old_context.close()
        logged_in, user_info = await is_logged_in()
        state["logged_in"] = logged_in
        state["user_info"] = user_info
        return {"status": "ok", "logged_in": logged_in}
    except Exception as e:
        return {"error": str(e)}


@app.get("/query")
async def query(status: str = "FILL", page_num: int = 1, page_size: int = 10):
    """查询项目列表，status: ALL/FILL/AUDIT/ADMIT/MODIFY/DONE/DISTRIBUTE"""
    if not state["user_info"]:
        if not state["context"]:
            return {"error": "未登录"}
        async with get_login_lock():
            if not state["user_info"]:
                logged_in, user_info = await is_logged_in()
                if not logged_in:
                    return {"error": "session已过期，请重新登录"}
                state["logged_in"] = True
                state["user_info"] = user_info

    user_info = state["user_info"]
    token = user_info["authorization_token"]
    key = user_info["authorization_key"]
    user_id = user_info["id"]

    api = f"https://gateway.ccopyright.com.cn/registerQuerySoftServer/userCenter/statusList/{user_id}"
    page = await state["context"].new_page()
    try:
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
    except Exception as e:
        log.error(f"API 请求失败：{e}")
        return {"error": "查询失败，请稍后重试"}
    finally:
        await page.close()
    return data
