"""通知 API"""
from fastapi import APIRouter, HTTPException, Depends
from backend.models.database import get_db
from backend.dependencies import get_current_user, require_admin, require_manager_or_admin

router = APIRouter()


@router.get("/scheduler-status")
async def get_scheduler_status(user: dict = Depends(require_admin)):
    """获取定时任务调度器状态（管理员）"""
    try:
        from backend.services.scheduler_service import get_scheduler_info
        return get_scheduler_info()
    except Exception as e:
        return {"running": False, "jobs": [], "error": str(e)}


@router.get("/list")
async def get_notifications(unread_only: int = 0, user: dict = Depends(get_current_user)):
    """获取通知列表"""
    db = await get_db()
    if user["role"] == "admin":
        if unread_only:
            cursor = await db.execute(
                "SELECT * FROM notifications WHERE is_read=0 ORDER BY created_at DESC LIMIT 50")
        else:
            cursor = await db.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 100")
    else:
        if unread_only:
            cursor = await db.execute(
                "SELECT * FROM notifications WHERE (user_id=? OR user_id IS NULL) AND is_read=0 ORDER BY created_at DESC LIMIT 50",
                (user["user_id"],))
        else:
            cursor = await db.execute(
                "SELECT * FROM notifications WHERE (user_id=? OR user_id IS NULL) ORDER BY created_at DESC LIMIT 100",
                (user["user_id"],))

    notifications = await cursor.fetchall()
    return [dict(n) for n in notifications]


@router.post("/read/{notification_id}")
async def mark_read(notification_id: int, user: dict = Depends(get_current_user)):
    """标记通知已读"""
    db = await get_db()
    await db.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notification_id,))
    await db.commit()
    return {"status": "ok"}


@router.get("/unread-count")
async def get_unread_count(user: dict = Depends(get_current_user)):
    """获取未读通知数（通过 Authorization: Bearer 认证）"""
    db = await get_db()
    if user["role"] == "admin":
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM notifications WHERE is_read=0")
    else:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE (user_id=? OR user_id IS NULL) AND is_read=0",
            (user["user_id"],))
    count = await cursor.fetchone()
    return {"count": count["cnt"]}


@router.post("/send")
async def send_notification(
    user_id: int = None,
    title: str = "",
    content: str = "",
    notify_type: str = "info",
    user: dict = Depends(require_admin)
):
    """发送通知（管理员）"""
    db = await get_db()
    await db.execute(
        "INSERT INTO notifications (user_id, title, content, type) VALUES (?,?,?,?)",
        (user_id, title, content, notify_type)
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/check-inventory")
async def check_inventory_alerts(user: dict = Depends(require_manager_or_admin)):
    """执行库存预警检查，将预警写入通知表（admin手动触发或定时调用）"""
    alerts_data = await _get_inventory_alerts()

    db = await get_db()
    created = 0
    for a in alerts_data[:20]:
        cursor = await db.execute(
            "SELECT id FROM notifications WHERE type='inventory' AND content LIKE ? AND created_at > datetime('now', '-1 hour')",
            (f"%{a['message']}%",)
        )
        existing = await cursor.fetchone()
        if existing:
            continue

        await db.execute(
            "INSERT INTO notifications (title, content, type) VALUES (?,?,?)",
            (f"库存预警：{a['series']}", a["message"], "inventory")
        )
        created += 1

    await db.commit()
    return {"status": "ok", "alerts_found": len(alerts_data), "notifications_created": created}


async def _get_inventory_alerts():
    """内部函数：获取库存预警列表"""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM alert_rules WHERE is_active=1")
    rules = await cursor.fetchall()
    rule_map = {r["model_series"]: dict(r) for r in rules}

    cursor = await db.execute("""
        SELECT i.*, s.name as store_name
        FROM inventory i JOIN stores s ON i.store_id = s.id
        WHERE s.is_active = 1
    """)
    all_inv = await cursor.fetchall()

    alerts = []

    def get_series(mc):
        if not mc: return ""
        s = mc.upper()
        if any(k in s for k in ("S9420","S9470","S9480")): return "S26"
        if "ZFOLD7" in s: return "FOLD7"
        if "ZFLIP7" in s: return "FLIP7"
        if "W26" in s: return "W26"
        return ""

    if "S26" in rule_map and rule_map["S26"]["rule_type"] == "per_store_color_spec":
        threshold = rule_map["S26"]["threshold"]
        for inv in all_inv:
            if get_series(inv["model_code"]) != "S26": continue
            if inv["qty"] < threshold:
                alerts.append({"series": "S26",
                    "message": f"{inv['store_name']} {inv['model_code']} {inv['color']} {inv['spec']} 仅{inv['qty']}台（需≥{threshold}台）"})

    from collections import defaultdict

    if "FOLD7" in rule_map:
        threshold = rule_map["FOLD7"]["threshold"]
        st = defaultdict(int)
        for i in all_inv:
            if get_series(i["model_code"]) == "FOLD7": st[i["store_name"]] += i["qty"]
        for sn, total in st.items():
            if total < threshold:
                alerts.append({"series": "FOLD7", "message": f"{sn} Z Fold7 合计仅{total}台（需≥{threshold}台）"})

    if "FLIP7" in rule_map:
        threshold = rule_map["FLIP7"]["threshold"]
        st = defaultdict(int)
        for i in all_inv:
            if get_series(i["model_code"]) == "FLIP7": st[i["store_name"]] += i["qty"]
        for sn, total in st.items():
            if total < threshold:
                alerts.append({"series": "FLIP7", "message": f"{sn} Z Flip7 合计仅{total}台（需≥{threshold}台）"})

    if "W26" in rule_map:
        threshold = rule_map["W26"]["threshold"]
        w26_total = sum(i["qty"] for i in all_inv if get_series(i["model_code"]) == "W26")
        if w26_total < threshold:
            alerts.append({"series": "W26", "message": f"W26 全渠道仅{w26_total}台（需≥{threshold}台）"})

    alerts.sort(key=lambda x: (x["series"], x.get("store","")))
    return alerts
