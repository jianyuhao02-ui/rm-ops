"""社区互动 API"""
from fastapi import APIRouter, Depends, HTTPException
from backend.dependencies import get_current_user, require_admin, require_manager_or_admin
from backend.models.database import get_db

router = APIRouter()


@router.get("/posts")
async def get_posts(category: str = None, page: int = 1, page_size: int = 20,
    user: dict = Depends(get_current_user)):
    """获取社区帖子列表"""

    db = await get_db()
    offset = (page - 1) * page_size
    if category:
        cursor = await db.execute("""
            SELECT p.*, u.display_name as author_name, s.name as store_name
            FROM community_posts p
            JOIN users u ON p.author_id = u.id
            LEFT JOIN stores s ON p.store_id = s.id
            WHERE p.category = ?
            ORDER BY p.is_pinned DESC, p.updated_at DESC
            LIMIT ? OFFSET ?
        """, (category, page_size, offset))
    else:
        cursor = await db.execute("""
            SELECT p.*, u.display_name as author_name, s.name as store_name
            FROM community_posts p
            JOIN users u ON p.author_id = u.id
            LEFT JOIN stores s ON p.store_id = s.id
            ORDER BY p.is_pinned DESC, p.updated_at DESC
            LIMIT ? OFFSET ?
        """, (page_size, offset))

    posts = await cursor.fetchall()

    # 获取每个帖子的回复数
    result = []
    for post in posts:
        p = dict(post)
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM community_comments WHERE post_id=?", (post["id"],))
        count = await cursor.fetchone()
        p["comment_count"] = count["cnt"]
        result.append(p)

    return {"posts": result, "page": page, "page_size": page_size}


@router.get("/post/{post_id}")
async def get_post_detail(post_id: int,
    user: dict = Depends(get_current_user)):
    """获取帖子详情+回复"""

    db = await get_db()
    # 帖子
    cursor = await db.execute("""
        SELECT p.*, u.display_name as author_name, s.name as store_name
        FROM community_posts p
        JOIN users u ON p.author_id = u.id
        LEFT JOIN stores s ON p.store_id = s.id
        WHERE p.id = ?
    """, (post_id,))
    post = await cursor.fetchone()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    # 增加浏览量
    await db.execute("UPDATE community_posts SET views=views+1 WHERE id=?", (post_id,))
    await db.commit()

    # 回复
    cursor = await db.execute("""
        SELECT c.*, u.display_name as author_name, u.role as author_role, s.name as store_name
        FROM community_comments c
        JOIN users u ON c.author_id = u.id
        LEFT JOIN stores s ON u.store_id = s.id
        WHERE c.post_id = ?
        ORDER BY c.created_at ASC
    """, (post_id,))
    comments = await cursor.fetchall()

    return {
        "post": dict(post),
        "comments": [dict(c) for c in comments]
    }


@router.post("/posts")
async def create_post(
    title: str, content: str, category: str = "general",
    user: dict = Depends(get_current_user)):
    """发帖"""

    db = await get_db()
    await db.execute(
        "INSERT INTO community_posts (author_id, store_id, title, content, category) VALUES (?,?,?,?,?)",
        (user["user_id"], user.get("store_id"), title, content, category)
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/post/{post_id}/comments")
async def add_comment(post_id: int, content: str, is_official: int = 0,
    user: dict = Depends(get_current_user)):
    """回复帖子"""

    db = await get_db()
    # 只有管理员可以标记官方回复
    if is_official and user["role"] != "admin":
        is_official = 0

    await db.execute(
        "INSERT INTO community_comments (post_id, author_id, content, is_official) VALUES (?,?,?,?)",
        (post_id, user["user_id"], content, is_official)
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/post/{post_id}/resolve")
async def resolve_post(post_id: int,
    user: dict = Depends(get_current_user)):
    """标记帖子已解决"""

    db = await get_db()
    # 帖子作者或管理员可以标记
    cursor = await db.execute("SELECT author_id FROM community_posts WHERE id=?", (post_id,))
    post = await cursor.fetchone()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    if user["role"] != "admin" and post["author_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="权限不足")

    await db.execute("UPDATE community_posts SET is_resolved=1 WHERE id=?", (post_id,))
    await db.commit()
    return {"status": "ok"}


@router.delete("/post/{post_id}")
async def delete_post(post_id: int,
    user: dict = Depends(get_current_user)):
    """删除帖子（作者或管理员）"""

    db = await get_db()
    cursor = await db.execute("SELECT author_id FROM community_posts WHERE id=?", (post_id,))
    post = await cursor.fetchone()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    if user["role"] != "admin" and post["author_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="权限不足")
    await db.execute("DELETE FROM community_comments WHERE post_id=?", (post_id,))
    await db.execute("DELETE FROM community_posts WHERE id=?", (post_id,))
    await db.commit()
    return {"status": "ok"}


@router.post("/post/{post_id}/like")
async def like_post(post_id: int,
    user: dict = Depends(get_current_user)):
    """点赞帖子（likes+1）"""

    db = await get_db()
    cursor = await db.execute("SELECT id FROM community_posts WHERE id=?", (post_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="帖子不存在")
    await db.execute("UPDATE community_posts SET likes=COALESCE(likes,0)+1 WHERE id=?", (post_id,))
    await db.commit()
    cursor = await db.execute("SELECT COALESCE(likes,0) as cnt FROM community_posts WHERE id=?", (post_id,))
    result = await cursor.fetchone()
    return {"status": "ok", "likes": result["cnt"]}
