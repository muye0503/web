"""
补正通知书抓取模块
使用方式：
    from fetch_modify import fetch_all_modify_notices
    results = await fetch_all_modify_notices(page, user_id, token, key)
"""
import logging

log = logging.getLogger(__name__)

BASE = "https://gateway.ccopyright.com.cn"


def _headers(token: str, key: str) -> dict:
    return {
        "authorization": f"Bearer {token}",
        "authorization_key": key,
        "authorization_token": token,
        "device": "pc"
    }


async def _get(page, url: str, token: str, key: str, params: dict = None) -> dict:
    resp = await page.request.get(url, headers=_headers(token, key), params=params or {})
    return await resp.json()


async def fetch_all_modify_notices(page, user_id: str, token: str, key: str) -> list[dict]:
    """
    遍历所有待补正条目，获取补正通知书内容
    返回：[{flow_number, advice_id, content, date}, ...]
    """
    results = []
    page_num = 1

    while True:
        # 1. 获取待补正列表（分页）
        data = await _get(page, f"{BASE}/registerQuerySoftServer/userCenter/statusList/{user_id}",
                          token, key, {
                              "keyWord": "", "applyDate": "ALL", "status": "MODIFY",
                              "applyType": "", "createUser": user_id,
                              "pageNum": str(page_num), "pageSize": "10"
                          })

        if data.get("returnCode") != "SUCCESS":
            log.error(f"获取列表失败：{data.get('msg')}")
            break

        items = data.get("data", {}).get("list", [])
        total = data.get("data", {}).get("paging", {}).get("total", 0)

        if not items:
            break

        for item in items:
            flow_number = item.get("flowNumber")
            if not flow_number:
                continue

            # 2. 获取补正通知书 ID
            handle_data = await _get(page,
                f"{BASE}/registerQuerySoftServer/userCenter/flowNumberHandle/{user_id}/{flow_number}",
                token, key)

            if handle_data.get("returnCode") != "SUCCESS":
                log.warning(f"[{flow_number}] 获取 handle 失败：{handle_data.get('msg')}")
                continue

            # 从 handle 数据里找补正通知书 ID
            handle_list = handle_data.get("data", [])
            advice_id = None
            for h in handle_list:
                if "Modify" in str(h.get("handleCode", "")):
                    advice_id = h.get("handleCode")
                    break

            if not advice_id:
                log.warning(f"[{flow_number}] 未找到补正通知书 ID")
                continue

            # 3. 获取补正通知书内容
            notice_data = await _get(page,
                f"{BASE}/registerQuerySoftServer/userCenter/searchAdviceNote/{user_id}/{advice_id}",
                token, key)

            if notice_data.get("returnCode") != "SUCCESS":
                log.warning(f"[{flow_number}] 获取通知书失败：{notice_data.get('msg')}")
                continue

            notice = notice_data.get("data", {})
            results.append({
                "flow_number": flow_number,
                "advice_id": advice_id,
                "content": notice.get("content") or notice.get("adviceContent"),
                "date": notice.get("date") or notice.get("createTime"),
                "raw": notice
            })
            log.info(f"[{flow_number}] 获取补正通知书成功")

        # 判断是否还有下一页
        if page_num * 10 >= total:
            break
        page_num += 1

    return results
