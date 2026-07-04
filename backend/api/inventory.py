"""库存监控 API - 完整版（含预警引擎 + Excel上传导入）"""
import os, re, tempfile, collections
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from backend.dependencies import get_current_user, require_admin, require_manager_or_admin
from pydantic import BaseModel
from typing import List, Optional
import aiosqlite
import xlrd
from backend.models.database import get_db

router = APIRouter()

# 四系列机型定义
MODEL_SERIES = {
    "S26": {"models": ["S9420", "S9470", "S9480"], "name": "Galaxy S26系列"},
    "FOLD7": {"models": ["ZFOLD7"], "name": "Galaxy Z Fold7"},
    "FLIP7": {"models": ["ZFLIP7"], "name": "Galaxy Z Flip7"},
    "W26": {"models": ["W26"], "name": "Galaxy W26"},
}


def get_series(model_code: str) -> str:
    """根据型号编码判断系列"""
    for series, info in MODEL_SERIES.items():
        if model_code in info["models"]:
            return series
    return ""


@router.get("/status")
async def get_inventory_status(
    user: dict = Depends(get_current_user)
):
    """获取库存状态（热力图数据），按系列分组"""

    db = await get_db()
    # 门店列表
    cursor = await db.execute("SELECT id, name, province FROM stores WHERE is_active=1 ORDER BY sort_order")
    stores = await cursor.fetchall()

    # 全部库存
    cursor = await db.execute("""
        SELECT i.store_id, s.name as store_name, i.model_code, i.color, i.spec, i.qty, i.updated_at
        FROM inventory i JOIN stores s ON i.store_id = s.id
        WHERE s.is_active = 1
        ORDER BY s.sort_order, i.model_code, i.color, i.spec
    """)
    inventory = await cursor.fetchall()

    # 预警规则
    cursor = await db.execute("SELECT * FROM alert_rules WHERE is_active=1")
    rules = await cursor.fetchall()

    # 按系列组织
    by_series = {}
    for series_name in MODEL_SERIES:
        by_series[series_name] = {
            "name": MODEL_SERIES[series_name]["name"],
            "stores": []
        }

    # 构建每个门店在每个系列的库存矩阵
    for store in stores:
        store_inv = [dict(i) for i in inventory if i["store_id"] == store["id"]]
        for series_name, series_info in MODEL_SERIES.items():
            series_items = [i for i in store_inv if i["model_code"] in series_info["models"]]
            # 计算门店级汇总
            store_total = sum(i["qty"] for i in series_items)
            by_series[series_name]["stores"].append({
                "store_id": store["id"],
                "store_name": store["name"],
                "province": store["province"],
                "items": series_items,
                "total_qty": store_total,
            })

    return {
        "stores": [dict(s) for s in stores],
        "series": by_series,
        "rules": [dict(r) for r in rules]
    }


