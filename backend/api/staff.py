"""店员管理 API"""
import re
from fastapi import APIRouter, Depends, HTTPException
from backend.dependencies import get_current_user, require_admin, require_manager_or_admin
from backend.models.database import get_db

router = APIRouter()


# ── 店员列表 ──────────────────────────────────────

@router.get("/list")
async def list_staff(
    user: dict = Depends(get_current_user),
    store_id: int = None):
    """获取店员列表"""

    db = await get_db()
    if store_id:
        cursor = await db.execute("""
            SELECT s.*, st.name as store_name
            FROM staff s JOIN stores st ON s.store_id = st.id
            WHERE s.store_id = ? AND s.is_active = 1
            ORDER BY s.store_id, s.position DESC, s.id
        """, (store_id,))
    else:
        cursor = await db.execute("""
            SELECT s.*, st.name as store_name
            FROM staff s JOIN stores st ON s.store_id = st.id
            WHERE s.is_active = 1
            ORDER BY s.store_id, s.position DESC, s.id
        """)
    return [dict(r) for r in await cursor.fetchall()]


# ── 店员详情（含销售数据）─────────────────────────

@router.get("/{staff_id}")
async def get_staff_detail(staff_id: int, month: str = None,
    user: dict = Depends(get_current_user)):
    """获取店员详情，含当月销售和提成"""

    db = await get_db()
    # 店员信息
    cursor = await db.execute("""
        SELECT s.*, st.name as store_name
        FROM staff s JOIN stores st ON s.store_id = st.id
        WHERE s.id = ?
    """, (staff_id,))
    staff = await cursor.fetchone()
    if not staff:
        raise HTTPException(404, "店员不存在")

    staff_data = dict(staff)

    # 当月销售汇总
    if not month:
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")

    cursor = await db.execute("""
        SELECT
            SUM(phone_sales) as phone_sales,
            SUM(ncme_sales) as ncme_sales,
            SUM(phone_qty) as phone_qty,
            SUM(key_model_qty) as key_model_qty,
            SUM(accessory_sales) as accessory_sales,
            SUM(trade_in_qty) as trade_in_qty,
            SUM(commission) as commission
        FROM staff_sales
        WHERE staff_id=? AND sale_date LIKE ?
    """, (staff_id, month + "%"))

    sales = await cursor.fetchone()
    staff_data["sales"] = dict(sales) if sales else {}

    # 当月目标
    y, m = month.split("-")
    cursor = await db.execute("""
        SELECT * FROM staff_targets
        WHERE staff_id=? AND year=? AND month=?
    """, (staff_id, int(y), int(m)))
    target = await cursor.fetchone()
    staff_data["target"] = dict(target) if target else {}

    # 收入预估 = 底薪 + 提成
    base = staff_data.get("base_salary", 3000) or 3000
    commission = (sales and sales[6]) or 0
    staff_data["estimated_income"] = base + commission

    # 提成明细
    staff_data["commission_detail"] = await _calc_commission_breakdown(db, staff_id, month)

    return staff_data


# ── 提成计算 ──────────────────────────────────────

@router.get("/{staff_id}/commission")
async def get_staff_commission(staff_id: int, month: str = None,
    user: dict = Depends(get_current_user)):
    """获取店员提成明细"""

    if not month:
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")

    db = await get_db()
    return await _calc_commission_breakdown(db, staff_id, month)


