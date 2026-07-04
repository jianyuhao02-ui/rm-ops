"""会员管理 API - 含标签管理、购机追踪、重点客户跟进"""
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.dependencies import get_current_user, require_admin, require_manager_or_admin
from pydantic import BaseModel
from typing import Optional, List
from backend.models.database import get_db

router = APIRouter()

# ─── 请求模型 ───────────────────────────────────────────────

class CreateMemberRequest(BaseModel):
    name: str
    phone: str
    store_id: Optional[int] = None
    level: Optional[str] = "普通"
    is_vip: Optional[int] = 0
    join_date: Optional[str] = None
    remark: Optional[str] = None

class UpdateMemberRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    store_id: Optional[int] = None
    level: Optional[str] = None
    is_vip: Optional[int] = None
    join_date: Optional[str] = None
    remark: Optional[str] = None

class AddPurchaseRequest(BaseModel):
    amount: float
    store_id: Optional[int] = None
    model_code: Optional[str] = ""
    product_info: Optional[str] = ""
    spec: Optional[str] = ""
    color: Optional[str] = ""
    imei: Optional[str] = ""
    trade_in_model: Optional[str] = ""
    trade_in_amount: Optional[float] = 0
    purchase_date: Optional[str] = None

class CreateTagDefRequest(BaseModel):
    name: str
    color: Optional[str] = "#1428a0"
    description: Optional[str] = ""

class SetMemberTagsRequest(BaseModel):
    tag_ids: List[int]

class AddFollowupRequest(BaseModel):
    content: str
    followup_type: Optional[str] = "call"   # call/visit/wechat/sms
    result: Optional[str] = ""
    next_followup_date: Optional[str] = None
    store_id: Optional[int] = None

class ResolveFollowupRequest(BaseModel):
    is_resolved: int = 1


# ─── 统计总览 ─────────────────────────────────────────────