@router.get("/alerts")
async def get_inventory_alerts(
    user: dict = Depends(get_current_user)
):
    """获取库存预警列表（完整规则引擎）"""

    db = await get_db()
    # 获取预警规则
    cursor = await db.execute("SELECT * FROM alert_rules WHERE is_active=1")
    rules = await cursor.fetchall()
    rule_map = {r["model_series"]: dict(r) for r in rules}

    # 获取全部库存
    cursor = await db.execute("""
        SELECT i.*, s.name as store_name
        FROM inventory i JOIN stores s ON i.store_id = s.id
        WHERE s.is_active = 1
    """)
    all_inv = await cursor.fetchall()

    alerts = []

    # S26系列：每店每色每规格 ≥ 1台
    if "S26" in rule_map and rule_map["S26"]["rule_type"] == "per_store_color_spec":
        threshold = rule_map["S26"]["threshold"]
        for inv in all_inv:
            series = get_series(inv["model_code"])
            if series != "S26":
                continue
            if inv["qty"] < threshold:
                alerts.append({
                    "series": "S26",
                    "level": "danger" if inv["qty"] == 0 else "warning",
                    "store": inv["store_name"],
                    "model": inv["model_code"],
                    "color": inv["color"],
                    "spec": inv["spec"],
                    "qty": inv["qty"],
                    "threshold": threshold,
                    "message": f"{inv['store_name']} {inv['model_code']} {inv['color']} {inv['spec']} 仅{inv['qty']}台（需≥{threshold}台）"
                })

    # FOLD7系列：每店总量 ≥ 2台
    if "FOLD7" in rule_map and rule_map["FOLD7"]["rule_type"] == "per_store":
        threshold = rule_map["FOLD7"]["threshold"]
        fold7_inv = [dict(i) for i in all_inv if get_series(i["model_code"]) == "FOLD7"]
        # 按门店汇总
        from collections import defaultdict
        store_totals = defaultdict(int)
        for item in fold7_inv:
            store_totals[item["store_name"]] += item["qty"]
        for store_name, total in store_totals.items():
            if total < threshold:
                alerts.append({
                    "series": "FOLD7",
                    "level": "danger" if total == 0 else "warning",
                    "store": store_name,
                    "model": "ZFOLD7",
                    "color": "",
                    "spec": "全规格合计",
                    "qty": total,
                    "threshold": threshold,
                    "message": f"{store_name} Z Fold7 全规格合计仅{total}台（需≥{threshold}台）"
                })

    # FLIP7系列：每店总量 ≥ 1台
    if "FLIP7" in rule_map and rule_map["FLIP7"]["rule_type"] == "per_store":
        threshold = rule_map["FLIP7"]["threshold"]
        flip7_inv = [dict(i) for i in all_inv if get_series(i["model_code"]) == "FLIP7"]
        from collections import defaultdict
        store_totals = defaultdict(int)
        for item in flip7_inv:
            store_totals[item["store_name"]] += item["qty"]
        for store_name, total in store_totals.items():
            if total < threshold:
                alerts.append({
                    "series": "FLIP7",
                    "level": "danger" if total == 0 else "warning",
                    "store": store_name,
                    "model": "ZFLIP7",
                    "color": "",
                    "spec": "全规格合计",
                    "qty": total,
                    "threshold": threshold,
                    "message": f"{store_name} Z Flip7 全规格合计仅{total}台（需≥{threshold}台）"
                })

    # W26系列：全渠道总量 ≥ 10台
    if "W26" in rule_map and rule_map["W26"]["rule_type"] == "total":
        threshold = rule_map["W26"]["threshold"]
        w26_inv = [dict(i) for i in all_inv if get_series(i["model_code"]) == "W26"]
        total_w26 = sum(i["qty"] for i in w26_inv)
        if total_w26 < threshold:
            alerts.append({
                "series": "W26",
                "level": "danger" if total_w26 == 0 else "warning",
                "store": "全渠道",
                "model": "W26",
                "color": "",
                "spec": "全渠道合计",
                "qty": total_w26,
                "threshold": threshold,
                "message": f"W26 全渠道合计仅{total_w26}台（需≥{threshold}台）"
            })

    # 按严重程度排序
    alerts.sort(key=lambda x: (0 if x["level"] == "danger" else 1, x["series"], x["store"]))

    return {"alerts": alerts, "total": len(alerts)}


@router.get("/summary")
async def get_inventory_summary(
    user: dict = Depends(get_current_user)
):
    """获取库存汇总（用于Dashboard）"""

    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) as total FROM inventory WHERE qty > 0")
    total_items = (await cursor.fetchone())["total"]

    cursor = await db.execute("SELECT COUNT(DISTINCT store_id) as stores FROM inventory WHERE qty > 0")
    active_stores = (await cursor.fetchone())["stores"]

    # 预警数量
    cursor = await db.execute("SELECT COUNT(*) FROM alert_rules WHERE is_active=1")
    rule_count = (await cursor.fetchone())[0]

    # 总库存量
    cursor = await db.execute("SELECT SUM(qty) as total_qty FROM inventory")
    total_qty = (await cursor.fetchone())["total_qty"] or 0

    return {
        "total_items": total_items,
        "active_stores": active_stores,
        "alert_rule_count": rule_count,
        "total_qty": total_qty
    }


# ─── 新增：库存趋势与智能建议 ─────────────────────────────

