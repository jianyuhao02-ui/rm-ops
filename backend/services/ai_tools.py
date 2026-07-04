"""
AI 助手 Function Calling 工具集
将自然语言意图映射为结构化数据库查询
"""
import json
from typing import Optional, Callable, Awaitable
from backend.models.database import get_db

# ──── 工具注册表 ────

def get_tool_definitions() -> list:
    """返回 OpenAI 兼容的 Tool 定义列表"""
    return [
        {
            "type": "function",
            "function": {
                "name": "query_sales",
                "description": "查询销售数据：月度/累计完成率、门店排名、销量趋势、目标达成情况",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["summary", "ranking", "trend", "detail"],
                            "description": "查询类型: summary=汇总, ranking=门店排名, trend=趋势, detail=明细"
                        },
                        "store_name": {
                            "type": "string",
                            "description": "门店名称（模糊匹配），不传则查所有门店"
                        },
                        "year": {"type": "integer", "description": "年份，默认当年"},
                        "month": {"type": "integer", "description": "月份(1-12)，默认当月"},
                        "limit": {"type": "integer", "description": "返回数量，默认10"},
                    },
                    "required": ["query_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_inventory",
                "description": "查询库存数据：库存预警、库龄分析、在库型号明细、安全库存状态",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["alert", "summary", "detail", "aging"],
                            "description": "查询类型: alert=预警, summary=汇总, detail=明细, aging=库龄"
                        },
                        "store_name": {
                            "type": "string",
                            "description": "门店名称（模糊匹配），不传则查所有门店"
                        },
                        "model_name": {
                            "type": "string",
                            "description": "手机型号关键词，如 S25、Z Flip"
                        },
                        "alert_type": {
                            "type": "string",
                            "enum": ["overstock", "understock", "all"],
                            "description": "预警类型: overstock=超量库存, understock=低库存, all=全部预警"
                        },
                    },
                    "required": ["query_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_prices",
                "description": "查询竞品价格数据：京东/九机价格对比、异常价格检测、价格历史走势",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["comparison", "anomaly", "history", "lowest"],
                            "description": "查询类型: comparison=对比, anomaly=异常, history=历史, lowest=最低价"
                        },
                        "model_name": {
                            "type": "string",
                            "description": "手机型号关键词，如 S25 Ultra"
                        },
                        "platform": {
                            "type": "string",
                            "enum": ["jd", "jiuji", "all"],
                            "description": "平台: jd=京东, jiuji=九机, all=全部"
                        },
                        "days": {
                            "type": "integer",
                            "description": "查询最近N天的数据，默认7",
                        },
                    },
                    "required": ["query_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_members",
                "description": "查询会员数据：会员数量统计、待跟进会员、消费记录、新增会员趋势",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["summary", "followup", "new", "detail"],
                            "description": "查询类型: summary=汇总, followup=待跟进, new=新增, detail=明细"
                        },
                        "store_name": {
                            "type": "string",
                            "description": "门店名称（模糊匹配）"
                        },
                        "days": {
                            "type": "integer",
                            "description": "查询最近N天，默认30"
                        },
                    },
                    "required": ["query_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_kb",
                "description": "搜索店长百事通知识库：产品知识、销售话术、售后政策、培训资料",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "搜索关键词"
                        },
                        "category": {
                            "type": "string",
                            "enum": ["product", "sales", "service", "policy", "training", "all"],
                            "description": "知识分类"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回条数，默认5"
                        },
                    },
                    "required": ["keyword"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_insight",
                "description": "获取业务智能分析洞察：异常指标、趋势变化、优化建议",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "enum": ["sales", "inventory", "prices", "members", "overall"],
                            "description": "分析主题"
                        },
                        "store_name": {
                            "type": "string",
                            "description": "门店名称（模糊匹配）"
                        },
                    },
                    "required": ["topic"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "commission_query",
                "description": "查询店员提成数据：提成排名、月度汇总、提成明细、个人提成详情",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["ranking", "summary", "detail", "staff_detail"],
                            "description": "查询类型: ranking=排名, summary=汇总, detail=明细, staff_detail=个人详情"
                        },
                        "staff_name": {
                            "type": "string",
                            "description": "店员姓名（模糊匹配），用于查个人详情"
                        },
                        "store_name": {
                            "type": "string",
                            "description": "门店名称（模糊匹配）"
                        },
                        "month": {"type": "string", "description": "月份，格式 YYYY-MM，默认当月"},
                        "limit": {"type": "integer", "description": "返回数量，默认10"},
                    },
                    "required": ["query_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "task_query",
                "description": "查询任务数据：我的任务、待办列表、已完成任务、任务统计",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["pending", "my_tasks", "summary", "overdue"],
                            "description": "查询类型: pending=待办, my_tasks=我的任务, summary=统计汇总, overdue=逾期"
                        },
                        "store_name": {
                            "type": "string",
                            "description": "门店名称（模糊匹配）"
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["urgent", "high", "normal", "low", "all"],
                            "description": "任务优先级筛选"
                        },
                        "limit": {"type": "integer", "description": "返回数量，默认10"},
                    },
                    "required": ["query_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "attendance_query",
                "description": "查询考勤数据：今日打卡、月度汇总、考勤异常、迟到早退统计",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["today", "summary", "anomaly", "detail"],
                            "description": "查询类型: today=今日打卡, summary=月度汇总, anomaly=异常考勤, detail=明细"
                        },
                        "store_name": {
                            "type": "string",
                            "description": "门店名称（模糊匹配）"
                        },
                        "day": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天"},
                    },
                    "required": ["query_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "approval_query",
                "description": "查询审批数据：待审批、已审批、我的申请、审批统计",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["pending", "my_requests", "summary", "recent"],
                            "description": "查询类型: pending=待审批, my_requests=我的申请, summary=统计汇总, recent=最近审批"
                        },
                        "approval_type": {
                            "type": "string",
                            "enum": ["leave", "reimbursement", "purchase", "general", "all"],
                            "description": "审批类型"
                        },
                        "store_name": {
                            "type": "string",
                            "description": "门店名称（模糊匹配）"
                        },
                        "limit": {"type": "integer", "description": "返回数量，默认10"},
                    },
                    "required": ["query_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "member_detail",
                "description": "查询单个会员的完整档案：消费记录、跟进历史、标签信息、消费习惯分析",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "member_keyword": {
                            "type": "string",
                            "description": "会员姓名或手机号（模糊匹配）"
                        },
                        "member_id": {
                            "type": "integer",
                            "description": "会员ID（精确查询）"
                        },
                    },
                    "required": [],
                },
            },
        },
    ]