@router.get("/stats")
async def get_member_stats(
    user: dict = Depends(get_current_user)
):
    """会员统计总览（按门店权限过滤）"""
    db = await get_db()
    store_id = user.get("store_id")
    store_cond = " AND store_id = ?" if store_id else ""
    store_params = [store_id] if store_id else []

    # 总数
    cur = await db.execute(
        f"SELECT COUNT(*) FROM members WHERE is_active=1{store_cond}",
        store_params
    )
    total = (await cur.fetchone())[0]

    # 新增（本月）
    cur = await db.execute(
        f"SELECT COUNT(*) FROM members WHERE is_active=1{store_cond} AND join_date LIKE ?",
        store_params + [f"{__import__('datetime').date.today().strftime('%Y-%m')}%"]
    )
    new_this_month = (await cur.fetchone())[0]

    # VIP 数
    cur = await db.execute(
        f"SELECT COUNT(*) FROM members WHERE is_active=1{store_cond} AND is_vip=1",
        store_params
    )
    vip_count = (await cur.fetchone())[0]

    # 等级分布
    cur = await db.execute(
        f"SELECT level, COUNT(*) as cnt FROM members WHERE is_active=1{store_cond} GROUP BY level ORDER BY cnt DESC",
        store_params
    )
    level_dist = {r["level"]: r["cnt"] for r in await cur.fetchall()}

    # 门店分布（非 admin 只看自己门店）
    if store_id:
        cur = await db.execute("""
            SELECT s.name as store_name,
                   COUNT(DISTINCT m.id) as member_count,
                   COALESCE(SUM(m.total_spent), 0) as total_spent
            FROM stores s
            LEFT JOIN members m ON m.store_id = s.id AND m.is_active = 1
            WHERE s.is_active = 1 AND s.id = ?
            GROUP BY s.id
        """, (store_id,))
    else:
        cur = await db.execute("""
            SELECT s.name as store_name,
                   COUNT(DISTINCT m.id) as member_count,
                   COALESCE(SUM(m.total_spent), 0) as total_spent
            FROM stores s
            LEFT JOIN members m ON m.store_id = s.id AND m.is_active = 1
            WHERE s.is_active = 1
            GROUP BY s.id ORDER BY member_count DESC
        """)
    store_dist = [dict(r) for r in await cur.fetchall()]

    # 总消费额
    cur = await db.execute(
        f"SELECT COALESCE(SUM(total_spent),0) FROM members WHERE is_active=1{store_cond}",
        store_params
    )
    total_spent = (await cur.fetchone())[0]

    # 待跟进数（未解决）
    cur = await db.execute(
        f"SELECT COUNT(*) FROM member_followups WHERE is_resolved=0{store_cond}",
        store_params
    )
    pending_followups = (await cur.fetchone())[0]

    # 近30天购机数
    cur = await db.execute(
        f"SELECT COUNT(*) FROM member_purchases WHERE purchase_date >= date('now','-30 days'){store_cond}",
        store_params
    )
    purchases_30d = (await cur.fetchone())[0]

    # 最活跃机型 TOP5
    cur = await db.execute(f"""
        SELECT model_code, COUNT(*) as cnt FROM member_purchases
        WHERE model_code != '' AND purchase_date >= date('now','-90 days'){store_cond}
        GROUP BY model_code ORDER BY cnt DESC LIMIT 5
    """, store_params)
    top_models = [dict(r) for r in await cur.fetchall()]

    # ── 消费频次分析 ──────────────────────────────────
    freq_sql = f"""
        SELECT
            SUM(CASE WHEN purchase_count >= 10 THEN 1 ELSE 0 END) as high_freq,
            SUM(CASE WHEN purchase_count BETWEEN 3 AND 9 THEN 1 ELSE 0 END) as mid_freq,
            SUM(CASE WHEN purchase_count IN (1,2) THEN 1 ELSE 0 END) as low_freq,
            SUM(CASE WHEN purchase_count = 0 THEN 1 ELSE 0 END) as no_purchase
        FROM (
            SELECT m.id, COUNT(mp.id) as purchase_count
            FROM members m
            LEFT JOIN member_purchases mp ON mp.member_id = m.id
            WHERE m.is_active = 1{store_cond}
            GROUP BY m.id
        )
    """
    cur = await db.execute(freq_sql, store_params)
    freq_row = await cur.fetchone()
    frequency_analysis = {
        "high": freq_row[0] or 0,   # 高频 ≥10次
        "mid":  freq_row[1] or 0,   # 中频 3-9次
        "low":  freq_row[2] or 0,   # 低频 1-2次
        "none": freq_row[3] or 0,   # 无消费
    }

    # ── 消费习惯分析 ──────────────────────────────────
    # 客单价分布
    cur = await db.execute("""
        SELECT
            SUM(CASE WHEN avg_ticket < 1000 THEN 1 ELSE 0 END) as tier1,
            SUM(CASE WHEN avg_ticket BETWEEN 1000 AND 2999 THEN 1 ELSE 0 END) as tier2,
            SUM(CASE WHEN avg_ticket BETWEEN 3000 AND 4999 THEN 1 ELSE 0 END) as tier3,
            SUM(CASE WHEN avg_ticket BETWEEN 5000 AND 7999 THEN 1 ELSE 0 END) as tier4,
            SUM(CASE WHEN avg_ticket >= 8000 THEN 1 ELSE 0 END) as tier5
        FROM (
            SELECT m.id,
                   CASE WHEN COUNT(mp.id) > 0
                        THEN m.total_spent * 1.0 / COUNT(mp.id)
                        ELSE 0 END as avg_ticket
            FROM members m
            LEFT JOIN member_purchases mp ON mp.member_id = m.id
            WHERE m.is_active = 1 AND m.total_spent > 0
            GROUP BY m.id
        )
    """)
    ticket_row = await cur.fetchone()
    avg_ticket_dist = {
        "lt1000":  ticket_row[0] or 0,
        "1000_2999": ticket_row[1] or 0,
        "3000_4999": ticket_row[2] or 0,
        "5000_7999": ticket_row[3] or 0,
        "gte8000":   ticket_row[4] or 0,
    }

    # 换机周期（有≥2次购买的会员的平均间隔天数）
    cur = await db.execute("""
        SELECT AVG(cycle_days) as avg_cycle
        FROM (
            SELECT member_id,
                   AVG(JULIANDAY(purchase_date) - JULIANDAY(lag_date)) as cycle_days
            FROM (
                SELECT member_id, purchase_date,
                       LAG(purchase_date) OVER (PARTITION BY member_id ORDER BY purchase_date) as lag_date
                FROM member_purchases
            )
            WHERE lag_date IS NOT NULL
            GROUP BY member_id
        )
    """)
    cycle_row = await cur.fetchone()
    avg_upgrade_cycle = round(cycle_row[0] or 0, 1)

    # 价格敏感度：用标准差衡量（标准差小=价格敏感，标准差大=价格不敏感）
    cur = await db.execute("""
        SELECT
            AVG(amount) as grand_mean,
            AVG(amount * amount) - AVG(amount) * AVG(amount) as variance
        FROM member_purchases
        WHERE amount > 0
    """)
    price_row = await cur.fetchone()
    price_stddev = round((price_row[1] or 0) ** 0.5, 0)

    # 消费月份偏好（哪个月份购买最多）
    cur = await db.execute("""
        SELECT CAST(substr(purchase_date,6,2) AS INTEGER) as month,
               COUNT(*) as cnt
        FROM member_purchases
        WHERE purchase_date != ''
        GROUP BY month
        ORDER BY cnt DESC
        LIMIT 3
    """)
    month_pref = [{"month": r["month"], "count": r["cnt"]} for r in await cur.fetchall()]

    # 机型偏好 TOP10（全量）
    cur = await db.execute("""
        SELECT model_code, COUNT(*) as cnt, AVG(amount) as avg_amount
        FROM member_purchases
        WHERE model_code != '' AND model_code IS NOT NULL
        GROUP BY model_code
        ORDER BY cnt DESC
        LIMIT 10
    """)
    model_pref = [dict(r) for r in await cur.fetchall()]

    return {
        "total": total,
        "new_this_month": new_this_month,
        "vip_count": vip_count,
        "level_distribution": level_dist,
        "store_distribution": store_dist,
        "total_spent": total_spent,
        "pending_followups": pending_followups,
        "purchases_30d": purchases_30d,
        "top_models": top_models,
        # 新增
        "frequency_analysis": frequency_analysis,
        "avg_ticket_distribution": avg_ticket_dist,
        "avg_upgrade_cycle_days": avg_upgrade_cycle,
        "price_stddev": price_stddev,
        "month_preference": month_pref,
        "model_preference": model_pref,
    }


