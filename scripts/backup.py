"""
数据库备份与恢复工具
支持手动备份、自动清理、从备份恢复
"""
import os
import sys
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path(__file__).parent.parent / "data" / "samsung_ops.db"
BACKUP_DIR = Path.home() / "Desktop" / "samsung_ops_backup"
RETENTION_DAYS = 7


def backup_database(backup_dir: Path = None, keep_days: int = None):
    """备份数据库"""
    backup_dir = backup_dir or BACKUP_DIR
    keep_days = keep_days or RETENTION_DAYS

    if not DB_PATH.exists():
        print(f"[X] 数据库文件不存在: {DB_PATH}")
        return False

    backup_dir.mkdir(parents=True, exist_ok=True)

    # 先执行 checkpoint
    try:
        db = sqlite3.connect(str(DB_PATH))
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.close()
    except Exception:
        pass

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"samsung_ops_{timestamp}.db"
    backup_path = backup_dir / backup_name

    try:
        shutil.copy2(str(DB_PATH), str(backup_path))
        size_kb = backup_path.stat().st_size / 1024
        print(f"[OK] 备份完成: {backup_name} ({size_kb:.1f} KB)")

        # 清理旧备份
        cutoff = datetime.now() - timedelta(days=keep_days)
        deleted = 0
        for f in backup_dir.glob("samsung_ops_*.db"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                deleted += 1

        if deleted > 0:
            print(f"[*] 清理了 {deleted} 个旧备份文件（保留{keep_days}天）")

        return True
    except Exception as e:
        print(f"[X] 备份失败: {e}")
        return False


def restore_database(backup_file: str):
    """从备份恢复数据库"""
    backup_path = Path(backup_file)
    if not backup_path.exists():
        print(f"[X] 备份文件不存在: {backup_path}")
        return False

    # 先备份当前数据库
    if DB_PATH.exists():
        bak = DB_PATH.with_suffix(".db.before_restore")
        shutil.copy2(str(DB_PATH), str(bak))
        print(f"[*] 当前数据库已备份至: {bak}")

    try:
        shutil.copy2(str(backup_path), str(DB_PATH))

        # 验证恢复后的数据库
        db = sqlite3.connect(str(DB_PATH))
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        db.close()

        if integrity == "ok":
            print(f"[OK] 数据库恢复成功！")
            return True
        else:
            print(f"[X] 恢复后数据库校验失败: {integrity}")
            return False
    except Exception as e:
        print(f"[X] 恢复失败: {e}")
        return False


def list_backups():
    """列出所有备份文件"""
    if not BACKUP_DIR.exists():
        print("无备份目录")
        return

    backups = sorted(BACKUP_DIR.glob("samsung_ops_*.db"), reverse=True)
    if not backups:
        print("无备份文件")
        return

    print(f"备份目录: {BACKUP_DIR}")
    print(f"共 {len(backups)} 个备份文件:\n")
    for f in backups:
        size_kb = f.stat().st_size / 1024
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {f.name}  ({size_kb:.1f} KB, {mtime})")


def check_database():
    """检查数据库完整性"""
    if not DB_PATH.exists():
        print(f"[X] 数据库文件不存在: {DB_PATH}")
        return

    print(f"数据库: {DB_PATH}")
    print(f"大小: {DB_PATH.stat().st_size / 1024:.1f} KB")

    db = sqlite3.connect(str(DB_PATH))
    try:
        # 完整性检查
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        print(f"完整性: {integrity}")

        # 各表记录数
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"\n表统计:")
        for (name,) in tables:
            if name.startswith("_"):
                continue
            count = db.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
            print(f"  {name}: {count} 条")

    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="三星事业部管理平台 - 数据库备份工具")
    parser.add_argument("action", nargs="?", default="backup",
                       choices=["backup", "restore", "list", "check"],
                       help="操作: backup(备份) restore(恢复) list(列表) check(检查)")
    parser.add_argument("--file", "-f", help="恢复时指定备份文件路径")
    parser.add_argument("--keep", "-k", type=int, default=7, help="保留天数（默认7天）")

    args = parser.parse_args()

    print("=" * 50)
    print("  三星事业部管理平台 - 数据库工具")
    print("=" * 50)
    print()

    if args.action == "backup":
        backup_database(keep_days=args.keep)
    elif args.action == "restore":
        if not args.file:
            list_backups()
            print("\n请使用 --file 参数指定要恢复的备份文件")
        else:
            restore_database(args.file)
    elif args.action == "list":
        list_backups()
    elif args.action == "check":
        check_database()

    print()
    input("按任意键退出...")
