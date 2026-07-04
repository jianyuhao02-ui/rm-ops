"""
SQLite 数据库初始化与连接管理

连接池策略：
- 使用单例共享连接（aiosqlite 本身是线程安全的异步驱动）
- WAL 日志模式 + busy_timeout 5000ms，消除 "database is locked" 错误
- 50人并发读写完全够用；未来迁移 PostgreSQL 只需替换这个文件
"""
import aiosqlite
import asyncio
import os
from typing import Optional
from backend.config import DB_PATH, DB_JOURNAL_MODE
from backend.logger import db_logger

DB_PATH_STR = str(DB_PATH)

# ==================== 连接池 ====================
_db_instance: Optional[aiosqlite.Connection] = None
_db_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    """
    获取全局共享数据库连接（单例池）。

    SQLite + aiosqlite 最佳实践：
    1. 一个进程共享一个长连接，避免反复 open/close 的磁盘 I/O 开销
    2. WAL 模式允许多读一写并发，不会锁全库
    3. busy_timeout=5000 让写操作等最多 5 秒再报 locked，而不是立即失败
    """
    global _db_instance
    async with _db_lock:
        if _db_instance is None:
            _db_instance = await aiosqlite.connect(DB_PATH_STR, timeout=5)
            _db_instance.row_factory = aiosqlite.Row
            # WAL 日志模式：读写互不阻塞（读不阻塞写，写不阻塞读）
            await _db_instance.execute("PRAGMA journal_mode=WAL")
            # 写冲突等待最多 5 秒，避免 "database is locked" 直接崩掉
            await _db_instance.execute("PRAGMA busy_timeout=5000")
            await _db_instance.execute("PRAGMA foreign_keys=ON")
            # 提高缓存：2MB 页缓存，减少磁盘 I/O
            await _db_instance.execute("PRAGMA cache_size=-2000")
            await _db_instance.execute("PRAGMA synchronous=NORMAL")
            db_logger.info("数据库连接池已初始化（单例 WAL 模式）")
    return _db_instance


async def close_db():
    """关闭数据库连接（进程退出时调用）"""
    global _db_instance
    if _db_instance is not None:
        await _db_instance.close()
        _db_instance = None
        db_logger.info("数据库连接已关闭")

