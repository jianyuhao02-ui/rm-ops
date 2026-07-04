"""任务管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from backend.dependencies import get_current_user
from backend.models.database import get_db
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class CreateTaskRequest(BaseModel):
    title: str
    description: str = ""
    priority: str = "normal"  # urgent / high / normal / low
    assignee_id: Optional[int] = None
    due_date: Optional[str] = None


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[int] = None
    due_date: Optional[str] = None
    status: Optional[str] = None  # pending / in_progress / completed / cancelled


@router.post("/create")
async def create_task(
    body: CreateTaskRequest,
    user: dict = Depends(get_current_user)
):
    """创建任务"""
    db = await get_db()
    await db.execute(
        """INSERT INTO tasks (creator_id, assignee_id, store_id, title, description, priority, due_date)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user["user_id"], body.assignee_id or user["user_id"],
         user.get("store_id"), body.title, body.description,
         body.priority, body.due_date)
    )
    await db.commit()
    return {"status": "ok", "message": "任务已创建"}


@router.get("/list")
async def get_tasks(
    status: str = None,  # pending / in_progress / completed / all
    assignee: str = "me",  # me / all
    user: dict = Depends(get_current_user)
):
    """获取任务列表"""
    db = await get_db()

    sql = """SELECT t.*,
        u1.display_name as creator_name,
        u2.display_name as assignee_name,
        s.name as store_name
        FROM tasks t
        JOIN users u1 ON t.creator_id = u1.id
        LEFT JOIN users u2 ON t.assignee_id = u2.id
        LEFT JOIN stores s ON t.store_id = s.id
        WHERE 1=1"""
    params = []

    if assignee == "me":
        sql += " AND (t.assignee_id = ? OR t.creator_id = ?)"
        params.extend([user["user_id"], user["user_id"]])

    if status and status != "all":
        sql += " AND t.status = ?"
        params.append(status)

    # 门店权限
    if user["role"] in ("manager", "staff") and user.get("store_id"):
        sql += " AND t.store_id = ?"
        params.append(user["store_id"])

    sql += " ORDER BY CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, t.created_at DESC"

    cursor = await db.execute(sql, tuple(params))
    tasks = await cursor.fetchall()

    # 统计
    stats = {"pending": 0, "in_progress": 0, "completed": 0}
    for t in tasks:
        s = t["status"]
        if s in stats:
            stats[s] += 1

    return {"tasks": [dict(t) for t in tasks], "stats": stats}


@router.put("/{task_id}")
async def update_task(
    task_id: int,
    body: UpdateTaskRequest,
    user: dict = Depends(get_current_user)
):
    """更新任务"""
    db = await get_db()

    cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = await cursor.fetchone()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 权限：创建者、执行者、或管理员
    if user["role"] != "admin" and task["creator_id"] != user["user_id"] and task["assignee_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="权限不足")

    updates = []
    params = []
    if body.title is not None:
        updates.append("title = ?")
        params.append(body.title)
    if body.description is not None:
        updates.append("description = ?")
        params.append(body.description)
    if body.priority is not None:
        updates.append("priority = ?")
        params.append(body.priority)
    if body.assignee_id is not None:
        updates.append("assignee_id = ?")
        params.append(body.assignee_id)
    if body.due_date is not None:
        updates.append("due_date = ?")
        params.append(body.due_date)
    if body.status is not None:
        updates.append("status = ?")
        params.append(body.status)
        if body.status == "completed":
            updates.append("completed_at = datetime('now','localtime')")

    if updates:
        params.append(task_id)
        await db.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", tuple(params))
        await db.commit()

    return {"status": "ok", "message": "任务已更新"}


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    user: dict = Depends(get_current_user)
):
    """删除任务（创建者或管理员）"""
    db = await get_db()
    cursor = await db.execute("SELECT creator_id FROM tasks WHERE id = ?", (task_id,))
    task = await cursor.fetchone()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if user["role"] != "admin" and task["creator_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="权限不足")

    await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    await db.commit()
    return {"status": "ok", "message": "任务已删除"}


@router.get("/stats")
async def get_task_stats(
    user: dict = Depends(get_current_user)
):
    """任务统计"""
    db = await get_db()

    base = """FROM tasks t WHERE (t.assignee_id = ? OR t.creator_id = ?)"""
    params = [user["user_id"], user["user_id"]]

    if user["role"] in ("manager", "staff") and user.get("store_id"):
        base += " AND t.store_id = ?"
        params.append(user["store_id"])

    cursor = await db.execute(f"SELECT COUNT(*) as cnt {base}", tuple(params))
    total = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(f"SELECT COUNT(*) as cnt {base} AND t.status = 'pending'", tuple(params))
    pending = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(f"SELECT COUNT(*) as cnt {base} AND t.status = 'in_progress'", tuple(params))
    in_progress = (await cursor.fetchone())["cnt"]

    cursor = await db.execute(f"SELECT COUNT(*) as cnt {base} AND t.priority = 'urgent' AND t.status != 'completed'", tuple(params))
    urgent = (await cursor.fetchone())["cnt"]

    return {
        "total": total, "pending": pending,
        "in_progress": in_progress, "urgent": urgent
    }
