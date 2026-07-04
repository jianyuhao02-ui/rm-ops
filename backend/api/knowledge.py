"""知识库 API"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from backend.dependencies import get_current_user, require_admin, require_manager_or_admin
from pydantic import BaseModel
from typing import Optional
from backend.models.database import get_db

router = APIRouter()


class CategoryCreate(BaseModel):
    name: str
    icon: str = ""
    sort_order: int = 0


class CategoryDelete(BaseModel):
    category_id: int


class ArticleCreate(BaseModel):
    category_id: int
    title: str
    content: str
    sort_order: int = 0


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


@router.get("/categories")
async def get_categories(
    user: dict = Depends(get_current_user)
):
    """获取知识库分类列表"""

    db = await get_db()
    cursor = await db.execute("SELECT * FROM kb_categories ORDER BY sort_order")
    categories = await cursor.fetchall()

    result = []
    for cat in categories:
        cat_data = dict(cat)
        # 获取该分类下的文章数
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM kb_articles WHERE category_id=?", (cat["id"],))
        count = await cursor.fetchone()
        cat_data["article_count"] = count["cnt"]
        result.append(cat_data)

    return result


@router.get("/articles")
async def get_articles(category_id: int = None, keyword: str = "",
    user: dict = Depends(get_current_user)):
    """获取知识库文章（支持全文搜索）"""

    db = await get_db()
    if category_id:
        cursor = await db.execute(
            "SELECT * FROM kb_articles WHERE category_id=? ORDER BY sort_order, id",
            (category_id,)
        )
    elif keyword:
        # 增强搜索：标题优先，内容次之，带相关性排序
        cursor = await db.execute(
            """SELECT *, 
                CASE WHEN title LIKE ? THEN 1 ELSE 0 END as title_match,
                LENGTH(title) - LENGTH(REPLACE(LOWER(title), LOWER(?), '')) as title_score
            FROM kb_articles 
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY title_match DESC, title_score DESC, id LIMIT 50""",
            (f"%{keyword}%", keyword, f"%{keyword}%", f"%{keyword}%")
        )
    else:
        cursor = await db.execute("SELECT * FROM kb_articles ORDER BY sort_order, id")

    articles = await cursor.fetchall()
    return [dict(a) for a in articles]


@router.get("/search")
async def search_knowledge(
    keyword: str = "",
    category_id: int = None,
    user: dict = Depends(get_current_user)
):
    """增强版知识库搜索：跨分类全文检索"""
    db = await get_db()
    
    sql = """SELECT a.*, c.name as category_name, c.icon as category_icon
        FROM kb_articles a
        JOIN kb_categories c ON a.category_id = c.id
        WHERE 1=1"""
    params = []

    if keyword:
        sql += " AND (a.title LIKE ? OR a.content LIKE ?)"
        kw = f"%{keyword}%"
        params.extend([kw, kw])

    if category_id:
        sql += " AND a.category_id = ?"
        params.append(category_id)

    sql += " ORDER BY a.views DESC, a.created_at DESC LIMIT 30"

    cursor = await db.execute(sql, tuple(params))
    articles = await cursor.fetchall()

    # 为搜索结果生成摘要（截取关键字附近内容）
    result = []
    for a in articles:
        item = dict(a)
        if keyword and item.get("content"):
            content = item["content"]
            # 简单摘要：取关键字前后80字符
            idx = content.lower().find(keyword.lower())
            if idx >= 0:
                start = max(0, idx - 40)
                end = min(len(content), idx + len(keyword) + 40)
                snippet = content[start:end]
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."
                item["snippet"] = snippet
            else:
                item["snippet"] = content[:100]
        result.append(item)

    return {"keyword": keyword, "total": len(result), "articles": result}


@router.get("/article/{article_id}")
async def get_article(article_id: int,
    user: dict = Depends(get_current_user)):
    """获取单篇文章详情"""

    db = await get_db()
    cursor = await db.execute("SELECT * FROM kb_articles WHERE id=?", (article_id,))
    article = await cursor.fetchone()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 增加浏览量
    await db.execute("UPDATE kb_articles SET views=views+1 WHERE id=?", (article_id,))
    await db.commit()

    return dict(article)


@router.post("/categories")
async def create_category(body: CategoryCreate,
    user: dict = Depends(get_current_user)):
    """创建分类（管理员）"""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    await db.execute(
        "INSERT INTO kb_categories (name, icon, sort_order) VALUES (?,?,?)",
        (body.name, body.icon, body.sort_order)
    )
    await db.commit()
    return {"status": "ok"}


@router.delete("/categories")
async def delete_category(body: CategoryDelete,
    user: dict = Depends(get_current_user)):
    """删除分类及其下所有文章（管理员）"""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    await db.execute("DELETE FROM kb_articles WHERE category_id=?", (body.category_id,))
    await db.execute("DELETE FROM kb_categories WHERE id=?", (body.category_id,))
    await db.commit()
    return {"status": "ok"}


@router.post("/articles")
async def create_article(body: ArticleCreate,
    user: dict = Depends(get_current_user)):
    """创建知识库文章（管理员）"""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    await db.execute(
        "INSERT INTO kb_articles (category_id, title, content, sort_order) VALUES (?,?,?,?)",
        (body.category_id, body.title, body.content, body.sort_order)
    )
    await db.commit()
    return {"status": "ok"}


@router.delete("/article/{article_id}")
async def delete_article(article_id: int,
    user: dict = Depends(get_current_user)):
    """删除文章（管理员）"""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    cursor = await db.execute("SELECT id FROM kb_articles WHERE id=?", (article_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="文章不存在")
    await db.execute("DELETE FROM kb_articles WHERE id=?", (article_id,))
    await db.commit()
    return {"status": "ok"}


@router.put("/article/{article_id}")
async def update_article(article_id: int, body: ArticleUpdate,
    user: dict = Depends(get_current_user)):
    """更新文章（管理员）"""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="权限不足")

    db = await get_db()
    if body.title:
        await db.execute("UPDATE kb_articles SET title=?, updated_at=datetime('now','localtime') WHERE id=?", (body.title, article_id))
    if body.content:
        await db.execute("UPDATE kb_articles SET content=?, updated_at=datetime('now','localtime') WHERE id=?", (body.content, article_id))
    await db.commit()
    return {"status": "ok"}