# ─── 标签定义（放在 /{member_id} 之前，防止路由歧义）─────────────────────────────

@router.get("/tags/defs")
async def list_tag_defs_early(
    user: dict = Depends(get_current_user)
):
    """获取所有标签定义（前置注册，避免被 /{member_id} 拦截）"""
    db = await get_db()
    cur = await db.execute("""
        SELECT td.*, COUNT(mt.id) as member_count
        FROM member_tag_defs td
        LEFT JOIN member_tags mt ON mt.tag_id=td.id
        GROUP BY td.id ORDER BY td.name
    """)
    return [dict(r) for r in await cur.fetchall()]


@router.get("/followups/pending")
async def get_pending_followups_early(
    user: dict = Depends(get_current_user),
    store_id: int = 0, page: int = 1, page_size: int = 20):
    """待跟进列表（前置注册，避免被 /{member_id} 拦截）"""
    db = await get_db()
    conditions = ["mf.is_resolved = 0"]
    params = []
    # 权限控制：非 admin（绑定了门店）只能看自己门店
    if user.get("store_id"):
        conditions.append("mf.store_id = ?")
        params.append(user["store_id"])
    elif store_id > 0 and user["role"] == "admin":
        conditions.append("mf.store_id = ?")
        params.append(store_id)
    where = " AND ".join(conditions)
    cur = await db.execute(f"SELECT COUNT(*) FROM member_followups mf WHERE {where}", params)
    total = (await cur.fetchone())[0]
    offset = (page - 1) * page_size
    cur = await db.execute(f"""
        SELECT mf.*, m.name as member_name, m.phone as member_phone,
               m.level as member_level, m.is_vip,
               u.display_name as staff_name, s.name as store_name
        FROM member_followups mf
        JOIN members m ON mf.member_id=m.id
        LEFT JOIN users u ON mf.staff_id=u.id
        LEFT JOIN stores s ON mf.store_id=s.id
        WHERE {where}
        ORDER BY mf.next_followup_date ASC, mf.created_at DESC
        LIMIT ? OFFSET ?
    """, params + [page_size, offset])
    return {
        "total": total, "page": page, "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "data": [dict(r) for r in await cur.fetchall()]
    }