@router.get("/trend")
async def get_inventory_trend(
    store_id: int = None,
    model_series: str = "S26",
    days: int = 30,
    user: dict = Depends(get_current_user)
):
    """库存变化趋势：基于 eBoss 同步日志推断库存变化"""
    db = await get_db()

    # 获取每日销售数据作为消耗量
    models = MODEL_SERIES.get(model_series, {}).get("models", [])
    if not models:
        return {"error": f"未知系列: {model_series}"}

    from datetime import datetime, timedelta
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 查询每日销售中这些机型的销量（用 key_model 来近似）
    placeholders = ",".join(["?" for _ in models])
    store_cond = "AND store_id = ?" if store_id else ""
    params = [start_date, end_date] + models
    if store_id:
        params.append(store_id)

    sql = f"""
        SELECT date, SUM(phone_qty) as daily_sales, SUM(key_model_qty) as daily_km
        FROM daily_sales
        WHERE date >= ? AND date < ?
        AND date IN (
            SELECT date FROM daily_sales 
            WHERE date >= ? AND date < ? 
            GROUP BY date
        )
        {store_cond}
        GROUP BY date ORDER BY date
    """
    # simpler query:
    sql_simple = f"""
        SELECT date, SUM(phone_qty) as daily_qty, SUM(key_model_qty) as daily_km,
               SUM(phone_sales) as daily_sales_amt
        FROM daily_sales
        WHERE date >= ? AND date < ? {store_cond}
        GROUP BY date ORDER BY date
    """
    params_simple = [start_date, end_date]
    if store_id:
        params_simple.append(store_id)

    cur = await db.execute(sql_simple, tuple(params_simple))
    rows = await cur.fetchall()

    # 当前库存
    inv_sql = f"""
        SELECT s.name as store_name, SUM(i.qty) as total_stock, i.store_id
        FROM inventory i JOIN stores s ON i.store_id = s.id
        WHERE s.is_active = 1
    """
    inv_params = []
    if store_id:
        inv_sql += " AND i.store_id = ?"
        inv_params.append(store_id)
    inv_sql += " GROUP BY i.store_id ORDER BY s.sort_order"
    cur = await db.execute(inv_sql, tuple(inv_params))
    inv_rows = await cur.fetchall()

    # 计算日均销量和库存可销天数
    trends = [{"date": r["date"], "daily_qty": r["daily_qty"], "daily_km": r["daily_km"], "sales_amt": r["daily_sales_amt"]} for r in rows]

    total_qty = sum(r["daily_qty"] for r in rows)
    avg_daily = round(total_qty / max(len(rows), 1), 1)

    stock_summary = []
    for inv in inv_rows:
        stock = inv["total_stock"] or 0
        days_left = round(stock / avg_daily, 1) if avg_daily > 0 else 999
        status = "critical" if days_left < 3 else "warning" if days_left < 7 else "normal"
        stock_summary.append({
            "store_id": inv["store_id"],
            "store_name": inv["store_name"],
            "current_stock": stock,
            "estimated_days_left": days_left,
            "status": status,
        })

    return {
        "model_series": model_series,
        "avg_daily_sales": avg_daily,
        "daily_trend": trends,
        "stock_summary": stock_summary,
        "suggestion": f"日均销售约{avg_daily}台，建议各门店保持至少{max(int(avg_daily * 7), 1)}台库存（7天安全量）"
    }


