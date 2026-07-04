"""
钉钉消息推送服务
封装钉钉机器人Webhook和私信API，用于定时任务通知。
"""
import json
import httpx
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("dingtalk")


# ==================== 配置 ====================
# 钉钉机器人Webhook（如需群通知，在此配置）
ROBOT_WEBHOOK_URL = ""  # 留空则不发送群消息

# 钉钉API基础URL
DINGTALK_API_BASE = "https://api.dingtalk.com"

# 老大的钉钉userId
ADMIN_USER_ID = "16381712592737652"


async def send_dingtalk_private(user_id: str, title: str, content: str, access_token: str = "") -> bool:
    """
    通过钉钉API发送工作通知（私信）

    Args:
        user_id: 接收人userId
        title: 通知标题
        content: 通知内容（支持markdown）
        access_token: 钉钉access_token（通过dws工具获取）

    Returns:
        是否发送成功
    """
    if not access_token:
        logger.warning("未配置钉钉access_token，跳过私信发送")
        return False

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            headers = {
                "x-acs-dingtalk-access-token": access_token,
                "Content-Type": "application/json"
            }
            payload = {
                "agent_id": "",  # 可选
                "userid_list": user_id,
                "msg": {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": title,
                        "text": content
                    }
                }
            }
            resp = await client.post(
                f"{DINGTALK_API_BASE}/topapi/message/corpconversation/asyncsend_v2",
                headers=headers,
                json=payload
            )
            if resp.status_code == 200:
                result = resp.json()
                if result.get("errcode") == 0:
                    logger.info(f"钉钉私信发送成功: {title}")
                    return True
                else:
                    logger.error(f"钉钉私信发送失败: {result}")
                    return False
            else:
                logger.error(f"钉钉私信HTTP错误: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.error(f"钉钉私信发送异常: {e}")
        return False


async def send_robot_webhook(text: str, is_markdown: bool = True) -> bool:
    """
    通过钉钉机器人Webhook发送群消息

    Args:
        text: 消息内容
        is_markdown: 是否为markdown格式

    Returns:
        是否发送成功
    """
    if not ROBOT_WEBHOOK_URL:
        logger.warning("未配置机器人Webhook URL，跳过群消息发送")
        return False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            payload = {
                "msgtype": "markdown" if is_markdown else "text",
                "markdown" if is_markdown else "text": {
                    "title": "三星运营通知" if is_markdown else "",
                    "text": text
                }
            }
            resp = await client.post(ROBOT_WEBHOOK_URL, json=payload)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("errcode") == 0:
                    logger.info("机器人Webhook发送成功")
                    return True
            logger.error(f"Webhook发送失败: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Webhook发送异常: {e}")
        return False


def build_sales_report_md(store_reports: list, date_str: str) -> str:
    """
    构建销售日报Markdown文本

    Args:
        store_reports: 门店报告列表 [{store_name, phone_sales, ncme, phone_qty, key_model, accessory, trade_in}]
        date_str: 日期字符串

    Returns:
        Markdown格式文本
    """
    total_phone = sum(r.get("phone_sales", 0) for r in store_reports)
    total_ncme = sum(r.get("ncme", 0) for r in store_reports)
    total_qty = sum(r.get("phone_qty", 0) for r in store_reports)
    total_key = sum(r.get("key_model", 0) for r in store_reports)
    total_acc = sum(r.get("accessory", 0) for r in store_reports)
    total_trade = sum(r.get("trade_in", 0) for r in store_reports)

    lines = [
        f"## 三星体验店日报 ({date_str})\n",
        f"**汇总：手机¥{total_phone:,} / NCME¥{total_ncme:,} / {total_qty}台 / 重点{total_key}台 / 配件¥{total_acc:,} / 回收{total_trade}台**\n",
        "---",
    ]

    for r in store_reports:
        name = r.get("store_name", "未知")
        if not r.get("phone_sales"):
            lines.append(f"- **{name}**：未上报")
            continue
        lines.append(
            f"- **{name}**：手机¥{r['phone_sales']:,} | NCME¥{r['ncme']:,} | "
            f"{r['phone_qty']}台 | 重点{r['key_model']}台 | 配件¥{r['accessory']:,} | 回收{r['trade_in']}台"
        )

    return "\n".join(lines)


def build_inventory_alert_md(alerts: list) -> str:
    """
    构建库存预警Markdown文本

    Args:
        alerts: 预警列表 [{series, message, level}]

    Returns:
        Markdown格式文本
    """
    now = datetime.now().strftime("%m月%d日 %H:%M")
    danger_count = sum(1 for a in alerts if a.get("level") == "danger")
    warn_count = len(alerts) - danger_count

    lines = [
        f"## 库存预警报告 ({now})\n",
        f"共 **{len(alerts)}** 项预警（严重{danger_count} / 警告{warn_count}）\n",
        "---",
    ]

    for a in alerts[:20]:  # 最多显示20条
        icon = "🔴" if a.get("level") == "danger" else "🟡"
        lines.append(f"{icon} {a.get('message', '')}")

    return "\n".join(lines)


def build_price_alert_md(changes: list) -> str:
    """
    构建价格变动Markdown文本

    Args:
        changes: 价格变动列表 [{model_name, spec, platform, old_price, new_price, diff}]

    Returns:
        Markdown格式文本
    """
    now = datetime.now().strftime("%m月%d日 %H:%M")
    if not changes:
        return f"## 价格监控 ({now})\n\n所有监控机型价格无变动。"

    lines = [
        f"## 价格变动通知 ({now})\n",
        f"**{len(changes)}** 项价格变动\n",
        "---",
    ]

    for c in changes[:15]:
        arrow = "↓" if c["diff"] < 0 else "↑"
        lines.append(
            f"- {c['model_name']} {c['spec']} ({c['platform']}): "
            f"¥{c['old_price']} → ¥{c['new_price']} ({arrow}¥{abs(c['diff'])})"
        )

    return "\n".join(lines)