# ─── 会员列表 ────────────────────────────────────────────

@router.get("/list")
async def list_members(
    user: dict = Depends(get_current_user),
    keyword: str = "",
    level: str = "",
    store_id: int = 0,
    is_vip: int = -1,
    tag_id: int = 0,
    has_pending_followup: int = -1,
    page: int = 1,
    page_size: int = 20
):
    """会员列表（支持搜索/等级/标签/VIP/待跟进 筛选）"""

    db = await get_db()
    conditions = ["m.is_active = 1"]
    params = []

    # 权限控制：非 admin（绑定了门店）只能看自己门店
    if user.get("store_id"):
        conditions.append("m.store_id = ?")
        params.append(user["store_id"])
    elif store_id > 0 and user["role"] == "admin":
        conditions.append("m.store_id = ?")
        params.append(store_id)

    if keyword:
        conditions.append("(m.name LIKE ? OR m.phone LIKE ?)")
        kw = f"%{keyword}%"
        params += [kw, kw]

    if level:
        conditions.append("m.level = ?")
        params.append(level)

    if is_vip >= 0:
        conditions.append("m.is_vip = ?")
        params.append(is_vip)

    if tag_id > 0:
        conditions.append("EXISTS(SELECT 1 FROM member_tags mt WHERE mt.member_id=m.id AND mt.tag_id=?)")
        params.append(tag_id)

    if has_pending_followup == 1:
        conditions.append("EXISTS(SELECT 1 FROM member_followups mf WHERE mf.member_id=m.id AND mf.is_resolved=0)")

    where_clause = " AND ".join(conditions)

    # 总数
    cur = await db.execute(f"SELECT COUNT(*) FROM members m WHERE {where_clause}", params)
    total = (await cur.fetchone())[0]

    # 分页
    offset = (page - 1) * page_size
    sql = f"""
        SELECT m.*, s.name as store_name,
          (SELECT COUNT(*) FROM member_purchases mp WHERE mp.member_id=m.id) as purchase_count,
          (SELECT MAX(mp2.purchase_date) FROM member_purchases mp2 WHERE mp2.member_id=m.id) as last_purchase_date,
          (SELECT COUNT(*) FROM member_followups mf WHERE mf.member_id=m.id AND mf.is_resolved=0) as pending_followups,
          (SELECT GROUP_CONCAT(td.name, ',') FROM member_tags mt
           JOIN member_tag_defs td ON mt.tag_id=td.id WHERE mt.member_id=m.id) as tags,
          (SELECT GROUP_CONCAT(td.color, ',') FROM member_tags mt
           JOIN member_tag_defs td ON mt.tag_id=td.id WHERE mt.member_id=m.id) as tag_colors
        FROM members m
        LEFT JOIN stores s ON m.store_id = s.id
        WHERE {where_clause}
        ORDER BY m.is_vip DESC, m.total_spent DESC, m.created_at DESC
        LIMIT ? OFFSET ?
    """
    cur = await db.execute(sql, params + [page_size, offset])
    rows = [dict(r) for r in await cur.fetchall()]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "data": rows
    }


# ─── 会员详情 ────────────────────────────────────────────