async def _calc_commission_breakdown(db, staff_id: int, month: str) -> dict:
    """计算提成明细"""
    # 当月销售
    cursor = await db.execute("""
        SELECT SUM(phone_qty) as phone_qty,
               SUM(key_model_qty) as key_model_qty,
               SUM(ncme_sales) as ncme_sales,
               SUM(accessory_sales) as accessory_sales,
               SUM(trade_in_qty) as trade_in_qty,
               SUM(commission) as total_commission
        FROM staff_sales
        WHERE staff_id=? AND sale_date LIKE ?
    """, (staff_id, month + "%"))
    sales = await cursor.fetchone()

    if not sales or not sales[0]:
        return {"phone_qty": 0, "breakdown": [], "total": 0}

    # 提成规则
    cursor = await db.execute("SELECT * FROM commission_rules WHERE is_active=1")
    rules = [dict(r) for r in await cursor.fetchall()]

    breakdown = []
    total_commission = 0

    for rule in rules:
        amount = 0
        ptype = rule["product_type"]

        if ptype == "phone" and rule["commission_type"] == "fixed":
            # 手机固定提成 = 台量 × 单价
            qty = sales[0]  # phone_qty
            amount = qty * (rule["commission_fixed"] or 0)
        elif ptype == "ncme" and rule["commission_type"] == "percentage":
            amount = (sales[2] or 0) * (rule["commission_rate"] or 0)
        elif ptype == "accessory" and rule["commission_type"] == "percentage":
            amount = (sales[3] or 0) * (rule["commission_rate"] or 0)
        elif ptype == "trade_in" and rule["commission_type"] == "fixed":
            amount = (sales[4] or 0) * (rule["commission_fixed"] or 0)

        if amount > 0:
            breakdown.append({
                "rule_name": rule["rule_name"],
                "type": ptype,
                "amount": round(amount, 2),
            })
            total_commission += amount

    return {
        "breakdown": breakdown,
        "total": round(total_commission, 2),
    }


# ── 店员销售排行 ──────────────────────────────────

@router.get("/ranking/sales")
async def get_sales_ranking(
    user: dict = Depends(get_current_user),
    month: str = None, limit: int = 20):
    """获取店员销售排行"""

    if not month:
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")

    db = await get_db()
    cursor = await db.execute("""
        SELECT sf.id, sf.name, sf.store_id, st.name as store_name,
               COALESCE(ss.phone_qty, 0) as phone_qty,
               COALESCE(ss.phone_sales, 0) as phone_sales,
               COALESCE(ss.ncme_sales, 0) as ncme_sales,
               COALESCE(ss.key_model_qty, 0) as key_model_qty,
               COALESCE(ss.accessory_sales, 0) as accessory_sales,
               COALESCE(ss.trade_in_qty, 0) as trade_in_qty,
               COALESCE(ss.commission, 0) as commission
        FROM staff sf
        JOIN stores st ON sf.store_id = st.id
        LEFT JOIN (
            SELECT staff_id,
                   SUM(phone_qty) as phone_qty,
                   SUM(phone_sales) as phone_sales,
                   SUM(ncme_sales) as ncme_sales,
                   SUM(key_model_qty) as key_model_qty,
                   SUM(accessory_sales) as accessory_sales,
                   SUM(trade_in_qty) as trade_in_qty,
                   SUM(commission) as commission
            FROM staff_sales
            WHERE sale_date LIKE ?
            GROUP BY staff_id
        ) ss ON sf.id = ss.staff_id
        WHERE sf.is_active = 1
        ORDER BY COALESCE(ss.phone_sales, 0) DESC
        LIMIT ?
    """, (month + "%", limit))
    return [dict(r) for r in await cursor.fetchall()]


# ── 每日同步：将门店数据分摊到店员 ─────────────────

