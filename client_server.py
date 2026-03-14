from fastapi import FastAPI
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright
import asyncio
import httpx
import os

app = FastAPI()

SERVER_URL = os.getenv("SERVER_URL")  # 服务端地址，如 http://服务器IP:8000
USERNAME = os.getenv("APP_USERNAME")
PASSWORD = os.getenv("APP_PASSWORD")

if not SERVER_URL or not USERNAME or not PASSWORD:
    raise ValueError("SERVER_URL、APP_USERNAME、APP_PASSWORD 环境变量均需设置")

login_status = {"running": False, "message": "未登录"}


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

        # 上传 session 到服务端 API
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SERVER_URL}/upload-session",
                json={"username": USERNAME, "session": session},
                timeout=30
            )
            resp.raise_for_status()
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
    # 从服务端查询登录状态
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{SERVER_URL}/status", timeout=10)
            server_status = resp.json()
    except Exception:
        server_status = {"logged_in": None}
    return {
        "username": USERNAME,
        "server_logged_in": server_status.get("logged_in"),
        "login_running": login_status["running"],
        "message": login_status["message"]
    }


@app.post("/login")
async def login():
    if login_status["running"]:
        return {"error": "登录已在进行中"}
    asyncio.create_task(do_login())
    return {"message": "登录已触发，请在弹出的浏览器中完成验证码"}
