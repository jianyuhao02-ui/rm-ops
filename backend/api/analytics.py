"""
数据分析 API - 提供报表统计、趋势分析、数据导出
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from backend.models.database import get_db
from backend.dependencies import get_current_user, require_admin, require_manager_or_admin

router = APIRouter()


@router.get("/overview")
async def get_business_overview(
    user: dict = Depends(get_current_user),
    year: Optional[int] = None,
    month: Optional[int] = None
):
    """
    业务总览 - 返回整体经营指标
    包括：销售总额、同比增长、门店排名、品类占比
    """
    import datetime
    now = datetime.datetime.now()
    year = year or now.year
    month = month or now.month

    db = await get_db()
    month_start = f"{year}-{month:02d}-01"
    next_month = f"{year}-{month + 1:02d}-01" if month < 12 else f"{year + 1}-01-01"

    # 本月销售汇总
    cursor = await db.execute("""
        SELECT
            SUM(phone_sales) as total_phone,
            SUM(ncme_sales) as total_ncme,
            SUM(phone_qty) as total_qty,
            SUM(key_model_qty) as total_km,
            SUM(accessory_sales) as total_acc,
            SUM(trade_in_qty) as total_ti,
            COUNT(DISTINCT store_id) as store_count,
            COUNT(DISTINCT date) as active_days
        FROM daily_sales
        WHERE date >= ? AND date < ?
    """, (month_start, next_month))
    month_data = await cursor.fetchone()

    # 上月数据（环比）
    prev_month_start = f"{year}-{month - 1:02d}-01" if month > 1 else f"{year - 1}-12-01"
    cursor = await db.execute("""
        SELECT SUM(phone_sales) as prev_phone, SUM(phone_qty) as prev_qty
        FROM daily_sales
        WHERE date >= ? AND date < ?
    """, (prev_month_start, month_start))
    prev_data = await cursor.fetchone()

    # 门店排名 Top 5
    cursor = await db.execute("""
        SELECT s.name as store_name, SUM(ds.phone_sales) as total
        FROM daily_sales ds JOIN stores s ON ds.store_id = s.id
        WHERE ds.date >= ? AND ds.date < ?
        GROUP BY ds.store_id
        ORDER BY total DESC
        LIMIT 5
    """, (month_start, next_month))
    top_stores = await cursor.fetchall()

    # 品类占比
    cursor = await db.execute("""
        SELECT source, SUM(phone_sales) as total
        FROM daily_sales WHERE date >= ? AND date < ?
        GROUP BY source
    """, (month_start, next_month))
    source_breakdown = await cursor.fetchall()

    # 会员统计
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM members WHERE is_active=1")
    member_count = (await cursor.fetchone())["cnt"]

    cursor = await db.execute("""
        SELECT level, COUNT(*) as cnt FROM members WHERE is_active=1 GROUP BY level
    """)
    member_levels = await cursor.fetchall()

    # 计算环比
    current_phone = month_data["total_phone"] or 0
    prev_phone = prev_data["prev_phone"] or 0
    mom_change = round((current_phone - prev_phone) / prev_phone * 100, 1) if prev_phone > 0 else 0

    return {
        "period": {"year": year, "month": month},
        "sales": {
            "total_phone": current_phone,
            "total_ncme": month_data["total_ncme"] or 0,
            "total_qty": month_data["total_qty"] or 0,
            "total_km": month_data["total_km"] or 0,
            "total_acc": month_data["total_acc"] or 0,
            "total_ti": month_data["total_ti"] or 0,
            "mom_change": mom_change,
            "store_count": month_data["store_count"] or 0,
            "active_days": month_data["active_days"] or 0,
        },
        "top_stores": [{"name": r["store_name"], "sales": r["total"] or 0} for r in top_stores],
        "source_breakdown": [{"source": r["source"], "sales": r["total"] or 0} for r in source_breakdown],
        "members": {
            "total": member_count,
            "levels": [{"level": r["level"], "count": r["cnt"]} for r in member_levels]
        }
    }


@router.get("/store-performance")
async def get_store_performance(
    user: dict = Depends(get_current_user),
    year: Optional[int] = None,
    month: Optional[int] = None
):
    """各门店业绩对比 - 包含完成率、排名、趋势"""
    import datetime
    now = datetime.datetime.now()
    year = year or now.year
    month = month or now.month

    db = await get_db()
    month_start = f"{year}-{month:02d}-01"
    next_month = f"{year}-{month + 1:02d}-01" if month < 12 else f"{year + 1}-01-01"

    cursor = await db.execute("""
        SELECT
            s.id, s.name, s.province,
            COALESCE(mt.phone_sales_target, 0) as target,
            COALESCE(SUM(ds.phone_sales), 0) as done,
            COALESCE(SUM(ds.phone_qty), 0) as qty,
            COALESCE(SUM(ds.ncme_sales), 0) as ncme,
            COALESCE(SUM(ds.accessory_sales), 0) as accessory,
            COALESCE(SUM(ds.trade_in_qty), 0) as trade_in
        FROM stores s
        LEFT JOIN monthly_targets mt ON mt.store_id = s.id AND mt.year=? AND mt.month=?
        LEFT JOIN daily_sales ds ON ds.store_id = s.id AND ds.date >= ? AND ds.date < ?
        WHERE s.is_active = 1
        GROUP BY s.id
        ORDER BY done DESC
    """, (year, month, month_start, next_month))
    rows = await cursor.fetchall()

    result = []
    for r in rows:
        target = r["target"] or 0
        done = r["done"] or 0
        rate = round(done / target * 100, 1) if target > 0 else 0
        result.append({
            "store_id": r["id"],
            "store_name": r["name"],
            "province": r["province"],
            "target": target,
            "done": done,
            "completion_rate": rate,
            "phone_qty": r["qty"] or 0,
            "ncme_sales": r["ncme"] or 0,
            "accessory_sales": r["accessory"] or 0,
            "trade_in_qty": r["trade_in"] or 0,
        })

    return {
        "year": year,
        "month": month,
        "stores": result
    }


@router.get("/trend")
async def get_sales_trend(
    user: dict = Depends(get_current_user),
    period: str = "monthly",  # daily / weekly / monthly
    months: int = 6
):
    """
    销售趋势分析
    period: daily=近30天, weekly=近12周, monthly=近N月
    """
    db = await get_db()
    if period == "monthly":
        cursor = await db.execute("""
            SELECT substr(date, 1, 7) as period,
                   SUM(phone_sales) as sales,
                   SUM(phone_qty) as qty
            FROM daily_sales
            GROUP BY period
            ORDER BY period DESC
            LIMIT ?
        """, (months,))
    elif period == "weekly":
        cursor = await db.execute("""
            SELECT strftime('%Y-%W', date) as period,
                   SUM(phone_sales) as sales,
                   SUM(phone_qty) as qty
            FROM daily_sales
            WHERE date >= date('now', '-84 days')
            GROUP BY period
            ORDER BY period
        """)
    else:  # daily
        cursor = await db.execute("""
            SELECT date as period,
                   SUM(phone_sales) as sales,
                   SUM(phone_qty) as qty
            FROM daily_sales
            WHERE date >= date('now', '-30 days')
            GROUP BY date
            ORDER BY date
        """)

    rows = await cursor.fetchall()
    return {
        "period_type": period,
        "data": [{"period": r["period"], "sales": r["sales"] or 0, "qty": r["qty"] or 0} for r in rows]
    }


@router.get("/dashboard-stats")
async def get_dashboard_stats(user: dict = Depends(get_current_user)):
    """
    Dashboard 聚合数据 - 一次请求返回所有看板需要的统计数据
    替代原来 Dashboard 页面的多次独立 API 调用
    """
    import datetime
    now = datetime.datetime.now()
    today = now.strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m") + "-01"

    db = await get_db()
    # 今日数据
    cursor = await db.execute("""
        SELECT SUM(phone_sales) as sales, SUM(phone_qty) as qty,
               SUM(ncme_sales) as ncme, SUM(accessory_sales) as acc,
               SUM(trade_in_qty) as trade_in
        FROM daily_sales WHERE date = ?
    """, (today,))
    today_data = await cursor.fetchone()

    # 本月数据
    cursor = await db.execute("""
        SELECT SUM(phone_sales) as sales, SUM(phone_qty) as qty,
               SUM(ncme_sales) as ncme, SUM(accessory_sales) as acc,
               SUM(trade_in_qty) as trade_in,
               COUNT(DISTINCT store_id) as stores,
               COUNT(DISTINCT date) as days
        FROM daily_sales WHERE date >= ?
    """, (month_start,))
    month_data = await cursor.fetchone()

    # 门店活跃度
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM stores WHERE is_active=1")
    total_stores = (await cursor.fetchone())["cnt"]

    # 会员总数
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM members WHERE is_active=1")
    member_count = (await cursor.fetchone())["cnt"]

    # 待跟进数
    cursor = await db.execute("""
        SELECT COUNT(*) as cnt FROM member_followups WHERE is_resolved=0
    """)
    pending_followups = (await cursor.fetchone())["cnt"]

    return {
        "today": {
            "sales": today_data["sales"] or 0,
            "qty": today_data["qty"] or 0,
            "ncme": today_data["ncme"] or 0,
            "accessory": today_data["acc"] or 0,
            "trade_in": today_data["trade_in"] or 0,
        },
        "month": {
            "sales": month_data["sales"] or 0,
            "qty": month_data["qty"] or 0,
            "ncme": month_data["ncme"] or 0,
            "accessory": month_data["acc"] or 0,
            "trade_in": month_data["trade_in"] or 0,
            "active_stores": month_data["stores"] or 0,
            "active_days": month_data["days"] or 0,
        },
        "stores": {"total": total_stores},
        "members": {"total": member_count, "pending_followups": pending_followups}
    }
