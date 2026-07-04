"""
订单管理 API — Phase 1: 快速成交卡片
每个订单入库时自动：
  1. 聚合到 daily_sales
  2. 写入 staff_sales + 实时计算提成
  3. 手机号自动匹配/创建会员 + 添加购买记录
"""
import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from backend.dependencies import get_current_user
from backend.models.database import get_db

router = APIRouter()


# ── 机型分类规则（与 eBoss parser 保持一致） ──

NCME_KEYWORDS = [
    "watch", "buds", "fit", "ring",   # 穿戴
    "手表", "耳机", "手环", "戒指",
    "tab", "sm-x", "平板",            # 平板
    "book", "笔记本",                  # 笔记本
]


def _rule_matches_order(rule_keyword: str, model_code: str, product_name: str) -> bool:
    """检查提成规则的 model_keyword 是否匹配订单型号
    
    支持多种匹配方式：
    1. 直接子串匹配（不区分大小写）
    2. 去掉 SM- 前缀后匹配
    3. 对纯数字/字母代码做宽松匹配
    """
    if not rule_keyword or not rule_keyword.strip():
        return True  # 无 keyword 限制 → 匹配所有
    
    combined = (model_code + " " + product_name).upper()
    # 去掉 SM- 前缀的短代码
    short_code = model_code.upper().replace("SM-", "").replace("SM", "")
    
    for kw in rule_keyword.upper().split("|"):
        kw = kw.strip()
        if not kw:
            continue
        # 直接匹配
        if kw in combined or kw in short_code:
            return True
        # 如果 keyword 是纯数字/字母组合，尝试在型号代码中搜索
        if len(kw) >= 3 and (kw in model_code.upper() or kw in short_code):
            return True
    
    return False


# ── 机型分类规则 ──

NCME_KEYWORDS = [
    "watch", "buds", "fit", "ring",
    "手表", "耳机", "手环", "戒指",
    "tab", "sm-x", "平板",
    "book", "笔记本",
]


def classify_product(model_code: str, product_name: str = "") -> dict:
    """根据型号代码和品名自动判定品类和是否重点机型"""
    code_lower = (model_code or "").lower().strip()
    name_lower = (product_name or "").lower().strip()

    # 判定是否为 NCME
    is_ncme = False
    for kw in NCME_KEYWORDS:
        if kw in code_lower or kw in name_lower:
            is_ncme = True
            break

    if is_ncme:
        category = "ncme"
    elif code_lower and any(ch.isdigit() for ch in code_lower):
        category = "phone"
    elif name_lower and ("手机" in name_lower or "phone" in name_lower or "galaxy" in name_lower):
        category = "phone"
    else:
        category = "accessory"

    # 重点机型判定：W26 或 FOLD/FLIP/S 系列旗舰
    is_key = 0
    combined = code_lower + " " + name_lower
    if re.search(r'w26(?!\d)', combined):  # W26 后面不直接跟数字
        is_key = 1
    elif any(kw in combined for kw in ["ultra", "fold", "flip", "s26"]):
        is_key = 1

    return {"category": category, "is_key_model": is_key}


# ── 请求模型 ──

class CreateOrderRequest(BaseModel):
    store_id: int = Field(..., description="门店ID")
    staff_id: int = Field(..., description="成交店员ID")
    model_code: str = Field(..., description="型号代码,如 SM-S9380")
    product_name: str = Field(default="", description="品名,如 Galaxy S26 Ultra")
    spec: str = Field(default="", description="规格,如 12+512GB")
    color: str = Field(default="", description="颜色")
    imei: str = Field(default="", description="IMEI/串号")
    original_price: float = Field(default=0, description="标价")
    actual_price: float = Field(..., description="实际成交价")
    member_phone: str = Field(default="", description="客户手机号(自动匹配会员)")
    member_name: str = Field(default="", description="新客户姓名(仅新会员时使用)")
    trade_in_model: str = Field(default="", description="旧机型号")
    trade_in_amount: float = Field(default=0, description="旧机折价")
    remark: str = Field(default="", description="备注")