@router.post("/sync-daily")
async def sync_staff_sales(
    user: dict = Depends(get_current_user),
    date: str = None):
    """将门店每日销售数据自动分摊给店员"""
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(403, "权限不足")

    if not date:
        from datetime import datetime, timedelta
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    db = await get_db()
    # 获取该日期所有门店销售
    cursor = await db.execute(
        "SELECT * FROM daily_sales WHERE date=? AND source='eboss'",
        (date,))
    store_sales = [dict(r) for r in await cursor.fetchall()]

    # 获取每个门店的店员数
    synced = 0
    for ss in store_sales:
        store_id = ss["store_id"]
        cursor = await db.execute(
            "SELECT id FROM staff WHERE store_id=? AND is_active=1",
            (store_id,))
        staff_ids = [r[0] for r in await cursor.fetchall()]

        if not staff_ids:
            continue

        # 平均分摊给店员
        n = len(staff_ids)
        for sid in staff_ids:
            # 检查是否已存在
            cursor = await db.execute(
                "SELECT id FROM staff_sales WHERE staff_id=? AND sale_date=? AND store_id=?",
                (sid, date, store_id))
            existing = await cursor.fetchone()

            if existing:
                continue

            await db.execute("""
                INSERT INTO staff_sales
                (staff_id, store_id, sale_date, phone_sales, ncme_sales,
                 phone_qty, key_model_qty, accessory_sales, trade_in_qty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sid, store_id, date,
                round(ss["phone_sales"] / n, 2),
                round(ss["ncme_sales"] / n, 2),
                max(1, round(ss["phone_qty"] / n)),
                max(1, round((ss["key_model_qty"] or 0) / n)),
                round(ss["accessory_sales"] / n, 2),
                round((ss["trade_in_qty"] or 0) / n),
            ))
            synced += 1

    await db.commit()

    # 计算提成
    if synced > 0:
        await _calc_and_save_commissions(db, date)

    return {"status": "ok", "synced": synced, "date": date}


async def _calc_and_save_commissions(db, date: str):
    """计算并保存提成"""
    # 获取该日期新同步的店员销售
    cursor = await db.execute(
        "SELECT * FROM staff_sales WHERE sale_date=? AND commission=0",
        (date,))
    rows = await cursor.fetchall()

    # 提成规则
    cursor2 = await db.execute("SELECT * FROM commission_rules WHERE is_active=1")
    rules = [dict(r) for r in await cursor2.fetchall()]

    for r in rows:
        # 使用命名字段访问，避免依赖列顺序导致静默错误
        r_dict = dict(r)
        total_comm = 0
        for rule in rules:
            ptype = rule["product_type"]
            if ptype == "phone" and rule["commission_type"] == "fixed":
                total_comm += (r_dict.get("phone_qty") or 0) * (rule["commission_fixed"] or 0)
            elif ptype == "ncme" and rule["commission_type"] == "percentage":
                total_comm += (r_dict.get("ncme_sales") or 0) * (rule["commission_rate"] or 0)
            elif ptype == "accessory" and rule["commission_type"] == "percentage":
                total_comm += (r_dict.get("accessory_sales") or 0) * (rule["commission_rate"] or 0)
            elif ptype == "trade_in" and rule["commission_type"] == "fixed":
                total_comm += (r_dict.get("trade_in_qty") or 0) * (rule["commission_fixed"] or 0)

        await db.execute(
            "UPDATE staff_sales SET commission=? WHERE id=?",
            (round(total_comm, 2), r_dict["id"]))

    await db.commit()


# ── 活动政策 ──────────────────────────────────────

@router.get("/activities/list")
async def list_activities(
    user: dict = Depends(get_current_user)
):
    """获取活动政策列表"""

    db = await get_db()
    cursor = await db.execute("""
        SELECT * FROM activities WHERE is_active=1
        ORDER BY created_at DESC
    """)
    return [dict(r) for r in await cursor.fetchall()]


# ── 店员新增/编辑 ─────────────────────────────────

@router.post("/create")
async def create_staff(
    store_id: int, name: str,
    position: str = "店员", phone: str = "",
    base_salary: float = 3000,
    user: dict = Depends(get_current_user)):
    """新增店员"""
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(403, "权限不足")

    db = await get_db()
    cursor = await db.execute("""
        INSERT INTO staff (store_id, name, phone, position, base_salary)
        VALUES (?, ?, ?, ?, ?)
    """, (store_id, name, phone, position, base_salary))
    await db.commit()
    return {"status": "ok", "id": cursor.lastrowid}
