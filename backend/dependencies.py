"""
FastAPI 依赖注入模块
提供统一的认证、权限校验、数据库连接管理

安全说明：
- Token 只允许通过 Authorization: Bearer 请求头传递
- 禁止通过 URL 查询参数传递 token（会被 Nginx/CDN/代理日志记录明文）
"""
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import jwt
from backend.config import SECRET_KEY, ALGORITHM
from backend.models.database import get_db

security = HTTPBearer(auto_error=False)


async def get_token_from_header(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    """只允许从 Authorization: Bearer 头获取 token，禁止 URL 参数"""
    if credentials:
        return credentials.credentials
    raise HTTPException(status_code=401, detail="请提供认证令牌（Authorization: Bearer）")


async def get_current_user(
    token: str = Depends(get_token_from_header)
) -> dict:
    """解析 JWT token，返回当前用户信息（依赖注入版本）"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的认证令牌")


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """要求管理员权限"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def require_manager_or_admin(user: dict = Depends(get_current_user)) -> dict:
    """要求店长或管理员权限"""
    if user.get("role") not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="需要店长或管理员权限")
    return user


class DatabaseSession:
    """数据库连接上下文管理器（连接池版本，不负责关闭）"""

    async def __aenter__(self):
        self.db = await get_db()
        return self.db

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 连接池模式：不在这里关闭，由 close_db() 在进程退出时统一关闭
        pass


async def get_db_session():
    """获取数据库会话（依赖注入版本，连接池模式）"""
    db = await get_db()
    yield db
    # 不 close：连接是全局共享的，close_db() 在进程退出时调用