class BatchImportRow(BaseModel):
    store_id: int
    staff_id: int
    model_code: str
    product_name: str = ""
    actual_price: float
    member_phone: str = ""
    trade_in_amount: float = 0
    remark: str = ""


# ── 创建订单（核心） ──

@router.post("/create")
async def create_order(
    req: CreateOrderRequest,
    user: dict = Depends(get_current_user)
):
    """
    创建一笔成交订单，自动完成：
    - 品类识别 & 重点机型标记
    - 聚合到 daily_sales
    - 写入 staff_sales & 计算提成
    - 会员自动匹配/创建 & 购买记录
    """
    db = await get_db()

    # 1. 品类自动分类
    classified = classify_product(req.model_code, req.product_name)
    category = classified["category"]
    is_key_model = classified["is_key_model"]

    # 2. 日期
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M:%S")

    # 3. IMEI 重复检测
    if req.imei and req.imei.strip():
        cursor = await db.execute(
            "SELECT id FROM sales_orders WHERE imei=? AND order_date=?",
            (req.imei.strip(), today))
        if await cursor.fetchone():
            raise HTTPException(400, f"IMEI {req.imei} 今天已有录入记录，请勿重复录入")

    # 4. 写入订单
    cursor = await db.execute("""
        INSERT INTO sales_orders
        (store_id, staff_id, order_date, order_time, model_code, product_name,
         spec, color, imei, original_price, actual_price, category, is_key_model,
         member_phone, trade_in_model, trade_in_amount, source, remark, created_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        req.store_id, req.staff_id, today, now_time,
        req.model_code, req.product_name, req.spec, req.color,
        req.imei.strip() if req.imei else "",
        req.original_price, req.actual_price, category, is_key_model,
        req.member_phone.strip() if req.member_phone else "",
        req.trade_in_model, req.trade_in_amount,
        "manual", req.remark, user.get("user_id", 0)
    ))
    order_id = cursor.lastrowid

    # 5. 聚合到 daily_sales
    await _upsert_daily_sales(db, req.store_id, today, category,
                              req.actual_price, is_key_model,
                              req.trade_in_amount)

    # 6. 写入 staff_sales + 计算提成
    await _upsert_staff_sales(db, req.staff_id, req.store_id, today,
                              category, req.actual_price, is_key_model,
                              req.trade_in_amount)

    # 7. 会员自动匹配/创建 + 购买记录
    member_id = None
    if req.member_phone and req.member_phone.strip():
        member_id = await _link_member_and_purchase(
            db, req.member_phone.strip(), req.member_name,
            req.store_id, order_id, req.model_code,
            req.product_name, req.spec, req.color, req.imei,
            req.actual_price, req.trade_in_model, req.trade_in_amount,
            today)

        # 更新订单的 member_id
        if member_id:
            await db.execute(
                "UPDATE sales_orders SET member_id=? WHERE id=?",
                (member_id, order_id))

    await db.commit()

    return {
        "status": "ok",
        "order_id": order_id,
        "category": category,
        "is_key_model": is_key_model,
        "member_id": member_id,
        "message": f"订单 #{order_id} 已录入，品类: {category}，提成已自动计算"
    }


# ── 查询订单列表 ──

@router.get("/list")
async def list_orders(
    store_id: int = None,
    staff_id: int = None,
    date: str = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user)
):
    """查询订单列表，支持按门店/店员/日期筛选"""
    db = await get_db()

    conditions = []
    params = []

    if store_id:
        conditions.append("o.store_id = ?")
        params.append(store_id)
    if staff_id:
        conditions.append("o.staff_id = ?")
        params.append(staff_id)
    if date:
        conditions.append("o.order_date = ?")
        params.append(date)
    else:
        # 默认今天
        conditions.append("o.order_date = ?")
        params.append(datetime.now().strftime("%Y-%m-%d"))

    where = " AND ".join(conditions) if conditions else "1=1"

    cursor = await db.execute(f"""
        SELECT o.*, st.name as store_name, sf.name as staff_name,
               m.name as member_name, m.phone as member_phone_db
        FROM sales_orders o
        JOIN stores st ON o.store_id = st.id
        JOIN staff sf ON o.staff_id = sf.id
        LEFT JOIN members m ON o.member_id = m.id
        WHERE {where}
        ORDER BY o.order_time DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])
    rows = await cursor.fetchall()

    # 总数
    cursor2 = await db.execute(f"SELECT COUNT(*) FROM sales_orders o WHERE {where}", params)
    total = (await cursor2.fetchone())[0]

    return {"total": total, "list": [dict(r) for r in rows]}