@router.get("/suggest")
async def get_restock_suggestions(
    model_series: str = None,
    user: dict = Depends(get_current_user)
):
    """智能补货建议：基于销售速度和当前库存"""
    db = await get_db()

    from datetime import datetime, timedelta
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    # 近7天各店日均销量
    cur = await db.execute("""
        SELECT s.id as store_id, s.name as store_name,
               COALESCE(SUM(ds.phone_qty), 0) as total_qty,
               COUNT(DISTINCT ds.date) as active_days
        FROM stores s
        LEFT JOIN daily_sales ds ON ds.store_id = s.id AND ds.date >= ?
        WHERE s.is_active = 1
        GROUP BY s.id ORDER BY s.sort_order
    """, (week_ago,))
    sales_velocity = {r["store_id"]: dict(r) for r in await cur.fetchall()}

    # 当前库存（按系列）
    series_filter = ""
    series_params = []
    if model_series and model_series in MODEL_SERIES:
        models = MODEL_SERIES[model_series]["models"]
        placeholders = ",".join(["?" for _ in models])
        series_filter = f"AND i.model_code IN ({placeholders})"
        series_params = models

    cur = await db.execute(f"""
        SELECT i.store_id, s.name as store_name, SUM(i.qty) as stock,
               i.model_code, i.color, i.spec, i.qty
        FROM inventory i JOIN stores s ON i.store_id = s.id
        WHERE s.is_active = 1 {series_filter}
        GROUP BY i.store_id, i.model_code, i.color, i.spec
    """, tuple(series_params))
    inv_rows = await cur.fetchall()

    # by store summary
    store_stock = {}
    for r in inv_rows:
        sid = r["store_id"]
        if sid not in store_stock:
            store_stock[sid] = {"store_name": r["store_name"], "total_stock": 0, "items": []}
        store_stock[sid]["total_stock"] += r["qty"] or 0
        store_stock[sid]["items"].append({
            "model": r["model_code"], "color": r["color"], "spec": r["spec"], "qty": r["qty"]
        })

    suggestions = []
    for sid, sv in sales_velocity.items():
        name = sv["store_name"]
        active_days = max(sv["active_days"], 1)
        daily_avg = round(sv["total_qty"] / active_days, 1)
        stock_data = store_stock.get(sid, {"total_stock": 0, "items": []})
        current = stock_data["total_stock"]
        days_left = round(current / daily_avg, 1) if daily_avg > 0 else 999

        need = 0
        if days_left < 3:
            priority = "urgent"
            need = max(int(daily_avg * 7 - current), 1)
            action = f"紧急补货！库存仅够{days_left}天"
        elif days_left < 7:
            priority = "warning"
            need = max(int(daily_avg * 3 - current), 1)
            action = f"建议补货，库存仅够{days_left}天"
        elif days_left < 14:
            priority = "notice"
            action = f"库存可销{days_left}天，可考虑补货"
        else:
            priority = "ok"
            action = f"库存充足（可销{days_left}天）"

        suggestions.append({
            "store_id": sid,
            "store_name": name,
            "daily_avg_sales": daily_avg,
            "current_stock": current,
            "days_left": days_left,
            "suggested_restock": need,
            "priority": priority,
            "action": action,
        })

    # Sort by priority
    prio_order = {"urgent": 0, "warning": 1, "notice": 2, "ok": 3}
    suggestions.sort(key=lambda x: prio_order.get(x["priority"], 9))

    return {
        "generated_at": today,
        "model_series": model_series or "全部机型",
        "suggestions": suggestions,
    }


class InventoryItem(BaseModel):
    store: str
    model_code: str
    color: str = ""
    spec: str = ""
    qty: int = 0


@router.post("/import")
async def import_inventory(data: List[InventoryItem],
    user: dict = Depends(get_current_user)):
    """导入库存数据（admin/manager）"""
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    imported = 0
    for item in data:
        store_name = item.store
        model_code = item.model_code

        if not store_name or not model_code:
            continue

        # 模糊匹配门店名
        cursor = await db.execute("SELECT id FROM stores WHERE name LIKE ?",
                                   (f"%{store_name}%",))
        store = await cursor.fetchone()
        if not store:
            continue

        await db.execute("""
            INSERT INTO inventory (store_id, model_code, color, spec, qty, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(store_id, model_code, color, spec)
            DO UPDATE SET qty=excluded.qty, updated_at=excluded.updated_at
        """, (store["id"], model_code, item.color, item.spec, item.qty))
        imported += 1

    await db.commit()
    return {"status": "ok", "imported": imported}


# ===== eBoss Excel 解析函数 =====
FOUR_SERIES = {
    'S9420': 'S26', 'S9470': 'S26', 'S9480': 'S26',
    'ZFOLD7': 'FOLD7', 'ZFLIP7': 'FLIP7', 'W26': 'W26',
}

def get_series_from_model(model_str: str) -> str:
    if not model_str:
        return ""
    for key, series in FOUR_SERIES.items():
        if key in model_str.upper().replace(" ", ""):
            return series
    return ""


