from fastapi import FastAPI
from fastapi.responses import FileResponse
from pymongo import MongoClient
from playwright.async_api import async_playwright
from datetime import datetime
import asyncio
import os

app = FastAPI()

MONGO_URI = os.getenv("MONGO_URI")
USERNAME = os.getenv("APP_USERNAME")
PASSWORD = os.getenv("APP_PASSWORD")

if not MONGO_URI or not USERNAME or not PASSWORD:
    raise ValueError("MONGO_URI、APP_USERNAME、APP_PASSWORD 环境变量均需设置")

login_status = {"running": False, "message": "未登录"}

# 修复3：MongoDB 单例
_mongo_client = None

def get_mongo_db():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _mongo_client["runzhu"]["sessions"].create_index("username", unique=True)
    return _mongo_client["runzhu"]


def _save_session(session: dict):
    get_mongo_db()["sessions"].update_one(
        {"username": USERNAME},
        {"$set": {"session": session, "updated_at": datetime.now()}},
        upsert=True
    )


async def do_login():
    login_status["running"] = True
    login_status["message"] = "正在打开登录页..."
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto("https://register.ccopyright.com.cn/login.html")
                await page.wait_for_load_state("networkidle")
                login_status["message"] = "正在填写账号密码..."
                await page.fill('input[type="text"]', USERNAME)
                await page.fill('input[type="password"]', PASSWORD)
                login_status["message"] = "请在浏览器中完成验证码（2分钟内）..."
                await page.wait_for_url(lambda url: "login" not in url, timeout=120000)
                login_status["message"] = "登录成功，正在上传 session..."
                session = await context.storage_state()
            finally:
                await browser.close()

        # 修复2：同步 MongoDB 操作放到线程池，不阻塞事件循环
        await asyncio.to_thread(_save_session, session)
        login_status["message"] = f"✅ session 已上传：{USERNAME}"
    except Exception as e:
        login_status["message"] = f"❌ 登录失败：{e}"
    finally:
        login_status["running"] = False


@app.get("/")
async def index():
    return FileResponse("client.html")


@app.get("/status")
async def status():
    try:
        doc = get_mongo_db()["sessions"].find_one({"username": USERNAME})
        updated_at = doc["updated_at"].strftime("%Y-%m-%d %H:%M:%S") if doc else None
    except Exception:
        updated_at = None
    return {
        "username": USERNAME,
        "session_updated_at": updated_at,
        "login_running": login_status["running"],
        "message": login_status["message"]
    }


@app.post("/login")
async def login():
    if login_status["running"]:
        return {"error": "登录已在进行中"}
    asyncio.create_task(do_login())
    return {"message": "登录已触发，请在弹出的浏览器中完成验证码"}