# ── 今日汇总 ──

@router.get("/today")
async def get_today_summary(
    store_id: int = None,
    user: dict = Depends(get_current_user)
):
    """获取今日销售汇总"""
    db = await get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    if not store_id and user.get("store_id"):
        store_id = user["store_id"]

    if store_id:
        cursor = await db.execute("""
            SELECT
                COUNT(*) as total_orders,
                SUM(CASE WHEN category='phone' THEN 1 ELSE 0 END) as phone_qty,
                SUM(CASE WHEN category='phone' THEN actual_price ELSE 0 END) as phone_sales,
                SUM(CASE WHEN category='ncme' THEN actual_price ELSE 0 END) as ncme_sales,
                SUM(CASE WHEN is_key_model=1 THEN 1 ELSE 0 END) as key_model_qty,
                SUM(CASE WHEN category='accessory' THEN actual_price ELSE 0 END) as accessory_sales,
                SUM(CASE WHEN trade_in_amount>0 THEN 1 ELSE 0 END) as trade_in_qty,
                SUM(trade_in_amount) as trade_in_total
            FROM sales_orders
            WHERE order_date=? AND store_id=?
        """, (today, store_id))
        row = await cursor.fetchone()
        result = dict(row) if row else {"total_orders": 0}
        # 单独查询今日提成总额
        cc = await db.execute(
            "SELECT COALESCE(SUM(commission), 0) as total_commission FROM staff_sales WHERE sale_date=? AND store_id=?",
            (today, store_id)
        )
        result["total_commission"] = (await cc.fetchone())[0]
        return result
    else:
        cursor = await db.execute("""
            SELECT
                COUNT(*) as total_orders,
                SUM(CASE WHEN category='phone' THEN 1 ELSE 0 END) as phone_qty,
                SUM(CASE WHEN category='phone' THEN actual_price ELSE 0 END) as phone_sales,
                SUM(CASE WHEN category='ncme' THEN actual_price ELSE 0 END) as ncme_sales,
                SUM(CASE WHEN is_key_model=1 THEN 1 ELSE 0 END) as key_model_qty,
                SUM(CASE WHEN category='accessory' THEN actual_price ELSE 0 END) as accessory_sales,
                SUM(CASE WHEN trade_in_amount>0 THEN 1 ELSE 0 END) as trade_in_qty,
                SUM(trade_in_amount) as trade_in_total
            FROM sales_orders
            WHERE order_date=?
        """, (today,))
        row = await cursor.fetchone()
        result = dict(row) if row else {"total_orders": 0}
        cc = await db.execute(
            "SELECT COALESCE(SUM(commission), 0) as total_commission FROM staff_sales WHERE sale_date=?",
            (today,)
        )
        result["total_commission"] = (await cc.fetchone())[0]
        return result


# ── 店员实时排行 ──