def parse_eboss_xls(file_path: str, sheet_index: int = 2) -> list:
    """
    解析 eBoss .xls 库存表，返回记录列表
    支持两种格式：
    1. 旧格式（多Sheet）：Sheet2，列0=门店，列2=机型，列3=规格，列4=颜色，列5=库存量
    2. 新格式（单Sheet明细）：Sheet0，每台设备一行含IMEI，
       列1=店仓名称(合并)，列5=机型，列7=颜色，列8=规格，需按组合计数
    """
    import re
    from collections import defaultdict

    wb = xlrd.open_workbook(file_path, formatting_info=True)

    # 自动检测格式：如果 sheet_index 指定的 sheet 不存在，回退到 sheet 0
    if wb.nsheets > sheet_index:
        sh = wb.sheet_by_index(sheet_index)
    else:
        sh = wb.sheet_by_index(0)

    # 构建合并单元格映射
    merged = {}
    for rlo, rhi, clo, chi in sh.merged_cells:
        for r in range(rlo, rhi):
            for c in range(clo, chi):
                if r == rlo and c == clo:
                    continue
                merged[(r, c)] = (rlo, clo)

    def get_val(r, c):
        if (r, c) in merged:
            return sh.cell_value(*merged[(r, c)])
        if r < sh.nrows and c < sh.ncols:
            return sh.cell_value(r, c)
        return ""

    # 检测格式：如果 Col0 有门店名且 Col5 是数值型库存量 → 旧格式
    # 如果 Col1 有门店名且 Col5 有型号编码 → 新明细格式
    test_c0 = str(get_val(1, 0)).strip()
    test_c1 = str(get_val(1, 1)).strip()
    test_c5 = str(get_val(1, 5)).strip()

    # 旧格式检测：Col0 有门店名，Col5 是数值
    is_old_format = (len(test_c0) > 3 and not any(k in test_c5.upper() for k in
                      ('S9420','S9470','S9480','ZFOLD7','ZFLIP7','W26')))

    if is_old_format:
        return _parse_eboss_xls_summary(sh, get_val)
    else:
        return _parse_eboss_xls_detail(sh, get_val)


def _parse_eboss_xls_summary(sh, get_val) -> list:
    """旧格式：Sheet2 汇总型（Col0=门店，Col2=机型，Col3=规格，Col4=颜色，Col5=库存量）"""
    records = []
    cur_store, cur_model, cur_color, cur_series = "", "", "", ""

    for r in range(1, sh.nrows):
        c0 = str(get_val(r, 0)).strip()
        c2 = str(get_val(r, 2)).strip()
        c3 = str(get_val(r, 3)).strip()
        c4 = str(get_val(r, 4)).strip()
        c5 = get_val(r, 5)

        if c0 and c0 != "合计" and len(c0) > 1:
            cur_store = c0
        if c2 and c2 != "合计":
            cur_model = c2
            cur_series = get_series_from_model(c2)
            cur_color = ""
        if c4 and c4 != "合计":
            cur_color = c4
        if c2 == "合计" or c0 == "合计":
            continue
        if not cur_series:
            continue
        if c3 and c3 != "合计":
            try:
                qty = int(float(c5)) if c5 != "" else 0
            except (ValueError, TypeError):
                qty = 0
            if qty > 0:
                records.append({
                    "store_name": cur_store,
                    "model_code": _normalize_model_code(cur_model),
                    "series": cur_series,
                    "color": cur_color,
                    "spec": c3,
                    "qty": qty,
                })
    return records


def _parse_eboss_xls_detail(sh, get_val) -> list:
    """新格式：明细型（每台设备一行，Col1=门店，Col5=机型，Col7=颜色，Col8=规格）"""
    from collections import defaultdict
    FOUR_SERIES_PATTERNS = ["S9420", "S9470", "S9480", "ZFOLD7", "ZFLIP7", "W26"]

    counts = defaultdict(int)
    cur_store = ""

    for r in range(1, sh.nrows):
        store_val = str(get_val(r, 1)).strip()
        if store_val and store_val != "合计" and len(store_val) > 2:
            cur_store = store_val

        model_raw = str(get_val(r, 5)).upper().replace(" ", "")
        if not model_raw:
            continue

        matched_code = None
        for pattern in FOUR_SERIES_PATTERNS:
            if pattern in model_raw:
                matched_code = pattern
                break
        if not matched_code:
            continue

        spec_val = str(get_val(r, 8)).strip()
        inv_val = str(get_val(r, min(9, sh.ncols - 1))).strip() if sh.ncols > 9 else ""
        if "合计" in spec_val or "合计" in inv_val:
            continue

        color_val = str(get_val(r, 7)).strip()
        key = (cur_store, matched_code, color_val, spec_val)
        counts[key] += 1

    records = []
    for (store_name, model_code, color, spec), qty in counts.items():
        series = get_series_from_model(model_code)
        records.append({
            "store_name": store_name,
            "model_code": model_code,
            "series": series,
            "color": color,
            "spec": spec,
            "qty": qty,
        })
    return records


