#!/usr/bin/env python3
"""
scripts/clear_data.py

用于清空数据库中用户可产生的数据（保留表结构和索引），或备份并删除 DB 文件。
默认行为会提示并创建备份。可使用 --yes 直接执行。
"""
import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

from backend.config import DB_PATH

TABLES_TO_CLEAR = [
    # 列出要清空的业务数据表（保留 schema）
    'users', 'stores', 'monthly_targets', 'daily_sales', 'inventory', 'price_records',
    'kb_categories', 'kb_articles', 'community_posts', 'community_comments', 'notifications',
    'alert_rules', 'members', 'member_purchases', 'member_tag_defs', 'member_tags', 'member_followups',
    'attendance_records', 'approvals', 'tasks', 'staff', 'staff_sales', 'staff_targets',
    'commission_rules', 'activities', 'sales_orders', 'eboss_sync_log'
]


def backup_db(db_path: Path):
    bak = db_path.with_suffix(db_path.suffix + '.bak')
    shutil.copy2(db_path, bak)
    return bak


def clear_tables(db_path: Path):
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute('PRAGMA foreign_keys=OFF')
    for t in TABLES_TO_CLEAR:
        try:
            cur.execute(f'DELETE FROM {t}')
            cur.execute(f"DELETE FROM sqlite_sequence WHERE name='{t}'")
            print(f'Cleared table: {t}')
        except Exception as e:
            print(f'Warning: failed to clear {t}: {e}')
    cur.execute('PRAGMA foreign_keys=ON')
    con.commit()
    con.close()


def delete_db(db_path: Path):
    db_path.unlink()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--yes', action='store_true', help='Skip confirmation')
    p.add_argument('--delete-file', action='store_true', help='Delete DB file instead of clearing tables')
    args = p.parse_args()

    db_path = Path(DB_PATH)
    if not db_path.exists():
        print('Database file not found:', db_path)
        sys.exit(1)

    if not args.yes:
        print('This will BACKUP and then clear business data from:', db_path)
        yn = input('Proceed? (y/N): ').strip().lower()
        if yn != 'y':
            print('Aborted')
            sys.exit(0)

    bak = backup_db(db_path)
    print('Backup created at', bak)

    if args.delete_file:
        delete_db(db_path)
        print('DB file deleted. You can restart the app to recreate an empty DB.')
    else:
        clear_tables(db_path)
        print('Data cleared. Schema preserved.')


if __name__ == '__main__':
    main()