@router.get("/staff-ranking")
async def get_staff_ranking(
    store_id: int = None,
    month: str = None,
    limit: int = 20,
    user: dict = Depends(get_current_user)
):
    """获取店员实时销售排行（基于订单数据）"""
    if not month:
        month = datetime.now().strftime("%Y-%m")

    db = await get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    # 本月排行
    conditions = ["o.order_date LIKE ?"]
    params = [month + "%"]
    if store_id:
        conditions.append("o.store_id = ?")
        params.append(store_id)

    where = " AND ".join(conditions)

    cursor = await db.execute(f"""
        SELECT
            sf.id, sf.name, sf.store_id, st.name as store_name,
            COUNT(*) as total_orders,
            SUM(CASE WHEN o.category='phone' THEN 1 ELSE 0 END) as phone_qty,
            SUM(CASE WHEN o.category='phone' THEN o.actual_price ELSE 0 END) as phone_sales,
            SUM(CASE WHEN o.category='ncme' THEN o.actual_price ELSE 0 END) as ncme_sales,
            SUM(CASE WHEN o.is_key_model=1 THEN 1 ELSE 0 END) as key_model_qty,
            SUM(CASE WHEN o.category='accessory' THEN o.actual_price ELSE 0 END) as accessory_sales,
            SUM(CASE WHEN o.trade_in_amount>0 THEN 1 ELSE 0 END) as trade_in_qty,
            SUM(o.trade_in_amount) as trade_in_total,
            SUM(CASE WHEN o.order_date=? THEN 1 ELSE 0 END) as today_orders,
            SUM(CASE WHEN o.order_date=? AND o.category='phone' THEN o.actual_price ELSE 0 END) as today_sales
        FROM sales_orders o
        JOIN staff sf ON o.staff_id = sf.id
        JOIN stores st ON sf.store_id = st.id
        WHERE {where}
        GROUP BY sf.id
        ORDER BY COALESCE(SUM(CASE WHEN o.category='phone' THEN o.actual_price ELSE 0 END), 0) DESC
        LIMIT ?
    """, [today, today] + params + [limit])

    rankings = [dict(r) for r in await cursor.fetchall()]

    # 为每个人附加实时提成预估
    for r in rankings:
        r["estimated_commission"] = await _calc_staff_order_commission(db, r["id"], month)

    return rankings


# ── 机型目录（供前端下拉选择） ──

@router.get("/model-catalog")
async def get_model_catalog(
    user: dict = Depends(get_current_user)
):
    """获取机型号目录（从历史订单 + 价格表中提取）"""
    db = await get_db()

    # 从价格表获取
    cursor = await db.execute("""
        SELECT DISTINCT model_code, spec, company_price
        FROM price_records
        WHERE model_code != ''
        ORDER BY model_code
    """)
    price_models = {r["model_code"]: {"spec": r["spec"], "price": r["company_price"] or 0}
                    for r in [dict(r) for r in await cursor.fetchall()]}

    # 从历史订单补充
    cursor = await db.execute("""
        SELECT DISTINCT model_code, product_name, spec, MAX(original_price) as price
        FROM sales_orders
        WHERE model_code != ''
        GROUP BY model_code
        ORDER BY model_code
    """)
    for r in await cursor.fetchall():
        r = dict(r)
        if r["model_code"] not in price_models:
            price_models[r["model_code"]] = {
                "spec": r.get("spec", ""),
                "price": r.get("price", 0),
                "name": r.get("product_name", "")
            }

    # 手动补充热门机型
    hot_models = {
        "SM-S9380": {"spec": "Galaxy S26 Ultra", "price": 9999},
        "SM-S9360": {"spec": "Galaxy S26+", "price": 7999},
        "SM-S9310": {"spec": "Galaxy S26", "price": 5999},
        "SM-F9660": {"spec": "Galaxy Z Fold7", "price": 13999},
        "SM-F7460": {"spec": "Galaxy Z Flip7", "price": 7499},
        "SM-W2621": {"spec": "Galaxy Watch7", "price": 1999},
        "SM-W2625": {"spec": "Galaxy Watch7 Ultra", "price": 2999},
        "SM-R510": {"spec": "Galaxy Buds3 Pro", "price": 1299},
        "SM-R400": {"spec": "Galaxy Buds3", "price": 899},
        "SM-X920": {"spec": "Galaxy Tab S10 Ultra", "price": 8499},
        "SM-X820": {"spec": "Galaxy Tab S10+", "price": 6499},
        "SM-X720": {"spec": "Galaxy Tab S10", "price": 4999},
        "SM-A5660": {"spec": "Galaxy A56", "price": 2999},
        "SM-A3660": {"spec": "Galaxy A36", "price": 1999},
        "SM-A2660": {"spec": "Galaxy A26", "price": 1499},
        "SM-R390": {"spec": "Galaxy Fit3", "price": 499},
        "SM-Q510": {"spec": "Galaxy Ring", "price": 2499},
    }
    for code, info in hot_models.items():
        if code not in price_models:
            price_models[code] = info

    return [
        {"model_code": code, "spec": info["spec"],
         "suggested_price": info.get("price", 0),
         "name": info.get("name", "")}
        for code, info in sorted(price_models.items())
    ]