@router.get("/{member_id}")
async def get_member_detail(member_id: int,
    user: dict = Depends(get_current_user)):
    """会员详情（含购机记录+标签+跟进记录）"""

    db = await get_db()
    cur = await db.execute("""
        SELECT m.*, s.name as store_name
        FROM members m LEFT JOIN stores s ON m.store_id = s.id
        WHERE m.id = ?
    """, (member_id,))
    member = await cur.fetchone()
    if not member:
        raise HTTPException(status_code=404, detail="会员不存在")

    member_dict = dict(member)

    # 权限：绑定了门店的用户只能查看自己门店的会员
    if user.get("store_id") and member_dict.get("store_id") != user["store_id"]:
        raise HTTPException(status_code=403, detail="权限不足，只能查看本门店会员")

    # 购机记录（全量，按日期降序）
    cur = await db.execute("""
        SELECT mp.*, s.name as store_name
        FROM member_purchases mp LEFT JOIN stores s ON mp.store_id = s.id
        WHERE mp.member_id = ? ORDER BY mp.purchase_date DESC, mp.id DESC
    """, (member_id,))
    member_dict["purchases"] = [dict(r) for r in await cur.fetchall()]

    # 标签
    cur = await db.execute("""
        SELECT td.id, td.name, td.color
        FROM member_tags mt JOIN member_tag_defs td ON mt.tag_id=td.id
        WHERE mt.member_id = ?
    """, (member_id,))
    member_dict["tags"] = [dict(r) for r in await cur.fetchall()]

    # 跟进记录（最近20条）
    cur = await db.execute("""
        SELECT mf.*, u.display_name as staff_name, s.name as store_name
        FROM member_followups mf
        LEFT JOIN users u ON mf.staff_id=u.id
        LEFT JOIN stores s ON mf.store_id=s.id
        WHERE mf.member_id = ?
        ORDER BY mf.created_at DESC LIMIT 20
    """, (member_id,))
    member_dict["followups"] = [dict(r) for r in await cur.fetchall()]

    return member_dict


# ─── 创建/更新/删除 ───────────────────────────────────────

@router.post("/create")
async def create_member(req: CreateMemberRequest,
    user: dict = Depends(get_current_user)):
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    cur = await db.execute("SELECT id FROM members WHERE phone = ?", (req.phone,))
    if await cur.fetchone():
        raise HTTPException(status_code=400, detail="手机号已存在")

    import datetime
    join_date = req.join_date or datetime.date.today().isoformat()
    await db.execute(
        "INSERT INTO members (name, phone, store_id, level, is_vip, join_date, remark) VALUES (?,?,?,?,?,?,?)",
        (req.name, req.phone, req.store_id, req.level or "普通", req.is_vip or 0, join_date, req.remark)
    )
    await db.commit()
    cur = await db.execute("SELECT last_insert_rowid()")
    new_id = (await cur.fetchone())[0]
    return {"status": "ok", "id": new_id}


@router.put("/{member_id}")
async def update_member(member_id: int, req: UpdateMemberRequest,
    user: dict = Depends(get_current_user)):
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    cur = await db.execute("SELECT * FROM members WHERE id = ?", (member_id,))
    if not await cur.fetchone():
        raise HTTPException(status_code=404, detail="会员不存在")

    updates, params = [], []
    for field, val in [("name", req.name), ("phone", req.phone), ("store_id", req.store_id),
                       ("level", req.level), ("is_vip", req.is_vip), ("join_date", req.join_date), ("remark", req.remark)]:
        if val is not None:
            if field == "phone":
                cur2 = await db.execute("SELECT id FROM members WHERE phone=? AND id!=?", (val, member_id))
                if await cur2.fetchone():
                    raise HTTPException(status_code=400, detail="手机号已被使用")
            updates.append(f"{field} = ?")
            params.append(val)

    if updates:
        params.append(member_id)
        await db.execute(f"UPDATE members SET {', '.join(updates)} WHERE id = ?", params)
        await db.commit()
    return {"status": "ok"}


