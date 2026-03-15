from fastapi import FastAPI
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright
from dotenv import load_dotenv
import asyncio
import httpx
import csv
import os

load_dotenv()
app = FastAPI()

SERVER_URL = os.getenv("SERVER_URL")
ACCOUNTS_FILE = os.getenv("ACCOUNTS_FILE", "accounts.csv")

if not SERVER_URL:
    raise ValueError("SERVER_URL 环境变量未设置")


def load_accounts() -> list[dict]:
    """从 CSV 读取账号列表，格式：username,password"""
    if not os.path.exists(ACCOUNTS_FILE):
        raise FileNotFoundError(f"账号文件不存在：{ACCOUNTS_FILE}")
    with open(ACCOUNTS_FILE, newline="", encoding="utf-8-sig") as f:
        try:
            return list(csv.DictReader(f))
        except UnicodeDecodeError:
            pass
    with open(ACCOUNTS_FILE, newline="", encoding="gbk") as f:
        return list(csv.DictReader(f))


def get_account(username: str) -> dict | None:
    for acc in load_accounts():
        if acc["username"] == username:
            return acc
    return None


login_tasks: dict[str, dict] = {}  # username -> {running, message}


async def do_login(username: str, password: str, account_type: str = "个人用户"):
    login_tasks[username] = {"running": True, "message": "正在打开登录页..."}
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto("https://register.ccopyright.com.cn/login.html")
                await page.wait_for_selector('input[type="text"]')
                # 选择账号类型
                await page.get_by_text(account_type, exact=True).click()
                login_tasks[username]["message"] = "正在填写账号密码..."
                await page.fill('input[type="text"]', username)
                await page.fill('input[type="password"]', password)
                login_tasks[username]["message"] = "请在浏览器中完成验证码（2分钟内）..."
                await page.wait_for_url(lambda url: "login" not in url, timeout=120000)
                login_tasks[username]["message"] = "登录成功，正在上传 session..."
                session = await context.storage_state()
            finally:
                await browser.close()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SERVER_URL}/upload-session",
                json={"username": username, "session": session},
                timeout=30
            )
            resp.raise_for_status()
        login_tasks[username]["message"] = f"✅ session 已上传：{username}"
    except Exception as e:
        login_tasks[username]["message"] = f"❌ 登录失败：{e}"
    finally:
        login_tasks[username]["running"] = False


@app.get("/")
async def index():
    return FileResponse("client.html")


@app.get("/accounts")
async def list_accounts():
    """返回本地 CSV 中的账号列表及登录状态"""
    try:
        accounts = load_accounts()
    except FileNotFoundError as e:
        return {"error": str(e)}

    result = []
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{SERVER_URL}/accounts", timeout=5)
            server_accounts = {a["username"]: a for a in resp.json()}
        except Exception:
            server_accounts = {}

        for acc in accounts:
            username = acc["username"]
            server = server_accounts.get(username, {})
            task = login_tasks.get(username, {})
            result.append({
                "username": username,
                "server_logged_in": server.get("logged_in"),
                "session_updated_at": server.get("session_updated_at"),
                "login_running": task.get("running", False),
                "message": task.get("message", "")
            })
    return result


@app.post("/login/{username}")
async def login(username: str):
    acc = get_account(username)
    if not acc:
        return {"error": f"账号 {username} 不在 CSV 文件中"}
    task = login_tasks.get(username, {})
    if task.get("running"):
        return {"error": "登录已在进行中"}
    asyncio.create_task(do_login(username, acc["password"], acc.get("account_type", "个人用户")))
    return {"message": f"登录已触发：{username}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5001)