# ── 删除订单（含回滚） ──

@router.delete("/{order_id}")
async def delete_order(
    order_id: int,
    user: dict = Depends(get_current_user)
):
    """删除订单并回滚聚合数据（需管理员或店长权限）"""
    if user.get("role") not in ("admin", "manager"):
        raise HTTPException(403, "需要店长或管理员权限")

    db = await get_db()
    cursor = await db.execute("SELECT * FROM sales_orders WHERE id=?", (order_id,))
    order = await cursor.fetchone()
    if not order:
        raise HTTPException(404, "订单不存在")

    order = dict(order)

    # 回滚 daily_sales（减去对应数据）
    await _rollback_daily_sales(db, order)

    # 回滚 staff_sales
    await _rollback_staff_sales(db, order)

    # 删除订单
    await db.execute("DELETE FROM sales_orders WHERE id=?", (order_id,))
    await db.commit()

    return {"status": "ok", "message": f"订单 #{order_id} 已删除，聚合数据已回滚"}


# ── 店员提成查询（实时，基于订单） ──

@router.get("/staff-commission/{staff_id}")
async def get_staff_order_commission(
    staff_id: int,
    month: str = None,
    user: dict = Depends(get_current_user)
):
    """获取店员实时提成（基于订单计算，不依赖 staff_sales 平均分摊）"""
    if not month:
        month = datetime.now().strftime("%Y-%m")

    db = await get_db()
    return await _calc_commission_detail(db, staff_id, month)


# ═══════════════════════════════════════════════════
#  内部辅助函数
# ═══════════════════════════════════════════════════

async def _upsert_daily_sales(db, store_id: int, date: str,
                              category: str, amount: float,
                              is_key_model: int, trade_in_amount: float):
    """聚合订单到 daily_sales"""
    cursor = await db.execute(
        "SELECT id FROM daily_sales WHERE store_id=? AND date=?",
        (store_id, date))
    existing = await cursor.fetchone()

    if existing:
        # 增量更新
        if category == "phone":
            await db.execute("""
                UPDATE daily_sales
                SET phone_sales = phone_sales + ?,
                    phone_qty = phone_qty + 1,
                    key_model_qty = key_model_qty + ?
                WHERE store_id=? AND date=?
            """, (amount, is_key_model, store_id, date))
        elif category == "ncme":
            await db.execute("""
                UPDATE daily_sales
                SET ncme_sales = ncme_sales + ?
                WHERE store_id=? AND date=?
            """, (amount, store_id, date))
        elif category == "accessory":
            await db.execute("""
                UPDATE daily_sales
                SET accessory_sales = accessory_sales + ?
                WHERE store_id=? AND date=?
            """, (amount, store_id, date))

        if trade_in_amount > 0:
            await db.execute("""
                UPDATE daily_sales
                SET trade_in_qty = trade_in_qty + 1
                WHERE store_id=? AND date=?
            """, (store_id, date))
    else:
        # 新建当天记录
        await db.execute("""
            INSERT INTO daily_sales
            (date, store_id, phone_sales, ncme_sales, phone_qty,
             key_model_qty, accessory_sales, trade_in_qty, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual')
        """, (
            date, store_id,
            amount if category == "phone" else 0,
            amount if category == "ncme" else 0,
            1 if category == "phone" else 0,
            is_key_model,
            amount if category == "accessory" else 0,
            1 if trade_in_amount > 0 else 0,
        ))


