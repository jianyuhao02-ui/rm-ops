"""考勤打卡 API"""
from fastapi import APIRouter, Depends, HTTPException
from backend.dependencies import get_current_user
from backend.models.database import get_db
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class PunchRequest(BaseModel):
    punch_type: str = "in"  # in / out
    location: str = ""
    remark: str = ""


@router.post("/punch")
async def punch_in_out(
    body: PunchRequest,
    user: dict = Depends(get_current_user)
):
    """打卡（上班/下班）"""
    db = await get_db()
    await db.execute(
        """INSERT INTO attendance_records (user_id, store_id, punch_type, location, remark)
           VALUES (?, ?, ?, ?, ?)""",
        (user["user_id"], user.get("store_id"), body.punch_type, body.location, body.remark)
    )
    await db.commit()
    return {"status": "ok", "punch_type": body.punch_type, "message": "打卡成功"}


@router.get("/records")
async def get_records(
    date: str = None,
    user: dict = Depends(get_current_user)
):
    """获取打卡记录"""
    db = await get_db()
    from datetime import datetime
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    sql = """SELECT a.*, u.display_name as user_name, s.name as store_name
        FROM attendance_records a
        JOIN users u ON a.user_id = u.id
        LEFT JOIN stores s ON a.store_id = s.id
        WHERE date(a.punch_time) = ?"""
    params = [date]

    # 权限过滤
    if user["role"] in ("manager", "staff") and user.get("store_id"):
        sql += " AND a.store_id = ?"
        params.append(user["store_id"])
    elif user["role"] == "admin":
        pass  # 看全部

    sql += " ORDER BY a.punch_time DESC"

    cursor = await db.execute(sql, tuple(params))
    records = await cursor.fetchall()

    # 统计汇总
    in_count = sum(1 for r in records if r["punch_type"] == "in")
    out_count = sum(1 for r in records if r["punch_type"] == "out")

    return {
        "date": date,
        "records": [dict(r) for r in records],
        "summary": {"in_count": in_count, "out_count": out_count, "total": len(records)}
    }


@router.get("/today")
async def get_today_status(
    user: dict = Depends(get_current_user)
):
    """获取当天打卡状态"""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")

    db = await get_db()
    cursor = await db.execute(
        """SELECT * FROM attendance_records
           WHERE user_id = ? AND date(punch_time) = ?
           ORDER BY punch_time DESC""",
        (user["user_id"], today)
    )
    records = await cursor.fetchall()

    has_in = any(r["punch_type"] == "in" for r in records)
    has_out = any(r["punch_type"] == "out" for r in records)

    return {
        "date": today,
        "has_punched_in": has_in,
        "has_punched_out": has_out,
        "latest_record": dict(records[0]) if records else None
    }


@router.get("/monthly")
async def get_monthly_summary(
    year: int = None, month: int = None,
    user: dict = Depends(get_current_user)
):
    """月度考勤汇总"""
    from datetime import datetime
    if not year or not month:
        now = datetime.now()
        year = now.year
        month = now.month

    db = await get_db()
    month_str = f"{year}-{month:02d}"

    sql = """SELECT u.id as user_id, u.display_name, s.name as store_name,
        COUNT(DISTINCT date(a.punch_time)) as work_days,
        SUM(CASE WHEN a.punch_type='in' THEN 1 ELSE 0 END) as in_count,
        SUM(CASE WHEN a.punch_type='out' THEN 1 ELSE 0 END) as out_count
        FROM users u
        LEFT JOIN stores s ON u.store_id = s.id
        LEFT JOIN attendance_records a ON a.user_id = u.id
            AND a.punch_time LIKE ?
        WHERE u.is_active = 1"""

    params = [f"{month_str}%"]

    if user["role"] in ("manager", "staff") and user.get("store_id"):
        sql += " AND u.store_id = ?"
        params.append(user["store_id"])

    sql += " GROUP BY u.id ORDER BY s.sort_order, u.display_name"

    cursor = await db.execute(sql, tuple(params))
    rows = await cursor.fetchall()

    return {
        "year": year, "month": month,
        "records": [dict(r) for r in rows]
    }