# ──── 工具执行器 ────

async def query_sales(args: dict, user: dict) -> str:
    """执行查询销售数据的 SQL（使用实际表 daily_sales / monthly_targets）"""
    db = await get_db()
    qtype = args.get("query_type", "summary")
    store_name = args.get("store_name", "")
    year = args.get("year", 2026)
    month = args.get("month", 6)
    limit = args.get("limit", 10)

    from datetime import datetime
    if not year or not month:
        now = datetime.now()
        year = now.year
        month = now.month

    month_start = f"{year}-{month:02d}-01"
    next_month = f"{year}-{month + 1:02d}-01" if month < 12 else f"{year + 1}-01-01"

    try:
        if qtype == "summary":
            sql = """SELECT COUNT(DISTINCT ds.store_id) as store_count,
                COALESCE(SUM(ds.phone_sales),0) as total_sales,
                COALESCE(SUM(ds.phone_qty),0) as total_qty,
                COALESCE(SUM(ds.ncme_sales),0) as total_ncme,
                COALESCE(SUM(ds.accessory_sales),0) as total_acc,
                COALESCE(SUM(ds.trade_in_qty),0) as total_trade_in
                FROM daily_sales ds
                WHERE ds.date >= ? AND ds.date < ?"""
            cursor = await db.execute(sql, (month_start, next_month))
            row = await cursor.fetchone()
            return json.dumps(dict(row), ensure_ascii=False)

        elif qtype == "ranking":
            sql = """SELECT s.name as store,
                mt.phone_sales_target as target,
                COALESCE(SUM(ds.phone_sales),0) as sales_amount,
                CASE WHEN mt.phone_sales_target > 0
                    THEN ROUND(COALESCE(SUM(ds.phone_sales),0)*100.0/mt.phone_sales_target, 1)
                    ELSE 0 END as completion_pct
                FROM stores s
                LEFT JOIN monthly_targets mt ON s.id = mt.store_id AND mt.year=? AND mt.month=?
                LEFT JOIN daily_sales ds ON s.id = ds.store_id AND ds.date>=? AND ds.date<?
                WHERE s.is_active=1
                GROUP BY s.id ORDER BY completion_pct DESC LIMIT ?"""
            cursor = await db.execute(sql, (year, month, month_start, next_month, limit))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "trend":
            sql = """SELECT ds.date, COUNT(DISTINCT ds.store_id) as store_cnt, 
                SUM(ds.phone_sales) as amount, SUM(ds.phone_qty) as qty
                FROM daily_sales ds
                WHERE ds.date >= ? AND ds.date < ?"""
            params = [month_start, next_month]
            if store_name:
                sql += " AND ds.store_id IN (SELECT id FROM stores WHERE name LIKE ?)"
                params.append(f"%{store_name}%")
            sql += " GROUP BY ds.date ORDER BY ds.date"
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "detail":
            sql = """SELECT ds.date, s.name as store, ds.phone_sales, ds.phone_qty, 
                ds.ncme_sales, ds.key_model_qty, ds.accessory_sales
                FROM daily_sales ds JOIN stores s ON ds.store_id=s.id
                WHERE ds.date >= ? AND ds.date < ?"""
            params = [month_start, next_month]
            if store_name:
                sql += " AND s.name LIKE ?"
                params.append(f"%{store_name}%")
            sql += " ORDER BY ds.date DESC LIMIT ?"
            params.append(limit)
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        return json.dumps({"error": f"unknown query_type: {qtype}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def query_inventory(args: dict, user: dict) -> str:
    """执行库存查询（使用实际表 inventory / alert_rules）"""
    db = await get_db()
    qtype = args.get("query_type", "summary")
    store_name = args.get("store_name", "")
    model_name = args.get("model_name", "")
    alert_type = args.get("alert_type", "all")

    try:
        if qtype == "alert":
            # 使用现有库存数据判断预警
            sql = """SELECT s.name as store, i.model_code as model, i.color, i.spec, i.qty as stock_qty,
                CASE WHEN i.qty = 0 THEN 'danger' WHEN i.qty < 2 THEN 'warning' ELSE 'normal' END as status
                FROM inventory i JOIN stores s ON i.store_id=s.id
                WHERE i.qty < 2"""
            if store_name:
                sql += " AND s.name LIKE ?"
                cursor = await db.execute(sql, (f"%{store_name}%",))
            else:
                cursor = await db.execute(sql)
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "summary":
            sql = """SELECT s.name as store, COUNT(i.id) as model_count,
                SUM(i.qty) as total_stock
                FROM inventory i JOIN stores s ON i.store_id=s.id
                GROUP BY s.id ORDER BY total_stock DESC"""
            cursor = await db.execute(sql)
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "detail":
            sql = """SELECT s.name as store, i.model_code as model, i.color, i.spec, i.qty as stock_qty,
                i.updated_at as last_updated
                FROM inventory i JOIN stores s ON i.store_id=s.id
                WHERE 1=1"""
            params = []
            if model_name:
                sql += " AND i.model_code LIKE ?"
                params.append(f"%{model_name}%")
            if store_name:
                sql += " AND s.name LIKE ?"
                params.append(f"%{store_name}%")
            sql += " ORDER BY i.qty DESC LIMIT 20"
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "aging":
            # 用 updated_at 判断库龄
            sql = """SELECT s.name as store, i.model_code as model, i.qty as stock_qty,
                i.updated_at,
                CASE WHEN i.updated_at < datetime('now', '-30 days') THEN '>30天'
                    WHEN i.updated_at < datetime('now', '-14 days') THEN '>14天' ELSE '<14天' END as aging
                FROM inventory i JOIN stores s ON i.store_id=s.id
                WHERE i.qty > 0 AND i.updated_at < datetime('now', '-14 days')
                ORDER BY i.updated_at"""
            if store_name:
                sql += " AND s.name LIKE ?"
                cursor = await db.execute(sql, (f"%{store_name}%",))
            else:
                cursor = await db.execute(sql)
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        return json.dumps({"error": f"unknown query_type: {qtype}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def query_prices(args: dict, user: dict) -> str:
    """执行价格查询"""
    db = await get_db()
    qtype = args.get("query_type", "comparison")
    model_name = args.get("model_name", "")
    platform = args.get("platform", "all")
    days = args.get("days", 7)

    try:
        if qtype == "comparison":
            sql = """SELECT model, platform, price, check_time
                FROM price_records WHERE check_time >= datetime('now', ? || ' days', 'localtime')"""
            params = [f"-{days}"]
            if model_name:
                sql += " AND model LIKE ?"
                params.append(f"%{model_name}%")
            if platform != "all":
                if platform == "jiuji":
                    sql += " AND (platform LIKE '%九机%' OR platform LIKE '%jiuji%')"
                elif platform == "jd":
                    sql += " AND (platform LIKE '%京东%' OR platform LIKE '%jd%')"
            sql += " ORDER BY check_time DESC LIMIT 30"
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "anomaly":
            sql = """SELECT model, platform, price, check_time,
                ROUND((price - avg_price)/avg_price*100,1) as deviation_pct
                FROM (
                    SELECT model, platform, price, check_time,
                    AVG(price) OVER (PARTITION BY model) as avg_price
                    FROM price_records
                    WHERE check_time >= datetime('now', ? || ' days', 'localtime')
                )
                WHERE ABS((price - avg_price)/avg_price) > 0.05
                ORDER BY ABS((price - avg_price)/avg_price) DESC"""
            cursor = await db.execute(sql, (f"-{days}",))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "history":
            sql = """SELECT model, platform, price, check_time
                FROM price_records WHERE check_time >= datetime('now', ? || ' days', 'localtime')"""
            params = [f"-{days}"]
            if model_name:
                sql += " AND model LIKE ?"
                params.append(f"%{model_name}%")
            sql += " ORDER BY model, platform, check_time"
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "lowest":
            sql = """SELECT model, platform, MIN(price) as lowest_price, check_time
                FROM price_records
                WHERE check_time >= datetime('now', ? || ' days', 'localtime')"""
            params = [f"-{days}"]
            if model_name:
                sql += " AND model LIKE ?"
                params.append(f"%{model_name}%")
            sql += " GROUP BY model, platform ORDER BY model, platform"
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        return json.dumps({"error": f"unknown query_type: {qtype}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def query_members(args: dict, user: dict) -> str:
    """会员数据查询"""
    db = await get_db()
    qtype = args.get("query_type", "summary")
    store_name = args.get("store_name", "")
    days = args.get("days", 30)

    try:
        if qtype == "summary":
            sql = """SELECT COUNT(id) as total_members,
                SUM(CASE WHEN last_visit >= datetime('now', ? || ' days') THEN 1 ELSE 0 END) as active_recent,
                SUM(CASE WHEN followup_status='pending' THEN 1 ELSE 0 END) as pending_followup
                FROM members"""
            cursor = await db.execute(sql, (f"-{days}",))
            row = await cursor.fetchone()
            return json.dumps(dict(row), ensure_ascii=False)

        elif qtype == "followup":
            sql = """SELECT m.name, m.phone, s.name as store, m.last_visit, m.followup_status,
                m.followup_notes, m.buy_intent
                FROM members m LEFT JOIN stores s ON m.store_id=s.id
                WHERE m.followup_status='pending'
                ORDER BY m.last_visit DESC LIMIT 20"""
            cursor = await db.execute(sql)
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "new":
            sql = """SELECT m.name, m.phone, s.name as store, m.created_at, m.source
                FROM members m LEFT JOIN stores s ON m.store_id=s.id
                WHERE m.created_at >= datetime('now', ? || ' days')
                ORDER BY m.created_at DESC LIMIT 30"""
            cursor = await db.execute(sql, (f"-{days}",))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "detail":
            sql = """SELECT m.name, m.phone, s.name as store, m.member_level,
                m.total_spent, m.last_visit, m.buy_intent, m.followup_status
                FROM members m LEFT JOIN stores s ON m.store_id=s.id
                ORDER BY m.total_spent DESC LIMIT 20"""
            cursor = await db.execute(sql)
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        return json.dumps({"error": f"unknown query_type: {qtype}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def search_kb(args: dict, user: dict) -> str:
    """搜索知识库（使用实际表 kb_articles / kb_categories）"""
    db = await get_db()
    keyword = args.get("keyword", "")
    category = args.get("category", "all")
    limit = args.get("limit", 5)

    try:
        sql = """SELECT a.id, a.title, c.name as category, a.views, a.created_at
            FROM kb_articles a
            JOIN kb_categories c ON a.category_id = c.id
            WHERE a.title LIKE ? OR a.content LIKE ?"""
        kw = f"%{keyword}%"
        params = [kw, kw]
        if category != "all":
            sql += " AND c.name LIKE ?"
            params.append(f"%{category}%")
        sql += " ORDER BY a.views DESC, a.created_at DESC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(sql, tuple(params))
        rows = await cursor.fetchall()
        if not rows:
            return json.dumps({"message": "未找到相关知识内容"}, ensure_ascii=False)

        result = []
        for r in rows:
            item = dict(r)
            # 获取内容摘要
            cur2 = await db.execute("SELECT SUBSTR(content, 1, 200) as snippet FROM kb_articles WHERE id=?", (r["id"],))
            row2 = await cur2.fetchone()
            if row2:
                item["snippet"] = row2["snippet"]
            result.append(item)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def get_insight(args: dict, user: dict) -> str:
    """获取业务洞察（使用实际表）"""
    db = await get_db()
    topic = args.get("topic", "overall")
    store_name = args.get("store_name", "")

    from datetime import datetime
    now = datetime.now()
    month_start = f"{now.year}-{now.month:02d}-01"
    next_month = f"{now.year}-{(now.month + 1):02d}-01" if now.month < 12 else f"{now.year + 1}-01-01"

    insights = {}

    try:
        # 销售洞察
        if topic in ("sales", "overall"):
            cursor = await db.execute("""
                SELECT s.name, mt.phone_sales_target as target,
                    COALESCE(SUM(ds.phone_sales),0) as actual,
                    CASE WHEN mt.phone_sales_target > 0
                        THEN ROUND(COALESCE(SUM(ds.phone_sales),0)*100.0/mt.phone_sales_target, 1)
                        ELSE 0 END as pct
                FROM stores s
                LEFT JOIN monthly_targets mt ON s.id=mt.store_id AND mt.year=? AND mt.month=?
                LEFT JOIN daily_sales ds ON s.id=ds.store_id AND ds.date>=? AND ds.date<?
                WHERE s.is_active=1 GROUP BY s.id ORDER BY pct""",
                (now.year, now.month, month_start, next_month))
            rows = await cursor.fetchall()
            sales_data = [dict(r) for r in rows]
            behind = [r for r in sales_data if r["pct"] < 50]
            on_track = [r for r in sales_data if r["pct"] >= 80]
            insights["sales"] = {
                "total_stores": len(sales_data),
                "behind_count": len(behind),
                "behind_stores": [r["name"] for r in behind[:3]],
                "on_track_count": len(on_track),
                "on_track_stores": [r["name"] for r in on_track[:3]],
            }

        # 库存洞察
        if topic in ("inventory", "overall"):
            cursor = await db.execute("""
                SELECT COUNT(*) as alert_count FROM inventory WHERE qty = 0""")
            row = await cursor.fetchone()
            insights["inventory"] = {"zero_stock_count": row["alert_count"]}

            cursor = await db.execute("""
                SELECT model_code, SUM(qty) as total_qty FROM inventory
                WHERE qty > 0 GROUP BY model_code ORDER BY total_qty DESC LIMIT 5""")
            rows = await cursor.fetchall()
            insights["inventory"]["top_models"] = [dict(r) for r in rows]

        # 会员洞察
        if topic in ("members", "overall"):
            cursor = await db.execute("""
                SELECT COUNT(*) as total, 
                SUM(CASE WHEN level='钻石' OR level='金卡' THEN 1 ELSE 0 END) as vip_count,
                SUM(total_spent) as total_spent
                FROM members WHERE is_active=1""")
            row = await cursor.fetchone()
            insights["members"] = dict(row) if row else {}

        return json.dumps(insights, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ──── 新增工具：店员提成查询 ────

async def commission_query(args: dict, user: dict) -> str:
    """查询店员提成数据"""
    db = await get_db()
    qtype = args.get("query_type", "ranking")
    staff_name = args.get("staff_name", "")
    store_name = args.get("store_name", "")
    month = args.get("month", "")
    limit = args.get("limit", 10)

    from datetime import datetime
    if not month:
        now = datetime.now()
        month = f"{now.year}-{now.month:02d}"

    try:
        if qtype == "ranking":
            sql = """SELECT sf.name as staff, st.name as store, sf.position,
                SUM(ss.phone_qty) as phones_sold, SUM(ss.ncme_sales) as ncme_amount,
                SUM(ss.commission) as total_comm
                FROM staff_sales ss
                JOIN staff sf ON ss.staff_id=sf.id
                JOIN stores st ON sf.store_id=st.id
                WHERE ss.sale_date LIKE ?
                GROUP BY ss.staff_id ORDER BY total_comm DESC LIMIT ?"""
            cursor = await db.execute(sql, (month + "%", limit))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "summary":
            sql = """SELECT st.name as store, COUNT(DISTINCT ss.staff_id) as staff_count,
                SUM(ss.phone_qty) as total_phones, SUM(ss.commission) as total_comm,
                ROUND(AVG(ss.commission), 2) as avg_comm
                FROM staff_sales ss
                JOIN staff sf ON ss.staff_id=sf.id
                JOIN stores st ON sf.store_id=st.id
                WHERE ss.sale_date LIKE ?
                GROUP BY st.id ORDER BY total_comm DESC"""
            cursor = await db.execute(sql, (month + "%",))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "detail":
            sql = """SELECT ss.sale_date as date, sf.name as staff, st.name as store,
                ss.phone_qty, ss.phone_sales, ss.ncme_sales, ss.accessory_sales,
                ss.trade_in_qty, ss.commission
                FROM staff_sales ss
                JOIN staff sf ON ss.staff_id=sf.id
                JOIN stores st ON sf.store_id=st.id
                WHERE ss.sale_date LIKE ?"""
            params = [month + "%"]
            if staff_name:
                sql += " AND sf.name LIKE ?"
                params.append(f"%{staff_name}%")
            if store_name:
                sql += " AND st.name LIKE ?"
                params.append(f"%{store_name}%")
            sql += " ORDER BY ss.sale_date DESC LIMIT ?"
            params.append(limit)
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "staff_detail":
            if not staff_name:
                return json.dumps({"error": "请提供店员姓名(staff_name)"})
            sql = """SELECT sf.name as staff, st.name as store, sf.position, sf.base_salary,
                SUM(ss.phone_qty) as month_phones, SUM(ss.phone_sales) as month_phone_sales,
                SUM(ss.ncme_sales) as month_ncme, SUM(ss.accessory_sales) as month_acc,
                SUM(ss.trade_in_qty) as month_trade_in, SUM(ss.commission) as month_comm,
                sf.base_salary + COALESCE(SUM(ss.commission), 0) as estimated_income
                FROM staff sf
                JOIN stores st ON sf.store_id=st.id
                LEFT JOIN staff_sales ss ON sf.id=ss.staff_id AND ss.sale_date LIKE ?
                WHERE sf.name LIKE ?
                GROUP BY sf.id"""
            cursor = await db.execute(sql, (month + "%", f"%{staff_name}%"))
            row = await cursor.fetchone()
            if not row:
                return json.dumps({"message": f"未找到店员: {staff_name}"})
            return json.dumps(dict(row), ensure_ascii=False)

        return json.dumps({"error": f"unknown query_type: {qtype}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ──── 新增工具：任务查询 ────

async def task_query(args: dict, user: dict) -> str:
    """查询任务数据"""
    db = await get_db()
    qtype = args.get("query_type", "pending")
    store_name = args.get("store_name", "")
    priority = args.get("priority", "all")
    limit = args.get("limit", 10)

    user_id = user.get("user_id", 0)

    try:
        if qtype == "pending":
            sql = """SELECT t.id, t.title, t.priority, t.status,
                u.display_name as assignee, s.name as store, t.due_date, t.created_at
                FROM tasks t
                LEFT JOIN users u ON t.assignee_id=u.id
                LEFT JOIN stores s ON t.store_id=s.id
                WHERE t.status IN ('pending','in_progress')
                ORDER BY CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
                t.due_date ASC LIMIT ?"""
            cursor = await db.execute(sql, (limit,))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "my_tasks":
            sql = """SELECT t.id, t.title, t.priority, t.status, t.due_date, t.created_at,
                cr.display_name as creator
                FROM tasks t
                LEFT JOIN users cr ON t.creator_id=cr.id
                WHERE t.assignee_id=?"""
            params = [user_id]
            if priority != "all":
                sql += " AND t.priority=?"
                params.append(priority)
            sql += " ORDER BY t.status, t.due_date ASC LIMIT ?"
            params.append(limit)
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "summary":
            sql = """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status='in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN priority='urgent' THEN 1 ELSE 0 END) as urgent_count,
                SUM(CASE WHEN due_date < datetime('now','localtime') AND status!='completed' THEN 1 ELSE 0 END) as overdue
                FROM tasks"""
            cursor = await db.execute(sql)
            row = await cursor.fetchone()
            return json.dumps(dict(row), ensure_ascii=False)

        elif qtype == "overdue":
            sql = """SELECT t.id, t.title, t.priority, t.status, t.due_date,
                u.display_name as assignee, s.name as store
                FROM tasks t
                LEFT JOIN users u ON t.assignee_id=u.id
                LEFT JOIN stores s ON t.store_id=s.id
                WHERE t.due_date < datetime('now','localtime') AND t.status!='completed'
                ORDER BY t.due_date ASC LIMIT ?"""
            cursor = await db.execute(sql, (limit,))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        return json.dumps({"error": f"unknown query_type: {qtype}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ──── 新增工具：考勤查询 ────

async def attendance_query(args: dict, user: dict) -> str:
    """查询考勤数据"""
    db = await get_db()
    qtype = args.get("query_type", "today")
    store_name = args.get("store_name", "")
    day = args.get("day", "")

    from datetime import datetime
    if not day:
        day = datetime.now().strftime("%Y-%m-%d")

    try:
        if qtype == "today":
            today_date = day if day else datetime.now().strftime("%Y-%m-%d")
            sql = """SELECT u.display_name as user, s.name as store,
                ar.punch_type, ar.punch_time, ar.remark
                FROM attendance_records ar
                JOIN users u ON ar.user_id=u.id
                LEFT JOIN stores s ON ar.store_id=s.id
                WHERE ar.punch_time LIKE ?
                ORDER BY ar.punch_time DESC LIMIT 30"""
            cursor = await db.execute(sql, (today_date + "%",))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "summary":
            month_start = day[:7] if len(day) >= 7 else datetime.now().strftime("%Y-%m")
            sql = """SELECT u.display_name as user, s.name as store,
                COUNT(*) as punch_count,
                SUM(CASE WHEN ar.punch_type='in' THEN 1 ELSE 0 END) as check_in,
                SUM(CASE WHEN ar.punch_type='out' THEN 1 ELSE 0 END) as check_out,
                MIN(ar.punch_time) as first_punch, MAX(ar.punch_time) as last_punch
                FROM attendance_records ar
                JOIN users u ON ar.user_id=u.id
                LEFT JOIN stores s ON ar.store_id=s.id
                WHERE ar.punch_time LIKE ?
                GROUP BY ar.user_id ORDER BY punch_count DESC LIMIT 20"""
            cursor = await db.execute(sql, (month_start + "%",))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "anomaly":
            # 查找签到时间晚于 09:15 的记录作为迟到/异常
            sql = """SELECT u.display_name as user, s.name as store,
                ar.punch_type, ar.punch_time, ar.remark
                FROM attendance_records ar
                JOIN users u ON ar.user_id=u.id
                LEFT JOIN stores s ON ar.store_id=s.id
                WHERE ar.punch_type='in'
                AND CAST(substr(ar.punch_time,12,5) AS TEXT) > '09:15'
                ORDER BY ar.punch_time DESC LIMIT 20"""
            cursor = await db.execute(sql)
            rows = await cursor.fetchall()
            if not rows:
                return json.dumps({"message": "未发现异常考勤记录"})
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "detail":
            sql = """SELECT u.display_name as user, s.name as store,
                ar.punch_type, ar.punch_time, ar.location, ar.remark
                FROM attendance_records ar
                JOIN users u ON ar.user_id=u.id
                LEFT JOIN stores s ON ar.store_id=s.id
                ORDER BY ar.punch_time DESC LIMIT ?"""
            cursor = await db.execute(sql, (min(limit, 30),))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        return json.dumps({"error": f"unknown query_type: {qtype}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ──── 新增工具：审批查询 ────

async def approval_query(args: dict, user: dict) -> str:
    """查询审批数据"""
    db = await get_db()
    qtype = args.get("query_type", "pending")
    approval_type = args.get("approval_type", "all")
    store_name = args.get("store_name", "")
    limit = args.get("limit", 10)

    user_id = user.get("user_id", 0)

    try:
        if qtype == "pending":
            sql = """SELECT a.id, a.title, a.approval_type, a.status,
                app.display_name as applicant, s.name as store, a.created_at
                FROM approvals a
                JOIN users app ON a.applicant_id=app.id
                LEFT JOIN stores s ON a.store_id=s.id
                WHERE a.status='pending'"""
            params = []
            if approval_type != "all":
                sql += " AND a.approval_type=?"
                params.append(approval_type)
            sql += " ORDER BY a.created_at DESC LIMIT ?"
            params.append(limit)
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "my_requests":
            sql = """SELECT a.id, a.title, a.approval_type, a.status,
                apr.display_name as approver, a.approved_at, a.created_at
                FROM approvals a
                LEFT JOIN users apr ON a.approver_id=apr.id
                WHERE a.applicant_id=?"""
            params = [user_id]
            if approval_type != "all":
                sql += " AND a.approval_type=?"
                params.append(approval_type)
            sql += " ORDER BY a.created_at DESC LIMIT ?"
            params.append(limit)
            cursor = await db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        elif qtype == "summary":
            sql = """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) as rejected,
                SUM(CASE WHEN approval_type='leave' THEN 1 ELSE 0 END) as leave_count,
                SUM(CASE WHEN approval_type='reimbursement' THEN 1 ELSE 0 END) as reimbursement_count
                FROM approvals"""
            cursor = await db.execute(sql)
            row = await cursor.fetchone()
            return json.dumps(dict(row), ensure_ascii=False)

        elif qtype == "recent":
            sql = """SELECT a.id, a.title, a.approval_type, a.status,
                app.display_name as applicant, apr.display_name as approver,
                a.approved_at, a.created_at
                FROM approvals a
                JOIN users app ON a.applicant_id=app.id
                LEFT JOIN users apr ON a.approver_id=apr.id
                ORDER BY a.created_at DESC LIMIT ?"""
            cursor = await db.execute(sql, (limit,))
            rows = await cursor.fetchall()
            return json.dumps([dict(r) for r in rows], ensure_ascii=False)

        return json.dumps({"error": f"unknown query_type: {qtype}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ──── 新增工具：会员详情查询 ────

async def member_detail(args: dict, user: dict) -> str:
    """查询会员完整档案"""
    db = await get_db()
    member_keyword = args.get("member_keyword", "")
    member_id = args.get("member_id", 0)

    try:
        if member_id:
            sql = """SELECT m.*, s.name as store_name
                FROM members m LEFT JOIN stores s ON m.store_id=s.id
                WHERE m.id=?"""
            cursor = await db.execute(sql, (member_id,))
        elif member_keyword:
            sql = """SELECT m.*, s.name as store_name
                FROM members m LEFT JOIN stores s ON m.store_id=s.id
                WHERE m.name LIKE ? OR m.phone LIKE ?
                ORDER BY m.total_spent DESC LIMIT 3"""
            kw = f"%{member_keyword}%"
            cursor = await db.execute(sql, (kw, kw))
        else:
            return json.dumps({"error": "请提供会员姓名/手机号或会员ID"})

        row = await cursor.fetchone()
        if not row:
            return json.dumps({"message": "未找到该会员"})

        member = dict(row)

        # 消费记录
        cursor2 = await db.execute("""
            SELECT mp.purchase_date as date, mp.product_info, mp.model_code,
                mp.spec, mp.color, mp.amount, mp.points_earned,
                mp.trade_in_model, mp.trade_in_amount
            FROM member_purchases mp
            WHERE mp.member_id=?
            ORDER BY mp.purchase_date DESC LIMIT 10
        """, (member["id"],))
        member["purchases"] = [dict(r) for r in await cursor2.fetchall()]

        # 跟进记录
        cursor3 = await db.execute("""
            SELECT mf.followup_type, mf.content, mf.result,
                u.display_name as staff, mf.created_at
            FROM member_followups mf
            LEFT JOIN users u ON mf.staff_id=u.id
            WHERE mf.member_id=?
            ORDER BY mf.created_at DESC LIMIT 10
        """, (member["id"],))
        member["followups"] = [dict(r) for r in await cursor3.fetchall()]

        # 标签
        cursor4 = await db.execute("""
            SELECT td.name as tag, td.color
            FROM member_tags mt
            JOIN member_tag_defs td ON mt.tag_id=td.id
            WHERE mt.member_id=?
        """, (member["id"],))
        member["tags"] = [dict(r) for r in await cursor4.fetchall()]

        return json.dumps(member, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ──── 路由表 ────

TOOL_ROUTER: dict[str, Callable] = {
    "query_sales": query_sales,
    "query_inventory": query_inventory,
    "query_prices": query_prices,
    "query_members": query_members,
    "search_kb": search_kb,
    "get_insight": get_insight,
    "commission_query": commission_query,
    "task_query": task_query,
    "attendance_query": attendance_query,
    "approval_query": approval_query,
    "member_detail": member_detail,
}


async def execute_tool(tool_name: str, arguments: dict, user: dict) -> str:
    """根据工具名执行对应的查询函数"""
    handler = TOOL_ROUTER.get(tool_name)
    if not handler:
        return json.dumps({"error": f"未知工具: {tool_name}"})
    return await handler(arguments, user)