async def _upsert_staff_sales(db, staff_id: int, store_id: int,
                               date: str, category: str,
                               amount: float, is_key_model: int,
                               trade_in_amount: float):
    """写入/更新店员销售记录，并计算提成"""
    cursor = await db.execute(
        "SELECT id FROM staff_sales WHERE staff_id=? AND store_id=? AND sale_date=?",
        (staff_id, store_id, date))
    existing = await cursor.fetchone()

    if existing:
        if category == "phone":
            await db.execute("""
                UPDATE staff_sales
                SET phone_sales = phone_sales + ?,
                    phone_qty = phone_qty + 1,
                    key_model_qty = key_model_qty + ?
                WHERE staff_id=? AND store_id=? AND sale_date=?
            """, (amount, is_key_model, staff_id, store_id, date))
        elif category == "ncme":
            await db.execute("""
                UPDATE staff_sales
                SET ncme_sales = ncme_sales + ?
                WHERE staff_id=? AND store_id=? AND sale_date=?
            """, (amount, staff_id, store_id, date))
        elif category == "accessory":
            await db.execute("""
                UPDATE staff_sales
                SET accessory_sales = accessory_sales + ?
                WHERE staff_id=? AND store_id=? AND sale_date=?
            """, (amount, staff_id, store_id, date))
        if trade_in_amount > 0:
            await db.execute("""
                UPDATE staff_sales
                SET trade_in_qty = trade_in_qty + 1
                WHERE staff_id=? AND store_id=? AND sale_date=?
            """, (staff_id, store_id, date))
    else:
        await db.execute("""
            INSERT INTO staff_sales
            (staff_id, store_id, sale_date, phone_sales, ncme_sales,
             phone_qty, key_model_qty, accessory_sales, trade_in_qty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            staff_id, store_id, date,
            amount if category == "phone" else 0,
            amount if category == "ncme" else 0,
            1 if category == "phone" else 0,
            is_key_model,
            amount if category == "accessory" else 0,
            1 if trade_in_amount > 0 else 0,
        ))

    # 重新计算该店员当日提成
    await _recalc_commission(db, staff_id, date)


async def _recalc_commission(db, staff_id: int, date: str):
    """根据提成规则逐单重新计算店员指定日期的提成"""
    cursor2 = await db.execute("SELECT * FROM commission_rules WHERE is_active=1")
    rules = [dict(r) for r in await cursor2.fetchall()]

    # 逐单计算提成（支持 model_keyword 过滤）
    cursor3 = await db.execute(
        "SELECT model_code, product_name, category, actual_price, trade_in_amount FROM sales_orders WHERE staff_id=? AND order_date=?",
        (staff_id, date))
    orders = [dict(r) for r in await cursor3.fetchall()]

    total = 0.0
    for order in orders:
        cat = order["category"]
        for rule in rules:
            # model_keyword 过滤
            if not _rule_matches_order(rule.get("model_keyword", ""),
                                       order.get("model_code", ""),
                                       order.get("product_name", "")):
                continue

            ptype = rule["product_type"]
            if ptype == "phone" and cat == "phone" and rule["commission_type"] == "fixed":
                total += rule["commission_fixed"] or 0
            elif ptype == "ncme" and cat == "ncme" and rule["commission_type"] == "percentage":
                total += (order["actual_price"] or 0) * (rule["commission_rate"] or 0)
            elif ptype == "accessory" and cat == "accessory" and rule["commission_type"] == "percentage":
                total += (order["actual_price"] or 0) * (rule["commission_rate"] or 0)
            elif ptype == "trade_in" and rule["commission_type"] == "fixed":
                if (order.get("trade_in_amount") or 0) > 0:
                    total += rule["commission_fixed"] or 0

    await db.execute(
        "UPDATE staff_sales SET commission=? WHERE staff_id=? AND sale_date=?",
        (round(total, 2), staff_id, date))


async def _link_member_and_purchase(
    db, phone: str, member_name: str, store_id: int,
    order_id: int, model_code: str, product_name: str,
    spec: str, color: str, imei: str, amount: float,
    trade_in_model: str, trade_in_amount: float, date: str
) -> int:
    """根据手机号匹配或创建会员，并添加购买记录。返回 member_id"""
    # 查找已有会员
    cursor = await db.execute("SELECT id, name, total_spent, points FROM members WHERE phone=?", (phone,))
    member = await cursor.fetchone()

    if member:
        member_id = member[0]
        # 更新累计消费和积分
        points_earned = int(amount)  # 1元=1积分
        await db.execute("""
            UPDATE members
            SET total_spent = total_spent + ?,
                points = points + ?,
                store_id = COALESCE(store_id, ?)
            WHERE id=?
        """, (amount, points_earned, store_id, member_id))
    else:
        # 创建新会员
        name = member_name if member_name and member_name.strip() else f"客户{phone[-4:]}"
        cursor = await db.execute("""
            INSERT INTO members (name, phone, store_id, join_date, total_spent, points)
            VALUES (?,?,?,?,?,?)
        """, (name, phone, store_id, date, amount, int(amount)))
        member_id = cursor.lastrowid

    # 添加购买记录
    await db.execute("""
        INSERT INTO member_purchases
        (member_id, store_id, model_code, product_info, spec, color, imei,
         amount, points_earned, trade_in_model, trade_in_amount, purchase_date)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        member_id, store_id, model_code,
        product_name or model_code, spec, color, imei,
        amount, int(amount), trade_in_model, trade_in_amount, date
    ))

    return member_id


