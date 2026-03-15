import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
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
MONGO_HOST = os.getenv("MONGO_HOST", "localhost:27017")
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS")
if not MONGO_USER or not MONGO_PASS:
    raise ValueError("MONGO_USER 和 MONGO_PASS 环境变量未设置")

# state["accounts"][username] = {"logged_in", "context", "user_info", "lock"}
state = {"browser": None, "accounts": {}}

_mongo_client = None


def get_mongo_db():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(
            host=MONGO_HOST,
            username=MONGO_USER,
            password=MONGO_PASS,
            authSource="admin",
            serverSelectionTimeoutMS=5000
        )
        db = _mongo_client["runzhu"]
        db["accounts"].create_index("username", unique=True)
        db["sessions"].create_index("username", unique=True)
    return _mongo_client["runzhu"]


def get_all_active_accounts():
    try:
        return list(get_mongo_db()["accounts"].find({"active": True}, {"_id": 0}))
    except Exception as e:
        log.error(f"读取账号列表失败：{e}")
        return []


def load_session_from_mongo(username: str):
    try:
        doc = get_mongo_db()["sessions"].find_one({"username": username})
        return doc["session"] if doc else None
    except Exception as e:
        log.error(f"MongoDB 读取 session 失败：{e}")
        return None


def save_session_to_mongo(username: str, session: dict):
    try:
        get_mongo_db()["sessions"].update_one(
            {"username": username},
            {"$set": {"session": session, "updated_at": datetime.now()}},
            upsert=True
        )
    except Exception as e:
        log.error(f"MongoDB 写入 session 失败：{e}")


def get_account_state(username: str) -> dict:
    """获取或初始化账号状态"""
    if username not in state["accounts"]:
        state["accounts"][username] = {
            "logged_in": False,
            "context": None,
            "user_info": None,
            "lock": asyncio.Lock()
        }
    return state["accounts"][username]


async def is_logged_in(username: str):
    acc = get_account_state(username)
    if not acc["context"]:
        return False, None
    try:
        page = await acc["context"].new_page()
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

            if "login" in current_url or not raw:
                return False, None

            user_info = json.loads(raw)
            token = user_info["authorization_token"]
            key = user_info["authorization_key"]
            user_id = user_info["id"]

            # 用真实 API 验证 token 是否有效
            api = f"https://gateway.ccopyright.com.cn/registerQuerySoftServer/userCenter/statusSummary/{user_id}"
            resp = await page.request.get(api, headers={
                "authorization": f"Bearer {token}",
                "authorization_key": key,
                "authorization_token": token,
                "device": "pc"
            })
            result = await resp.json()
            log.info(f"[{username}] is_logged_in: url={current_url}, API returnCode={result.get('returnCode')}")
            if result.get("returnCode") != "SUCCESS":
                return False, None
            return True, user_info
        finally:
            await page.close()

    except Exception as e:
        log.warning(f"[{username}] is_logged_in异常：{e}")
        return False, None


async def reload_context(username: str, session: dict) -> bool:
    """用新 session 替换账号的 context，返回登录状态"""
    acc = get_account_state(username)
    new_context = await state["browser"].new_context(storage_state=session)
    old_context = acc["context"]
    acc["context"] = new_context
    if old_context:
        await old_context.close()
    logged_in, user_info = await is_logged_in(username)
    acc["logged_in"] = logged_in
    acc["user_info"] = user_info
    return logged_in


async def init_account(username: str):
    """初始化单个账号的 context 和登录状态"""
    session = load_session_from_mongo(username)
    acc = get_account_state(username)
    if session:
        acc["context"] = await state["browser"].new_context(storage_state=session)
        logged_in, user_info = await is_logged_in(username)
        acc["logged_in"] = logged_in
        acc["user_info"] = user_info
        log.info(f"[{username}] 初始化完成，登录状态：{'已登录' if logged_in else '未登录'}")
    else:
        acc["context"] = await state["browser"].new_context()
        log.warning(f"[{username}] 无 session，请先登录")