@router.delete("/{member_id}")
async def delete_member(member_id: int,
    user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可删除")

    db = await get_db()
    await db.execute("UPDATE members SET is_active=0 WHERE id=?", (member_id,))
    await db.commit()
    return {"status": "ok"}


# ─── 购机追踪 ─────────────────────────────────────────────

@router.post("/{member_id}/purchase")
async def add_purchase(member_id: int, req: AddPurchaseRequest,
    user: dict = Depends(get_current_user)):
    """添加购机记录"""
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    cur = await db.execute("SELECT * FROM members WHERE id=? AND is_active=1", (member_id,))
    member = await cur.fetchone()
    if not member:
        raise HTTPException(status_code=404, detail="会员不存在")

    points = int(req.amount)
    purchase_store = req.store_id or member["store_id"]

    import datetime
    purchase_date = req.purchase_date or datetime.date.today().isoformat()

    await db.execute(
        """INSERT INTO member_purchases
           (member_id, store_id, model_code, product_info, spec, color, imei,
            amount, points_earned, trade_in_model, trade_in_amount, purchase_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (member_id, purchase_store, req.model_code, req.product_info, req.spec,
         req.color, req.imei, req.amount, points,
         req.trade_in_model, req.trade_in_amount, purchase_date)
    )

    # 更新累计消费和积分
    await db.execute(
        "UPDATE members SET total_spent=total_spent+?, points=points+? WHERE id=?",
        (req.amount, points, member_id)
    )

    # 自动升级等级
    new_total = member["total_spent"] + req.amount
    new_level = member["level"]
    if new_total >= 50000: new_level = "黑卡"
    elif new_total >= 20000: new_level = "钻卡"
    elif new_total >= 5000: new_level = "金卡"
    elif new_total >= 1000: new_level = "银卡"
    if new_level != member["level"]:
        await db.execute("UPDATE members SET level=? WHERE id=?", (new_level, member_id))

    await db.commit()
    cur = await db.execute("SELECT last_insert_rowid()")
    pid = (await cur.fetchone())[0]

    return {"status": "ok", "purchase_id": pid, "points_earned": points,
            "level_upgraded": new_level != member["level"], "new_level": new_level}


@router.get("/{member_id}/purchases")
async def get_member_purchases(member_id: int,
    user: dict = Depends(get_current_user), page: int = 1, page_size: int = 20):

    db = await get_db()
    cur = await db.execute("SELECT COUNT(*) FROM member_purchases WHERE member_id=?", (member_id,))
    total = (await cur.fetchone())[0]
    offset = (page - 1) * page_size
    cur = await db.execute("""
        SELECT mp.*, s.name as store_name
        FROM member_purchases mp LEFT JOIN stores s ON mp.store_id=s.id
        WHERE mp.member_id=? ORDER BY mp.purchase_date DESC, mp.id DESC
        LIMIT ? OFFSET ?
    """, (member_id, page_size, offset))
    return {
        "total": total, "page": page, "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "data": [dict(r) for r in await cur.fetchall()]
    }


# ─── 标签管理 ─────────────────────────────────────────────

@router.get("/tags/defs")
async def list_tag_defs(
    user: dict = Depends(get_current_user)
):
    """获取所有标签定义"""

    db = await get_db()
    cur = await db.execute("""
        SELECT td.*, COUNT(mt.id) as member_count
        FROM member_tag_defs td
        LEFT JOIN member_tags mt ON mt.tag_id=td.id
        GROUP BY td.id ORDER BY td.name
    """)
    return [dict(r) for r in await cur.fetchall()]


@router.post("/tags/defs")
async def create_tag_def(req: CreateTagDefRequest,
    user: dict = Depends(get_current_user)):
    """创建标签定义（admin/manager）"""
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    cur = await db.execute("SELECT id FROM member_tag_defs WHERE name=?", (req.name,))
    if await cur.fetchone():
        raise HTTPException(status_code=400, detail="标签名称已存在")
    await db.execute(
        "INSERT INTO member_tag_defs (name, color, description) VALUES (?,?,?)",
        (req.name, req.color, req.description)
    )
    await db.commit()
    cur = await db.execute("SELECT last_insert_rowid()")
    return {"status": "ok", "id": (await cur.fetchone())[0]}


@router.delete("/tags/defs/{tag_id}")
async def delete_tag_def(tag_id: int,
    user: dict = Depends(get_current_user)):
    """删除标签定义（admin）"""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可删除标签")

    db = await get_db()
    await db.execute("DELETE FROM member_tags WHERE tag_id=?", (tag_id,))
    await db.execute("DELETE FROM member_tag_defs WHERE id=?", (tag_id,))
    await db.commit()
    return {"status": "ok"}


@router.put("/{member_id}/tags")
async def set_member_tags(member_id: int, req: SetMemberTagsRequest,
    user: dict = Depends(get_current_user)):
    """设置会员标签（全量覆盖）"""
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    await db.execute("DELETE FROM member_tags WHERE member_id=?", (member_id,))
    for tag_id in req.tag_ids:
        try:
            await db.execute(
                "INSERT INTO member_tags (member_id, tag_id) VALUES (?,?)",
                (member_id, tag_id)
            )
        except Exception:
            pass
    await db.commit()
    return {"status": "ok"}


# ─── 重点客户跟进 ────────────────────────────────────────

@router.get("/followups/pending")
async def get_pending_followups(
    user: dict = Depends(get_current_user),
    store_id: int = 0, page: int = 1, page_size: int = 20):
    """获取待跟进列表（重点客户跟进总览）"""

    db = await get_db()
    conditions = ["mf.is_resolved = 0"]
    params = []

    # 权限控制：非 admin（绑定了门店）只能看自己门店
    if user.get("store_id"):
        conditions.append("mf.store_id = ?")
        params.append(user["store_id"])
    elif store_id > 0 and user["role"] == "admin":
        conditions.append("mf.store_id = ?")
        params.append(store_id)

    where = " AND ".join(conditions)
    cur = await db.execute(f"SELECT COUNT(*) FROM member_followups mf WHERE {where}", params)
    total = (await cur.fetchone())[0]

    offset = (page - 1) * page_size
    cur = await db.execute(f"""
        SELECT mf.*, m.name as member_name, m.phone as member_phone,
               m.level as member_level, m.is_vip,
               u.display_name as staff_name, s.name as store_name
        FROM member_followups mf
        JOIN members m ON mf.member_id=m.id
        LEFT JOIN users u ON mf.staff_id=u.id
        LEFT JOIN stores s ON mf.store_id=s.id
        WHERE {where}
        ORDER BY mf.next_followup_date ASC, mf.created_at DESC
        LIMIT ? OFFSET ?
    """, params + [page_size, offset])

    return {
        "total": total, "page": page, "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "data": [dict(r) for r in await cur.fetchall()]
    }


@router.post("/{member_id}/followup")
async def add_followup(member_id: int, req: AddFollowupRequest,
    user: dict = Depends(get_current_user)):
    """添加跟进记录"""

    db = await get_db()
    cur = await db.execute("SELECT id FROM members WHERE id=? AND is_active=1", (member_id,))
    if not await cur.fetchone():
        raise HTTPException(status_code=404, detail="会员不存在")

    store_id = req.store_id or user.get("store_id")
    await db.execute(
        """INSERT INTO member_followups
           (member_id, store_id, staff_id, followup_type, content, result, next_followup_date)
           VALUES (?,?,?,?,?,?,?)""",
        (member_id, store_id, user["id"], req.followup_type,
         req.content, req.result, req.next_followup_date)
    )
    await db.commit()
    cur = await db.execute("SELECT last_insert_rowid()")
    return {"status": "ok", "id": (await cur.fetchone())[0]}


@router.put("/followups/{followup_id}/resolve")
async def resolve_followup(followup_id: int, req: ResolveFollowupRequest,
    user: dict = Depends(get_current_user)):
    """标记跟进已完成/未完成"""

    db = await get_db()
    await db.execute(
        "UPDATE member_followups SET is_resolved=? WHERE id=?",
        (req.is_resolved, followup_id)
    )
    await db.commit()
    return {"status": "ok"}


@router.delete("/followups/{followup_id}")
async def delete_followup(followup_id: int,
    user: dict = Depends(get_current_user)):
    """删除跟进记录（admin/manager）"""
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    await db.execute("DELETE FROM member_followups WHERE id=?", (followup_id,))
    await db.commit()
    return {"status": "ok"}