async def init_db():
    """初始化所有表"""
    db_logger.info(f"初始化数据库: {DB_PATH_STR}")

    # 确保数据目录存在
    os.makedirs(os.path.dirname(DB_PATH_STR), exist_ok=True)

    async with aiosqlite.connect(DB_PATH_STR) as db:
        db.row_factory = aiosqlite.Row

        # 设置日志模式
        await db.execute(f"PRAGMA journal_mode={DB_JOURNAL_MODE}")
        await db.execute("PRAGMA foreign_keys=ON")

        # 用户表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'staff',
                store_id INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # 门店表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                province TEXT,
                dingtalk_dept_id TEXT,
                sort_order INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        """)

        # 月度目标表（每月一条记录）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monthly_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                store_id INTEGER NOT NULL,
                grade TEXT,
                phone_sales_target REAL DEFAULT 0,
                ncme_target REAL DEFAULT 0,
                phone_qty_target INTEGER DEFAULT 0,
                key_model_target INTEGER DEFAULT 0,
                accessory_target REAL DEFAULT 0,
                FOREIGN KEY (store_id) REFERENCES stores(id),
                UNIQUE(year, month, store_id)
            )
        """)

        # 每日销售记录
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                store_id INTEGER NOT NULL,
                phone_sales REAL DEFAULT 0,
                ncme_sales REAL DEFAULT 0,
                phone_qty INTEGER DEFAULT 0,
                key_model_qty INTEGER DEFAULT 0,
                accessory_sales REAL DEFAULT 0,
                trade_in_qty INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (store_id) REFERENCES stores(id),
                UNIQUE(date, store_id)
            )
        """)

        # 库存表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                model_code TEXT NOT NULL,
                color TEXT,
                spec TEXT,
                qty INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (store_id) REFERENCES stores(id),
                UNIQUE(store_id, model_code, color, spec)
            )
        """)

        # 价格记录表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS price_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_code TEXT NOT NULL,
                spec TEXT NOT NULL,
                platform TEXT NOT NULL,
                price REAL DEFAULT 0,
                company_price REAL DEFAULT 0,
                activity TEXT DEFAULT '',
                note TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_by INTEGER,
                FOREIGN KEY (updated_by) REFERENCES users(id),
                UNIQUE(model_code, spec, platform)
            )
        """)

        # 知识库分类
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kb_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                icon TEXT,
                sort_order INTEGER DEFAULT 0
            )
        """)

        # 知识库文章
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kb_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (category_id) REFERENCES kb_categories(id)
            )
        """)

        # 社区帖子
        await db.execute("""
            CREATE TABLE IF NOT EXISTS community_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author_id INTEGER NOT NULL,
                store_id INTEGER,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                is_resolved INTEGER DEFAULT 0,
                is_pinned INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (author_id) REFERENCES users(id),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        """)

        # 社区回复
        await db.execute("""
            CREATE TABLE IF NOT EXISTS community_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                is_official INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (post_id) REFERENCES community_posts(id) ON DELETE CASCADE,
                FOREIGN KEY (author_id) REFERENCES users(id)
            )
        """)

        # 通知记录
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                content TEXT,
                type TEXT DEFAULT 'info',
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # 库存预警规则
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_series TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                threshold INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        """)

        # 会员主表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                store_id INTEGER,
                level TEXT DEFAULT '普通',
                total_spent REAL DEFAULT 0,
                points INTEGER DEFAULT 0,
                join_date TEXT,
                is_vip INTEGER DEFAULT 0,
                remark TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        """)

        # 会员消费/购机记录
        await db.execute("""
            CREATE TABLE IF NOT EXISTS member_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                store_id INTEGER,
                model_code TEXT DEFAULT '',
                product_info TEXT DEFAULT '',
                spec TEXT DEFAULT '',
                color TEXT DEFAULT '',
                imei TEXT DEFAULT '',
                amount REAL DEFAULT 0,
                points_earned INTEGER DEFAULT 0,
                trade_in_model TEXT DEFAULT '',
                trade_in_amount REAL DEFAULT 0,
                purchase_date TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (member_id) REFERENCES members(id),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        """)

        # 会员标签定义表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS member_tag_defs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#1428a0',
                description TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # 会员标签关联表（多对多）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS member_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES member_tag_defs(id) ON DELETE CASCADE,
                UNIQUE(member_id, tag_id)
            )
        """)

        # 重点客户跟进记录
        await db.execute("""
            CREATE TABLE IF NOT EXISTS member_followups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                store_id INTEGER,
                staff_id INTEGER,
                followup_type TEXT DEFAULT 'call',
                content TEXT NOT NULL,
                result TEXT DEFAULT '',
                next_followup_date TEXT,
                is_resolved INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (member_id) REFERENCES members(id),
                FOREIGN KEY (store_id) REFERENCES stores(id),
                FOREIGN KEY (staff_id) REFERENCES users(id)
            )
        """)

        # eBoss 文件同步日志
        await db.execute("""
            CREATE TABLE IF NOT EXISTS eboss_sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_date TEXT,
                file_mtime TEXT NOT NULL,
                records_parsed INTEGER DEFAULT 0,
                records_imported INTEGER DEFAULT 0,
                status TEXT DEFAULT 'success',
                error_msg TEXT DEFAULT '',
                synced_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # ========== 考勤打卡 ==========
        await db.execute("""
            CREATE TABLE IF NOT EXISTS attendance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                store_id INTEGER,
                punch_type TEXT NOT NULL DEFAULT 'in',
                punch_time TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                location TEXT DEFAULT '',
                remark TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        """)

        # ========== 审批流程 ==========
        await db.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_id INTEGER NOT NULL,
                approver_id INTEGER,
                store_id INTEGER,
                title TEXT NOT NULL,
                content TEXT DEFAULT '',
                approval_type TEXT DEFAULT 'general',
                status TEXT DEFAULT 'pending',
                approved_at TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (applicant_id) REFERENCES users(id),
                FOREIGN KEY (approver_id) REFERENCES users(id),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        """)

        # ========== 任务管理 ==========
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER NOT NULL,
                assignee_id INTEGER,
                store_id INTEGER,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                priority TEXT DEFAULT 'normal',
                status TEXT DEFAULT 'pending',
                due_date TEXT,
                completed_at TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (creator_id) REFERENCES users(id),
                FOREIGN KEY (assignee_id) REFERENCES users(id),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        """)

        # 迁移：确保 community_posts 有 likes 字段
        try:
            await db.execute("ALTER TABLE community_posts ADD COLUMN likes INTEGER DEFAULT 0")
        except Exception:
            pass  # 字段已存在则忽略

        # 迁移：确保 daily_sales 有 source 字段
        try:
            await db.execute("ALTER TABLE daily_sales ADD COLUMN source TEXT DEFAULT 'dingtalk'")
        except Exception:
            pass  # 字段已存在则忽略

        # 迁移：确保 monthly_targets 有 trade_in_rate 字段
        try:
            await db.execute("ALTER TABLE monthly_targets ADD COLUMN trade_in_rate REAL DEFAULT 0")
        except Exception:
            pass

        # 迁移：确保 members 表存在 is_vip 字段
        try:
            await db.execute("ALTER TABLE members ADD COLUMN is_vip INTEGER DEFAULT 0")
        except Exception:
            pass

        # 迁移：确保 member_purchases 表存在 model_code / imei / trade_in_* 字段
        for col_sql in [
            "ALTER TABLE member_purchases ADD COLUMN model_code TEXT DEFAULT ''",
            "ALTER TABLE member_purchases ADD COLUMN spec TEXT DEFAULT ''",
            "ALTER TABLE member_purchases ADD COLUMN color TEXT DEFAULT ''",
            "ALTER TABLE member_purchases ADD COLUMN imei TEXT DEFAULT ''",
            "ALTER TABLE member_purchases ADD COLUMN trade_in_model TEXT DEFAULT ''",
            "ALTER TABLE member_purchases ADD COLUMN trade_in_amount REAL DEFAULT 0",
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass

        # ========== 店员管理基础表（确保存在） ==========
        await db.execute("""
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                position TEXT DEFAULT '店员',
                base_salary REAL DEFAULT 3000,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS staff_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id INTEGER NOT NULL,
                store_id INTEGER NOT NULL,
                sale_date TEXT NOT NULL,
                phone_sales REAL DEFAULT 0,
                ncme_sales REAL DEFAULT 0,
                phone_qty INTEGER DEFAULT 0,
                key_model_qty INTEGER DEFAULT 0,
                accessory_sales REAL DEFAULT 0,
                trade_in_qty INTEGER DEFAULT 0,
                commission REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (staff_id) REFERENCES staff(id),
                FOREIGN KEY (store_id) REFERENCES stores(id),
                UNIQUE(staff_id, store_id, sale_date)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS staff_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id INTEGER NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                target_qty INTEGER DEFAULT 0,
                target_sales REAL DEFAULT 0,
                FOREIGN KEY (staff_id) REFERENCES staff(id),
                UNIQUE(staff_id, year, month)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS commission_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT NOT NULL,
                product_type TEXT NOT NULL,
                commission_type TEXT NOT NULL DEFAULT 'fixed',
                commission_fixed REAL DEFAULT 0,
                commission_rate REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT DEFAULT '',
                start_date TEXT,
                end_date TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # ========== 订单记录表（Phase 1 新增） ==========
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sales_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                staff_id INTEGER NOT NULL,
                order_date TEXT NOT NULL,
                order_time TEXT NOT NULL DEFAULT (time('now', 'localtime')),
                model_code TEXT NOT NULL,
                product_name TEXT DEFAULT '',
                spec TEXT DEFAULT '',
                color TEXT DEFAULT '',
                imei TEXT DEFAULT '',
                original_price REAL DEFAULT 0,
                actual_price REAL NOT NULL,
                category TEXT NOT NULL DEFAULT 'phone',
                is_key_model INTEGER DEFAULT 0,
                member_id INTEGER,
                member_phone TEXT DEFAULT '',
                trade_in_model TEXT DEFAULT '',
                trade_in_amount REAL DEFAULT 0,
                source TEXT DEFAULT 'manual',
                remark TEXT DEFAULT '',
                created_by INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (store_id) REFERENCES stores(id),
                FOREIGN KEY (staff_id) REFERENCES staff(id),
                FOREIGN KEY (member_id) REFERENCES members(id)
            )
        """)

        # 索引
        await db.execute("CREATE INDEX IF NOT EXISTS idx_member_tags_member ON member_tags(member_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_member_followups_member ON member_followups(member_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_member_purchases_member ON member_purchases(member_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_members_phone ON members(phone)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_members_store ON members(store_id)")

        # ========== 会员管理（已在上面创建，此处不再重复） ==========

        # 创建性能索引（IF NOT EXISTS 保证幂等）
        await db.execute("CREATE INDEX IF NOT EXISTS idx_daily_sales_date ON daily_sales(date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_daily_sales_store_date ON daily_sales(store_id, date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_daily_sales_source ON daily_sales(source)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_price_records_model ON price_records(model_code, spec, platform)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_inventory_store_model ON inventory(store_id, model_code)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_community_comments_post ON community_comments(post_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_eboss_sync_log_file ON eboss_sync_log(file_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_kb_articles_category ON kb_articles(category_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_members_phone ON members(phone)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_members_store ON members(store_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_members_level ON members(level)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_purchases_member ON member_purchases(member_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sales_orders_date ON sales_orders(order_date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sales_orders_store_date ON sales_orders(store_id, order_date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sales_orders_staff_date ON sales_orders(staff_id, order_date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sales_orders_member ON sales_orders(member_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sales_orders_imei ON sales_orders(imei)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_staff_sales_staff_date ON staff_sales(staff_id, sale_date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_staff_sales_store_date ON staff_sales(store_id, sale_date)")

        await db.commit()

    # 初始化种子数据
    await seed_data()
    db_logger.info(f"数据库初始化完成: {DB_PATH_STR}")


async def seed_data():
    """初始化种子数据：门店 + 管理员账号"""
    from backend.config import ADMIN_USERNAME, ADMIN_PASSWORD, STORE_MANAGER_PASSWORD

    async with aiosqlite.connect(DB_PATH_STR) as db:
        db.row_factory = aiosqlite.Row

        # 检查是否已有数据
        count = await db.execute("SELECT COUNT(*) FROM stores")
        if (await count.fetchone())[0] > 0:
            return

        # 导入门店数据
        stores = [
            ("万象城三星授权旗舰店", "贵州", "935222159", 1),
            ("华润万象汇三星授权体验店", "贵州", "574246116", 2),
            ("兴义梦乐城三星授权体验店", "贵州·兴义", "639950218", 3),
            ("遵义吾悦三星授权体验店", "贵州·遵义", "430232289", 4),
            ("曲靖万达三星授权体验店", "云南·曲靖", "983685022", 5),
            ("六盘水三星授权体验店", "贵州·六盘水", "975306497", 6),
            ("龙湾万达三星授权体验店", "贵州·贵阳", "492986089", 7),
            ("昭通吾悦三星授权体验店", "云南·昭通", "899271796", 8),
            ("清镇吾悦三星授权体验店", "贵州·清镇", "894469704", 9),
            ("安顺三星授权体验店", "贵州·安顺", "979460265", 10),
            ("蒙自三星授权体验店", "云南·蒙自", "", 11),  # 第11家门店，补充进种子数据
        ]

        for name, province, dd_id, order in stores:
            await db.execute(
                "INSERT INTO stores (name, province, dingtalk_dept_id, sort_order) VALUES (?,?,?,?)",
                (name, province, dd_id, order)
            )

        # 管理员账号（使用 bcrypt，不再用无盐 SHA256）
        import bcrypt
        admin_pw = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt(rounds=12)).decode()
        store_pw = bcrypt.hashpw(STORE_MANAGER_PASSWORD.encode(), bcrypt.gensalt(rounds=12)).decode()

        await db.execute(
            "INSERT INTO users (username, password_hash, display_name, role) VALUES (?,?,?,?)",
            (ADMIN_USERNAME, admin_pw, "简禹豪", "admin")
        )

        # 为每个门店创建店长账号
        store_names_short = ["万象城", "万象汇", "兴义梦乐城", "遵义吾悦", "曲靖万达",
                             "六盘水", "龙湾万达", "昭通", "清镇吾悦", "安顺"]
        for i, short_name in enumerate(store_names_short):
            username = f"store{i+1}"
            await db.execute(
                "INSERT INTO users (username, password_hash, display_name, role, store_id) VALUES (?,?,?,?,?)",
                (username, store_pw, f"{short_name}店长", "manager", i + 1)
            )

        # 知识库分类
        categories = [
            ("产品知识", "📱", 1),
            ("销售话术", "💬", 2),
            ("SOP流程", "📋", 3),
            ("促销活动", "🏷️", 4),
            ("竞品分析", "⚔️", 5),
            ("客诉处理", "🛡️", 6),
        ]
        for name, icon, order in categories:
            await db.execute(
                "INSERT INTO kb_categories (name, icon, sort_order) VALUES (?,?,?)",
                (name, icon, order)
            )

        # 库存预警规则
        alert_rules = [
            ("S26", "per_store_color_spec", 1, 1),
            ("FOLD7", "per_store", 2, 1),
            ("FLIP7", "per_store", 1, 1),
            ("W26", "total", 10, 1),
        ]
        for series, rule_type, threshold, active in alert_rules:
            await db.execute(
                "INSERT INTO alert_rules (model_series, rule_type, threshold, is_active) VALUES (?,?,?,?)",
                (series, rule_type, threshold, active)
            )

        # 会员种子数据
        import datetime
        today = datetime.date.today().isoformat()

        members_data = [
            ("张伟", "13800138001", 1, "钻石", 158000, 15800, "2025-03-15", "S26忠实用户，已推荐5位客户"),
            ("李娜", "13900139002", 2, "金卡", 89000, 8900, "2025-06-20", "喜欢Flip系列"),
            ("王强", "13700137003", 3, "银卡", 32000, 3200, "2025-09-10", None),
            ("赵敏", "13600136004", 5, "普通", 8500, 850, "2026-01-05", "新客户，关注手表"),
            ("陈丽华", "13500135005", 4, "金卡", 72000, 7200, "2025-04-18", "企业团购客户"),
            ("刘建国", "13300133006", 1, "钻石", 210000, 21000, "2024-11-02", "万象城旗舰店VIP"),
            ("周晓燕", "13200132007", 7, "银卡", 28000, 2800, "2025-08-22", None),
            ("吴伟明", "13100131008", 8, "普通", 12000, 1200, "2026-02-14", None),
        ]

        for name, phone, store_id, level, spent, points, join_date, remark in members_data:
            await db.execute(
                "INSERT INTO members (name, phone, store_id, level, total_spent, points, join_date, remark) VALUES (?,?,?,?,?,?,?,?)",
                (name, phone, store_id, level, spent, points, join_date, remark)
            )

        # 消费记录种子数据
        purchases_data = [
            (1, 1, 12800, 12800, "Galaxy S26 Ultra 512GB", "2026-05-15"),
            (1, 1, 899, 899, "Galaxy Watch7", "2026-05-20"),
            (2, 2, 7800, 7800, "Galaxy Z Flip7 256GB", "2026-05-10"),
            (3, 3, 4500, 4500, "Galaxy S26 256GB", "2026-04-28"),
            (4, 5, 3999, 3999, "Galaxy Tab S10", "2026-05-01"),
            (5, 4, 5600, 5600, "Galaxy S26 256GB × 2", "2026-05-08"),
            (6, 1, 15800, 15800, "Galaxy S26 Ultra 1TB 限量版", "2026-05-18"),
            (7, 7, 5200, 5200, "Galaxy S26 256GB", "2026-05-12"),
            (2, 2, 1299, 1299, "Galaxy Buds3 Pro", "2026-05-25"),
            (3, 3, 350, 350, "原装硅胶保护壳", "2026-05-16"),
            (5, 4, 9800, 9800, "Galaxy Z Fold7 512GB", "2026-06-01"),
            (8, 8, 3200, 3200, "Galaxy A56 256GB", "2026-05-22"),
            (6, 1, 699, 699, "Galaxy Watch7 Classic", "2026-06-02"),
            (4, 5, 199, 199, "45W快充充电器", "2026-05-30"),
        ]

        for mid, sid, amount, points, info, date in purchases_data:
            await db.execute(
                "INSERT INTO member_purchases (member_id, store_id, amount, points_earned, product_info, purchase_date) VALUES (?,?,?,?,?,?)",
                (mid, sid, amount, points, info, date)
            )

        await db.commit()
        print("Seed data inserted: 10 stores, 11 users, 6 KB categories, 4 alert rules, 8 members, 14 purchases")

    # 种子数据2：提成规则 + 活动（幂等）
    await _seed_commission_rules()
    await _seed_default_activities()


async def _seed_commission_rules():
    """确保默认提成规则存在（幂等）"""
    async with aiosqlite.connect(DB_PATH_STR) as db:
        count = await db.execute("SELECT COUNT(*) FROM commission_rules")
        if (await count.fetchone())[0] > 0:
            return
        rules = [
            ("手机台量提成", "phone", "fixed", 50, 0),
            ("NCME销售额提成", "ncme", "percentage", 0, 0.03),
            ("配件销售额提成", "accessory", "percentage", 0, 0.05),
            ("以旧换新台量提成", "trade_in", "fixed", 20, 0),
        ]
        for name, ptype, ctype, fixed, rate in rules:
            await db.execute(
                "INSERT INTO commission_rules (rule_name, product_type, commission_type, commission_fixed, commission_rate) VALUES (?,?,?,?,?)",
                (name, ptype, ctype, fixed, rate))
        await db.commit()
        print("Seed: 4 commission rules inserted")


async def _seed_default_activities():
    """确保默认活动政策存在（幂等）"""
    async with aiosqlite.connect(DB_PATH_STR) as db:
        count = await db.execute("SELECT COUNT(*) FROM activities")
        if (await count.fetchone())[0] > 0:
            return
        activities = [
            ("S26系列新品上市", "S26 Ultra / S26+ 上市首销活动，到店体验送礼品", "2026-06-01", "2026-06-30"),
            ("以旧换新补贴", "任意品牌旧手机换购三星新机，最高补贴1000元", "2026-06-01", "2026-12-31"),
        ]
        for title, content, start, end in activities:
            await db.execute(
                "INSERT INTO activities (title, content, start_date, end_date) VALUES (?,?,?,?)",
                (title, content, start, end))
        await db.commit()
        print("Seed: 2 activities inserted")