async def keepalive_loop():
    while True:
        interval = random.randint(300, 600)
        log.info(f"下次保活间隔：{interval}秒")
        await asyncio.sleep(interval)

        accounts = get_all_active_accounts()
        for account in accounts:
            username = account["username"]
            acc = get_account_state(username)
            if not acc["context"]:
                continue
            try:
                page = await acc["context"].new_page()
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

                session = await acc["context"].storage_state()
                save_session_to_mongo(username, session)
                acc["user_info"] = user_info
                acc["logged_in"] = True
                log.info(f"[{username}] 保活成功")
            except Exception as e:
                acc["logged_in"] = False
                acc["user_info"] = None
                log.warning(f"[{username}] session过期：{e}，尝试从 MongoDB 重新加载")
                session = load_session_from_mongo(username)
                if session:
                    await reload_context(username, session)
                    if acc["logged_in"]:
                        log.info(f"[{username}] 从 MongoDB 重新加载 session 成功")
                    else:
                        log.warning(f"[{username}] MongoDB 中的 session 也已过期，请重新登录")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pw = await async_playwright().start()
    state["browser"] = await pw.chromium.launch(headless=True)

    accounts = get_all_active_accounts()
    if not accounts:
        log.warning("数据库中无账号，请通过 POST /accounts 添加账号")
    for account in accounts:
        await init_account(account["username"])

    task = asyncio.create_task(keepalive_loop())
    yield
    task.cancel()
    for acc in state["accounts"].values():
        if acc["context"]:
            await acc["context"].close()
    await state["browser"].close()
    await pw.stop()


app = FastAPI(lifespan=lifespan)


# ── 账号管理 ──

class AccountPayload(BaseModel):
    username: str


@app.post("/accounts")
async def add_account(payload: AccountPayload):
    """添加账号"""
    try:
        get_mongo_db()["accounts"].update_one(
            {"username": payload.username},
            {"$set": {"username": payload.username, "active": True}},
            upsert=True
        )
        await init_account(payload.username)
        return {"status": "ok", "username": payload.username}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/accounts/{username}")
async def delete_account(username: str):
    """删除账号"""
    try:
        get_mongo_db()["accounts"].update_one(
            {"username": username}, {"$set": {"active": False}}
        )
        acc = state["accounts"].pop(username, None)
        if acc and acc["context"]:
            await acc["context"].close()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/accounts")
async def list_accounts():
    """查看所有账号状态"""
    accounts = get_all_active_accounts()
    usernames = [a["username"] for a in accounts]
    session_docs = {
        d["username"]: d for d in get_mongo_db()["sessions"].find(
            {"username": {"$in": usernames}},
            {"username": 1, "updated_at": 1, "_id": 0}
        )
    }
    result = []
    for account in accounts:
        username = account["username"]
        acc = state["accounts"].get(username, {})
        doc = session_docs.get(username)
        updated_at = doc["updated_at"].strftime("%Y-%m-%d %H:%M:%S") if doc and doc.get("updated_at") else None
        result.append({
            "username": username,
            "logged_in": acc.get("logged_in", False),
            "session_updated_at": updated_at
        })
    return result


# ── session 管理 ──

class SessionPayload(BaseModel):
    username: str
    session: dict


@app.post("/upload-session")
async def upload_session(payload: SessionPayload):
    """接收客户机上传的 session"""
    try:
        save_session_to_mongo(payload.username, payload.session)
        # 自动同步 accounts 记录
        get_mongo_db()["accounts"].update_one(
            {"username": payload.username},
            {"$setOnInsert": {"username": payload.username, "active": True}},
            upsert=True
        )
        await reload_context(payload.username, payload.session)
        return {"status": "ok", "logged_in": state["accounts"].get(payload.username, {}).get("logged_in", False)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reload-session/{username}")
async def reload_session(username: str):
    """从 MongoDB 重新加载 session"""
    try:
        session = load_session_from_mongo(username)
        if not session:
            return {"error": "MongoDB 中无 session，请先登录"}
        logged_in = await reload_context(username, session)
        return {"status": "ok", "logged_in": logged_in}
    except Exception as e:
        return {"error": str(e)}


# ── 业务接口 ──

@app.get("/")
async def index():
    return FileResponse("index.html")


@app.get("/status")
async def status(username: str):
    acc = state["accounts"].get(username)
    if not acc:
        return {"username": username, "logged_in": False}
    return {"username": username, "logged_in": acc["logged_in"]}


@app.get("/query")
async def query(username: str, status: str = "FILL", page_num: int = 1, page_size: int = 10):
    """查询项目列表"""
    acc = state["accounts"].get(username)
    if not acc or not acc["context"]:
        return {"error": f"账号 {username} 未登录"}

    if not acc["user_info"]:
        async with acc["lock"]:
            if not acc["user_info"]:
                logged_in, user_info = await is_logged_in(username)
                if not logged_in:
                    return {"error": "session已过期，请重新登录"}
                acc["logged_in"] = True
                acc["user_info"] = user_info

    user_info = acc["user_info"]
    token = user_info["authorization_token"]
    key = user_info["authorization_key"]
    user_id = user_info["id"]

    api = f"https://gateway.ccopyright.com.cn/registerQuerySoftServer/userCenter/statusList/{user_id}"
    page = await acc["context"].new_page()
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
        log.error(f"[{username}] API 请求失败：{e}")
        return {"error": "查询失败，请稍后重试"}
    finally:
        await page.close()
    return data
