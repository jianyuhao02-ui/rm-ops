"""eBoss 数据同步管理 API"""
import os
from fastapi import APIRouter, Depends, Query
from backend.dependencies import get_current_user, require_admin, require_manager_or_admin
from backend.models.database import get_db

router = APIRouter()


@router.get("/sync-status")
async def get_sync_status(
    user: dict = Depends(get_current_user),
    limit: int = 50):
    """获取 eBoss 同步状态和历史记录"""

    db = await get_db()
    # 统计
    cursor = await db.execute("SELECT COUNT(*) as total FROM eboss_sync_log")
    total = (await cursor.fetchone())["total"]

    cursor = await db.execute("SELECT COUNT(*) as total FROM eboss_sync_log WHERE status='success'")
    success = (await cursor.fetchone())["total"]

    cursor = await db.execute("SELECT COUNT(*) as total FROM eboss_sync_log WHERE status='error'")
    errors = (await cursor.fetchone())["total"]

    # eBoss 来源的 daily_sales 记录数
    cursor = await db.execute("SELECT COUNT(*) as total FROM daily_sales WHERE source='eboss'")
    sales_count = (await cursor.fetchone())["total"]

    # 最近同步记录
    cursor = await db.execute("""
        SELECT * FROM eboss_sync_log ORDER BY id DESC LIMIT ?
    """, (limit,))
    logs = [dict(r) for r in await cursor.fetchall()]

    # 各类型文件统计
    cursor = await db.execute("""
        SELECT file_type, COUNT(*) as cnt,
               MAX(synced_at) as last_sync
        FROM eboss_sync_log WHERE status='success'
        GROUP BY file_type
    """)
    type_stats = [dict(r) for r in await cursor.fetchall()]

    return {
        "total_files": total,
        "success_count": success,
        "error_count": errors,
        "eboss_sales_records": sales_count,
        "type_stats": type_stats,
        "recent_logs": logs,
    }


@router.post("/scan-now")
async def trigger_scan(
    user: dict = Depends(get_current_user)
):
    """手动触发 eBoss 目录扫描"""
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="权限不足")

    try:
        from backend.services.scheduler_service import task_scan_eboss_dir
        import asyncio
        asyncio.create_task(task_scan_eboss_dir())
        return {"status": "ok", "message": "eBoss 目录扫描任务已触发"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/sales-by-source")
async def get_sales_by_source(
    user: dict = Depends(get_current_user),
    year: int = None, month: int = None):
    """按数据来源统计销售数据（dingtalk vs eboss）"""

    db = await get_db()
    where = ""
    params = []
    if year and month:
        where = " WHERE date LIKE ?"
        params.append(f"{year}-{month:02d}%")

    cursor = await db.execute(f"""
        SELECT source, COUNT(*) as records,
               SUM(phone_sales) as total_phone,
               SUM(phone_qty) as total_qty,
               SUM(accessory_sales) as total_acc
        FROM daily_sales {where}
        GROUP BY source
    """, params)
    return [dict(r) for r in await cursor.fetchall()]


@router.get("/files")
async def list_eboss_files(
    user: dict = Depends(get_current_user),
    filetype: str = None):
    """列出 eBoss 目录中的可处理文件"""

    from backend.services.eboss_parser import scan_eboss_directory
    files = scan_eboss_directory()

    if filetype:
        files = [f for f in files if filetype in f["filetype"]]

    return {"total": len(files), "files": files}