async def _rollback_daily_sales(db, order: dict):
    """回滚 daily_sales 聚合"""
    store_id = order["store_id"]
    date = order["order_date"]
    category = order["category"]
    amount = order["actual_price"]

    if category == "phone":
        await db.execute("""
            UPDATE daily_sales
            SET phone_sales = MAX(0, phone_sales - ?),
                phone_qty = MAX(0, phone_qty - 1),
                key_model_qty = MAX(0, key_model_qty - ?)
            WHERE store_id=? AND date=?
        """, (amount, order.get("is_key_model", 0), store_id, date))
    elif category == "ncme":
        await db.execute("""
            UPDATE daily_sales
            SET ncme_sales = MAX(0, ncme_sales - ?)
            WHERE store_id=? AND date=?
        """, (amount, store_id, date))
    elif category == "accessory":
        await db.execute("""
            UPDATE daily_sales
            SET accessory_sales = MAX(0, accessory_sales - ?)
            WHERE store_id=? AND date=?
        """, (amount, store_id, date))

    trade_in = order.get("trade_in_amount", 0) or 0
    if trade_in > 0:
        await db.execute("""
            UPDATE daily_sales
            SET trade_in_qty = MAX(0, trade_in_qty - 1)
            WHERE store_id=? AND date=?
        """, (store_id, date))


async def _rollback_staff_sales(db, order: dict):
    """回滚 staff_sales"""
    staff_id = order["staff_id"]
    store_id = order["store_id"]
    date = order["order_date"]
    category = order["category"]
    amount = order["actual_price"]

    if category == "phone":
        await db.execute("""
            UPDATE staff_sales
            SET phone_sales = MAX(0, phone_sales - ?),
                phone_qty = MAX(0, phone_qty - 1),
                key_model_qty = MAX(0, key_model_qty - ?)
            WHERE staff_id=? AND store_id=? AND sale_date=?
        """, (amount, order.get("is_key_model", 0), staff_id, store_id, date))
    elif category == "ncme":
        await db.execute("""
            UPDATE staff_sales
            SET ncme_sales = MAX(0, ncme_sales - ?)
            WHERE staff_id=? AND store_id=? AND sale_date=?
        """, (amount, staff_id, store_id, date))
    elif category == "accessory":
        await db.execute("""
            UPDATE staff_sales
            SET accessory_sales = MAX(0, accessory_sales - ?)
            WHERE staff_id=? AND store_id=? AND sale_date=?
        """, (amount, staff_id, store_id, date))

    trade_in = order.get("trade_in_amount", 0) or 0
    if trade_in > 0:
        await db.execute("""
            UPDATE staff_sales
            SET trade_in_qty = MAX(0, trade_in_qty - 1)
            WHERE staff_id=? AND store_id=? AND sale_date=?
        """, (staff_id, store_id, date))

    # 重新计算提成
    await _recalc_commission(db, staff_id, date)


