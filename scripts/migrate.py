"""
数据库迁移工具
用于在不同版本间迁移数据库结构，确保向后兼容
"""
import sqlite3
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))
DB_PATH = str(Path(__file__).parent.parent / "data" / "samsung_ops.db")


def get_db_version(db: sqlite3.Connection) -> int:
    """获取当前数据库版本"""
    try:
        db.execute("CREATE TABLE IF NOT EXISTS _db_version (version INTEGER)")
        cursor = db.execute("SELECT MAX(version) FROM _db_version")
        row = cursor.fetchone()
        return row[0] if row[0] else 0
    except Exception:
        return 0


def set_db_version(db: sqlite3.Connection, version: int):
    """设置数据库版本"""
    db.execute("INSERT OR REPLACE INTO _db_version (version) VALUES (?)", (version,))


def migrate_v1_to_v2(db: sqlite3.Connection):
    """V1 → V2: 添加 likes 字段到 community_posts"""
    print("  [v2] 添加 community_posts.likes 字段...")
    try:
        db.execute("ALTER TABLE community_posts ADD COLUMN likes INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        print("    (字段已存在，跳过)")


def migrate_v2_to_v3(db: sqlite3.Connection):
    """V2 → V3: 添加 source 字段到 daily_sales"""
    print("  [v3] 添加 daily_sales.source 字段...")
    try:
        db.execute("ALTER TABLE daily_sales ADD COLUMN source TEXT DEFAULT 'dingtalk'")
    except sqlite3.OperationalError:
        print("    (字段已存在，跳过)")


def migrate_v3_to_v4(db: sqlite3.Connection):
    """V3 → V4: 添加 trade_in_rate 字段到 monthly_targets"""
    print("  [v4] 添加 monthly_targets.trade_in_rate 字段...")
    try:
        db.execute("ALTER TABLE monthly_targets ADD COLUMN trade_in_rate REAL DEFAULT 0")
    except sqlite3.OperationalError:
        print("    (字段已存在，跳过)")


def migrate_v4_to_v5(db: sqlite3.Connection):
    """V4 → V5: 添加会员表新字段"""
    print("  [v5] 添加会员相关新字段...")
    migrations = [
        "ALTER TABLE members ADD COLUMN is_vip INTEGER DEFAULT 0",
        "ALTER TABLE member_purchases ADD COLUMN model_code TEXT DEFAULT ''",
        "ALTER TABLE member_purchases ADD COLUMN spec TEXT DEFAULT ''",
        "ALTER TABLE member_purchases ADD COLUMN color TEXT DEFAULT ''",
        "ALTER TABLE member_purchases ADD COLUMN imei TEXT DEFAULT ''",
        "ALTER TABLE member_purchases ADD COLUMN trade_in_model TEXT DEFAULT ''",
        "ALTER TABLE member_purchases ADD COLUMN trade_in_amount REAL DEFAULT 0",
    ]
    for sql in migrations:
        try:
            db.execute(sql)
        except sqlite3.OperationalError:
            pass  # 字段已存在则跳过


def migrate_v5_to_v6(db: sqlite3.Connection):
    """V5 → V6: 添加性能索引"""
    print("  [v6] 添加性能索引...")
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_daily_sales_date ON daily_sales(date)",
        "CREATE INDEX IF NOT EXISTS idx_daily_sales_store_date ON daily_sales(store_id, date)",
        "CREATE INDEX IF NOT EXISTS idx_daily_sales_source ON daily_sales(source)",
        "CREATE INDEX IF NOT EXISTS idx_price_records_model ON price_records(model_code, spec, platform)",
        "CREATE INDEX IF NOT EXISTS idx_inventory_store_model ON inventory(store_id, model_code)",
        "CREATE INDEX IF NOT EXISTS idx_community_comments_post ON community_comments(post_id)",
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read)",
        "CREATE INDEX IF NOT EXISTS idx_eboss_sync_log_file ON eboss_sync_log(file_name)",
        "CREATE INDEX IF NOT EXISTS idx_kb_articles_category ON kb_articles(category_id)",
        "CREATE INDEX IF NOT EXISTS idx_members_phone ON members(phone)",
        "CREATE INDEX IF NOT EXISTS idx_members_store ON members(store_id)",
        "CREATE INDEX IF NOT EXISTS idx_members_level ON members(level)",
        "CREATE INDEX IF NOT EXISTS idx_purchases_member ON member_purchases(member_id)",
        "CREATE INDEX IF NOT EXISTS idx_member_tags_member ON member_tags(member_id)",
        "CREATE INDEX IF NOT EXISTS idx_member_followups_member ON member_followups(member_id)",
    ]
    for sql in indexes:
        db.execute(sql)


MIGRATIONS = [
    migrate_v1_to_v2,
    migrate_v2_to_v3,
    migrate_v3_to_v4,
    migrate_v4_to_v5,
    migrate_v5_to_v6,
]


def run_migrations(db_path: str = None):
    """执行所有待处理的迁移"""
    db_path = db_path or DB_PATH

    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        print("将在首次启动时自动创建")
        return

    print(f"数据库: {db_path}")
    db = sqlite3.connect(db_path)

    try:
        current_version = get_db_version(db)
        print(f"当前版本: v{current_version}")

        if current_version >= len(MIGRATIONS):
            print("数据库已是最新版本，无需迁移")
            return

        for i in range(current_version, len(MIGRATIONS)):
            print(f"\n执行迁移 v{i} → v{i + 1}:")
            MIGRATIONS[i](db)
            set_db_version(db, i + 1)
            db.commit()

        print(f"\n迁移完成！当前版本: v{len(MIGRATIONS)}")

    except Exception as e:
        print(f"\n[X] 迁移失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("  三星事业部管理平台 - 数据库迁移工具")
    print("=" * 50)
    print()
    run_migrations()
    print()
    input("按任意键退出...")