def _normalize_model_code(model_str: str) -> str:
    """从机型全名提取标准编码，如 '三星S26(S9420)5G' -> 'S9420'"""
    import re
    m = re.search(r"(S\d{4}|ZFOLD\d+|ZFLIP\d+|W\d+)", model_str.upper().replace(" ", ""))
    if m:
        return m.group(1)
    # 尝试直接匹配
    for key in FOUR_SERIES:
        if key in model_str.upper().replace(" ", ""):
            return key
    return model_str


# ===== 门店名称模糊匹配 =====
STORE_ALIAS = {
    "万象城": "万象城三星授权旗舰店",
    "万象汇": "华润万象汇三星授权体验店",
    "兴义": "兴义梦乐城三星店",
    "遵义": "遵义吾悦三星授权店",
    "遵义吾悦": "遵义吾悦三星授权店",
    "曲靖": "曲靖万达三星授权店",
    "六盘水": "六盘水三星授权体验店",
    "龙湾": "龙湾万达三星专卖店",
    "昭通": "云南昭通三星授权体验店",
    "清镇": "清镇吾悦三星授权体验店",
    "安顺": "安顺万绿城三星授权体验店",
}


def match_store(store_name: str, db_stores: list) -> int:
    """模糊匹配门店名，返回 store_id，未匹配返回 None"""
    if not store_name:
        return None
    name = store_name.strip()
    # 精确匹配
    for s in db_stores:
        if s["name"] == name:
            return s["id"]
    # 别名匹配
    for alias, full_name in STORE_ALIAS.items():
        if alias in name or alias in full_name:
            for s in db_stores:
                if s["name"] == full_name:
                    return s["id"]
    # 关键词匹配
    for s in db_stores:
        if name in s["name"] or s["name"] in name:
            return s["id"]
    return None


@router.post("/upload")
async def upload_inventory_excel(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)):
    """
    上传 eBoss .xls 库存表，解析并导入数据库
    返回：解析记录数、导入记录数、预警信息
    """
    from backend.models.database import get_db

    # 保存上传文件到临时位置
    suffix = ".xls"
    if file.filename:
        if file.filename.lower().endswith(".xlsx"):
            suffix = ".xlsx"
        elif file.filename.lower().endswith(".xls"):
            suffix = ".xls"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # 解析
        records = parse_eboss_xls(tmp_path)
        if not records:
            return {"status": "warning", "message": "未解析到有效库存记录，请检查文件格式"}

        # 导入数据库
        db = await get_db()
        cursor = await db.execute("SELECT id, name FROM stores WHERE is_active=1")
        stores = [dict(r) for r in await cursor.fetchall()]

        imported = 0
        skipped = 0
        for rec in records:
            store_id = match_store(rec["store_name"], stores)
            if not store_id:
                skipped += 1
                continue
            await db.execute("""
                INSERT INTO inventory (store_id, model_code, color, spec, qty, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
                ON CONFLICT(store_id, model_code, color, spec)
                DO UPDATE SET qty=excluded.qty, updated_at=excluded.updated_at
            """, (store_id, rec["model_code"], rec["color"], rec["spec"], rec["qty"]))
            imported += 1

        await db.commit()

        # 统计预警
        from collections import defaultdict
        store_qty = defaultdict(lambda: defaultdict(int))
        for rec in records:
            store_id = match_store(rec["store_name"], stores)
            if store_id:
                store_qty[store_id][rec["series"]] += rec["qty"]

        return {
            "status": "ok",
            "parsed": len(records),
            "imported": imported,
            "skipped": skipped,
            "message": f"成功导入 {imported} 条库存记录"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败：{str(e)}")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
