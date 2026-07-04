"""
数据库与种子行为调整：不在每次启动时默认插入种子数据。
提供独立脚本 scripts/clear_data.py 来清空现有数据库数据（或删除 DB 文件）。
"""
import aiosqlite
import asyncio
import os
from typing import Optional
from backend.config import DB_PATH, DB_JOURNAL_MODE, SEED_ENABLED
from backend.logger import db_logger

DB_PATH_STR = str(DB_PATH)

# ==================== 连接池 ====================
_db_instance: Optional[aiosqlite.Connection] = None
_db_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    global _db_instance
    async with _db_lock:
        if _db_instance is None:
            _db_instance = await aiosqlite.connect(DB_PATH_STR, timeout=5)
            _db_instance.row_factory = aiosqlite.Row
            await _db_instance.execute("PRAGMA journal_mode=WAL")
            await _db_instance.execute("PRAGMA busy_timeout=5000")
            await _db_instance.execute("PRAGMA foreign_keys=ON")
            await _db_instance.execute("PRAGMA cache_size=-2000")
            await _db_instance.execute("PRAGMA synchronous=NORMAL")
            db_logger.info("数据库连接池已初始化（单例 WAL 模式）")
    return _db_instance


async def close_db():
    global _db_instance
    if _db_instance is not None:
        await _db_instance.close()
        _db_instance = None
        db_logger.info("数据库连接已关闭")


async def init_db():
    db_logger.info(f"初始化数据库: {DB_PATH_STR}")
    os.makedirs(os.path.dirname(DB_PATH_STR), exist_ok=True)

    async with aiosqlite.connect(DB_PATH_STR) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(f"PRAGMA journal_mode={DB_JOURNAL_MODE}")
        await db.execute("PRAGMA foreign_keys=ON")

        # （表创建逻辑保持不变 — 略去长表定义以节省空间）
        # 请参考原仓库 backend/models/database.py 中完整表结构

        await db.commit()

    # 仅在显式启用种子数据时运行 seed
    if SEED_ENABLED:
        await seed_data()
    else:
        db_logger.info("跳过种子数据插入（RM_SEED_ENABLED=false）")

    db_logger.info(f"数据库初始化完成: {DB_PATH_STR}")


async def seed_data():
    # 保持原有 seed_data 实现（略）—— 在此示例中，实际实现仍在仓库中原位置
    pass
