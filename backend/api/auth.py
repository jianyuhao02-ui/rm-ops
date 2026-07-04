"""认证 API - JWT 登录"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
import bcrypt
import jwt
import datetime
from backend.models.database import get_db
from backend.config import SECRET_KEY, ALGORITHM, TOKEN_EXPIRE_HOURS, ADMIN_USERNAME, ADMIN_PASSWORD
from backend.dependencies import get_current_user, require_admin, require_manager_or_admin

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str
    role: str = "manager"
    store_id: int = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


def hash_password(password: str) -> str:
    """bcrypt 哈希密码（自带随机 salt，每次调用结果不同）"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    """验证密码，兼容 bcrypt 哈希和旧版 SHA256 哈希（迁移过渡期）"""
    # bcrypt 哈希以 $2b$ 开头
    if hashed.startswith("$2b$") or hashed.startswith("$2a$"):
        return bcrypt.checkpw(password.encode(), hashed.encode())
    # 兼容旧版 SHA256（无盐）- 用于首次登录时自动迁移
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest() == hashed


def create_token(user_id: int, username: str, role: str, store_id: int = None, display_name: str = "") -> str:
    """创建 JWT Token"""
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "store_id": store_id,
        "display_name": display_name,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRE_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/login")
async def login(req: LoginRequest):
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, username, password_hash, display_name, role, store_id, is_active FROM users WHERE username = ?",
        (req.username,)
    )
    user = await cursor.fetchone()

    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    # 自动迁移：如果是旧版 SHA256 密码，登录成功后静默升级为 bcrypt
    old_hash = user["password_hash"]
    if not (old_hash.startswith("$2b$") or old_hash.startswith("$2a$")):
        new_hash = hash_password(req.password)
        await db.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user["id"]))
        await db.commit()

    token = create_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
        store_id=user["store_id"],
        display_name=user["display_name"]
    )

    # 获取门店名
    store_name = ""
    if user["store_id"]:
        cursor = await db.execute("SELECT name FROM stores WHERE id = ?", (user["store_id"],))
        store = await cursor.fetchone()
        if store:
            store_name = store["name"]

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
            "store_id": user["store_id"],
            "store_name": store_name
        }
    }


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    return user


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: dict = Depends(get_current_user)
):
    """修改当前用户密码"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT password_hash FROM users WHERE id = ?",
        (user["user_id"],)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")

    if not verify_password(req.old_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="原密码错误")

    await db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(req.new_password), user["user_id"])
    )
    await db.commit()
    return {"status": "ok", "message": "密码修改成功"}


@router.get("/users")
async def list_users(user: dict = Depends(require_admin)):
    """获取所有用户列表（管理员）"""
    db = await get_db()
    cursor = await db.execute("""
        SELECT u.id, u.username, u.display_name, u.role, u.store_id, u.is_active, s.name as store_name
        FROM users u LEFT JOIN stores s ON u.store_id = s.id
        ORDER BY u.id
    """)
    users = await cursor.fetchall()
    return [dict(row) for row in users]


@router.post("/users/reset-password")
async def reset_password(
    username: str,
    new_password: str,
    user: dict = Depends(require_admin)
):
    """重置用户密码（管理员）"""
    db = await get_db()
    await db.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (hash_password(new_password), username)
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/users/create")
async def create_user(
    req: CreateUserRequest,
    user: dict = Depends(require_admin)
):
    """新增用户（管理员）"""
    db = await get_db()
    # 检查用户名是否已存在
    cursor = await db.execute("SELECT id FROM users WHERE username=?", (req.username,))
    if await cursor.fetchone():
        raise HTTPException(status_code=400, detail="用户名已存在")

    await db.execute(
        "INSERT INTO users (username, password_hash, display_name, role, store_id) VALUES (?,?,?,?,?)",
        (req.username, hash_password(req.password), req.display_name, req.role, req.store_id)
    )
    await db.commit()
    return {"status": "ok"}


@router.put("/users/{username}/toggle")
async def toggle_user(
    username: str,
    user: dict = Depends(require_admin)
):
    """启用/禁用用户（管理员）"""
    db = await get_db()
    cursor = await db.execute("SELECT id, is_active FROM users WHERE username=?", (username,))
    target = await cursor.fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    new_status = 0 if target["is_active"] else 1
    await db.execute("UPDATE users SET is_active=? WHERE id=?", (new_status, target["id"]))
    await db.commit()
    return {"status": "ok", "is_active": new_status}


@router.get("/stores")
async def list_stores(
    user: dict = Depends(get_current_user)):

    db = await get_db()
    cursor = await db.execute("SELECT id, name, province FROM stores WHERE is_active=1 ORDER BY sort_order")
    stores = await cursor.fetchall()
    return [dict(s) for s in stores]