async def _calc_staff_order_commission(db, staff_id: int, month: str) -> float:
    """基于订单数据逐单计算店员提成（支持 model_keyword 过滤）"""
    cursor = await db.execute(
        "SELECT model_code, product_name, category, actual_price, trade_in_amount FROM sales_orders WHERE staff_id=? AND order_date LIKE ?",
        (staff_id, month + "%"))
    orders = [dict(r) for r in await cursor.fetchall()]

    if not orders:
        return 0

    cursor2 = await db.execute("SELECT * FROM commission_rules WHERE is_active=1")
    rules = [dict(r) for r in await cursor2.fetchall()]

    total = 0.0
    for order in orders:
        cat = order["category"]
        for rule in rules:
            if not _rule_matches_order(rule.get("model_keyword", ""),
                                       order.get("model_code", ""),
                                       order.get("product_name", "")):
                continue
            ptype = rule["product_type"]
            if ptype == "phone" and cat == "phone" and rule["commission_type"] == "fixed":
                total += rule["commission_fixed"] or 0
            elif ptype == "ncme" and cat == "ncme" and rule["commission_type"] == "percentage":
                total += (order["actual_price"] or 0) * (rule["commission_rate"] or 0)
            elif ptype == "accessory" and cat == "accessory" and rule["commission_type"] == "percentage":
                total += (order["actual_price"] or 0) * (rule["commission_rate"] or 0)
            elif ptype == "trade_in" and rule["commission_type"] == "fixed":
                if (order.get("trade_in_amount") or 0) > 0:
                    total += rule["commission_fixed"] or 0

    return round(total, 2)


async def _calc_commission_detail(db, staff_id: int, month: str) -> dict:
    """计算店员提成明细（含 breakdown，支持 model_keyword 过滤）"""
    cursor = await db.execute(
        "SELECT model_code, product_name, category, actual_price, trade_in_amount FROM sales_orders WHERE staff_id=? AND order_date LIKE ?",
        (staff_id, month + "%"))
    orders = [dict(r) for r in await cursor.fetchall()]

    if not orders:
        return {"phone_qty": 0, "breakdown": [], "total": 0}

    cursor2 = await db.execute("SELECT * FROM commission_rules WHERE is_active=1")
    rules = [dict(r) for r in await cursor2.fetchall()]

    phone_qty = sum(1 for o in orders if o["category"] == "phone")
    ncme_sales = sum(o["actual_price"] for o in orders if o["category"] == "ncme")

    detail = {}  # rule_name -> amount
    total = 0.0

    for order in orders:
        cat = order["category"]
        for rule in rules:
            if not _rule_matches_order(rule.get("model_keyword", ""),
                                       order.get("model_code", ""),
                                       order.get("product_name", "")):
                continue
            amount = 0.0
            ptype = rule["product_type"]
            if ptype == "phone" and cat == "phone" and rule["commission_type"] == "fixed":
                amount = rule["commission_fixed"] or 0
            elif ptype == "ncme" and cat == "ncme" and rule["commission_type"] == "percentage":
                amount = (order["actual_price"] or 0) * (rule["commission_rate"] or 0)
            elif ptype == "accessory" and cat == "accessory" and rule["commission_type"] == "percentage":
                amount = (order["actual_price"] or 0) * (rule["commission_rate"] or 0)
            elif ptype == "trade_in" and rule["commission_type"] == "fixed":
                if (order.get("trade_in_amount") or 0) > 0:
                    amount = rule["commission_fixed"] or 0

            if amount > 0:
                name = rule["rule_name"]
                detail[name] = detail.get(name, 0) + amount
                total += amount

    breakdown = [{"rule_name": k, "type": "", "amount": round(v, 2)} for k, v in detail.items()]

    return {
        "phone_qty": phone_qty,
        "ncme_sales": round(ncme_sales, 2),
        "breakdown": breakdown,
        "total": round(total, 2)
    }
