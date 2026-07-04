"""审批流程 API"""
from fastapi import APIRouter, Depends, HTTPException
from backend.dependencies import get_current_user
from backend.models.database import get_db
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class CreateApprovalRequest(BaseModel):
    title: str
    content: str = ""
    approval_type: str = "general"  # leave=请假, expense=报销, purchase=采购, general=通用
    approver_id: Optional[int] = None


class ApproveRequest(BaseModel):
    status: str = "approved"  # approved / rejected
    comment: str = ""


@router.post("/submit")
async def submit_approval(
    body: CreateApprovalRequest,
    user: dict = Depends(get_current_user)
):
    """提交审批"""
    db = await get_db()

    # 如果没有指定审批人，自动设为管理员
    approver_id = body.approver_id
    if not approver_id:
        cursor = await db.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        admin = await cursor.fetchone()
        if admin:
            approver_id = admin["id"]

    await db.execute(
        """INSERT INTO approvals (applicant_id, approver_id, store_id, title, content, approval_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user["user_id"], approver_id, user.get("store_id"),
         body.title, body.content, body.approval_type)
    )
    await db.commit()
    return {"status": "ok", "message": "审批已提交"}


@router.get("/list")
async def get_approvals(
    tab: str = "pending",  # pending / my / all
    user: dict = Depends(get_current_user)
):
    """获取审批列表"""
    db = await get_db()

    if tab == "pending" and user["role"] == "admin":
        # 管理员看待审批
        sql = """SELECT a.*, u1.display_name as applicant_name,
            u2.display_name as approver_name, s.name as store_name
            FROM approvals a
            JOIN users u1 ON a.applicant_id = u1.id
            LEFT JOIN users u2 ON a.approver_id = u2.id
            LEFT JOIN stores s ON a.store_id = s.id
            WHERE a.status = 'pending'
            ORDER BY a.created_at DESC"""
        cursor = await db.execute(sql)
    elif tab == "my":
        sql = """SELECT a.*, u1.display_name as applicant_name,
            u2.display_name as approver_name, s.name as store_name
            FROM approvals a
            JOIN users u1 ON a.applicant_id = u1.id
            LEFT JOIN users u2 ON a.approver_id = u2.id
            LEFT JOIN stores s ON a.store_id = s.id
            WHERE a.applicant_id = ?
            ORDER BY a.created_at DESC"""
        cursor = await db.execute(sql, (user["user_id"],))
    else:
        sql = """SELECT a.*, u1.display_name as applicant_name,
            u2.display_name as approver_name, s.name as store_name
            FROM approvals a
            JOIN users u1 ON a.applicant_id = u1.id
            LEFT JOIN users u2 ON a.approver_id = u2.id
            LEFT JOIN stores s ON a.store_id = s.id
            ORDER BY a.created_at DESC LIMIT 50"""
        cursor = await db.execute(sql)

    approvals = await cursor.fetchall()
    return {"approvals": [dict(a) for a in approvals]}


@router.post("/{approval_id}/approve")
async def approve_request(
    approval_id: int,
    body: ApproveRequest,
    user: dict = Depends(get_current_user)
):
    """审批通过/驳回（管理员）"""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可审批")

    db = await get_db()
    cursor = await db.execute("SELECT id, status FROM approvals WHERE id = ?", (approval_id,))
    approval = await cursor.fetchone()
    if not approval:
        raise HTTPException(status_code=404, detail="审批不存在")
    if approval["status"] != "pending":
        raise HTTPException(status_code=400, detail="该审批已处理")

    new_status = body.status
    approved_at = "datetime('now','localtime')" if new_status == "approved" else None

    await db.execute(
        f"""UPDATE approvals SET status = ?, approved_at = {approved_at or 'NULL'}
           WHERE id = ?""",
        (new_status, approval_id)
    )
    await db.commit()

    return {"status": "ok", "message": "审批已完成" if new_status == "approved" else "审批已驳回"}


@router.get("/stats")
async def get_approval_stats(
    user: dict = Depends(get_current_user)
):
    """审批统计"""
    db = await get_db()

    # 待审批数
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM approvals WHERE status = 'pending'")
    pending = (await cursor.fetchone())["cnt"]

    # 我的待审批数
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM approvals WHERE applicant_id = ? AND status IN ('approved','rejected')",
                              (user["user_id"],))
    my_processed = (await cursor.fetchone())["cnt"]

    return {"pending_count": pending, "my_processed_count": my_processed}
