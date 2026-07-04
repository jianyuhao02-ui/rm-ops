"""文件上传 API - 图片上传、文件管理"""
import os
import uuid
import secrets
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from backend.dependencies import get_current_user
from backend.config import PROJECT_DIR

router = APIRouter()

# 上传目录
UPLOAD_DIR = Path(PROJECT_DIR) / "frontend" / "uploads"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".docx", ".xlsx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """上传图片（知识库/社区通用）"""
    # 验证文件类型
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    # 验证大小
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过 10MB 限制")

    # 确保上传目录存在
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # 生成唯一文件名
    unique_name = f"{secrets.token_hex(8)}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = UPLOAD_DIR / unique_name

    # 保存文件
    with open(file_path, "wb") as f:
        f.write(content)

    # 返回可访问的 URL
    url = f"/uploads/{unique_name}"

    return {
        "status": "ok",
        "url": url,
        "filename": file.filename,
        "size": len(content),
        "mime_type": file.content_type,
    }


@router.delete("/image/{filename}")
async def delete_image(
    filename: str,
    user: dict = Depends(get_current_user)
):
    """删除上传的图片（管理员/店长）"""
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="权限不足")

    # 安全检查：防止路径穿越
    safe_name = Path(filename).name
    file_path = UPLOAD_DIR / safe_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    os.remove(file_path)
    return {"status": "ok"}
