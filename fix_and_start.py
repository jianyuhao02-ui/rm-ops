"""
修复 samsung_ops.db 的 WAL 模式残留问题
双击运行即可，修复后自动启动管理平台
"""
import sqlite3
import os
import sys
import subprocess

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "samsung_ops.db")
VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", ".venv", "Scripts", "python.exe")

def fix_db():
    print(f"[1/3] 检查数据库: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print(f"  [!] 数据库文件不存在，将在启动时自动创建")
        return True

    # 检查 WAL/SHM 残留文件
    wal_path = DB_PATH + "-wal"
    shm_path = DB_PATH + "-shm"
    has_wal = os.path.exists(wal_path)
    has_shm = os.path.exists(shm_path)
    print(f"  WAL文件: {'存在' if has_wal else '不存在'}")
    print(f"  SHM文件: {'存在' if has_shm else '不存在'}")

    try:
        db = sqlite3.connect(DB_PATH)
        # 检查当前模式
        mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        print(f"  当前日志模式: {mode}")

        if mode == "wal":
            print("[2/3] 修复WAL模式...")
            # 尝试 checkpoint
            try:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                print("  WAL checkpoint 完成")
            except Exception as e:
                print(f"  WAL checkpoint 失败: {e}")

            # 切换到 DELETE 模式（更稳定）
            db.execute("PRAGMA journal_mode=DELETE")
            db.commit()
            new_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
            print(f"  新日志模式: {new_mode}")

        # 完整性检查
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        print(f"  完整性检查: {integrity}")
        db.close()

        if integrity != "ok":
            print("  [!] 数据库损坏，尝试修复...")
            # 尝试 dump 和恢复
            return repair_db()

        # 清理残留文件
        for p in [wal_path, shm_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                    print(f"  已删除残留: {os.path.basename(p)}")
                except:
                    pass

        print("[3/3] 数据库修复完成 ✓")
        return True

    except sqlite3.OperationalError as e:
        print(f"  [X] 数据库打开失败: {e}")

        # 终极修复：删除 WAL/SHM 文件
        for p in [wal_path, shm_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                    print(f"  已删除残留: {os.path.basename(p)}")
                except:
                    print(f"  删除失败: {os.path.basename(p)}")

        # 重试
        try:
            db = sqlite3.connect(DB_PATH)
            db.execute("PRAGMA journal_mode=DELETE")
            db.commit()
            db.close()
            print("  重试成功 ✓")
            return True
        except Exception as e2:
            print(f"  [X] 重试也失败: {e2}")
            return False

def repair_db():
    """通过 dump + 恢复修复损坏的数据库"""
    import tempfile
    try:
        backup_path = DB_PATH + ".bak"
        fixed_path = DB_PATH + ".fixed"

        # 导出 SQL
        db_old = sqlite3.connect(DB_PATH)
        with open(fixed_path + ".sql", "w", encoding="utf-8") as f:
            for line in db_old.iterdump():
                f.write(line + "\n")
        db_old.close()

        # 创建新数据库
        if os.path.exists(fixed_path):
            os.remove(fixed_path)
        db_new = sqlite3.connect(fixed_path)
        with open(fixed_path + ".sql", "r", encoding="utf-8") as f:
            sql = f.read()
            db_new.executescript(sql)
        db_new.execute("PRAGMA journal_mode=DELETE")
        db_new.commit()
        db_new.close()

        # 替换
        os.replace(DB_PATH, backup_path)
        os.replace(fixed_path, DB_PATH)
        os.remove(fixed_path + ".sql")

        print(f"  修复成功，备份保存至: {backup_path}")
        return True
    except Exception as e:
        print(f"  [X] 修复失败: {e}")
        return False

def start_server():
    print("\n" + "=" * 40)
    print("  启动三星事业部管理平台...")
    print("  访问地址: http://localhost:9527")
    print("  管理员: admin / admin123")
    print("=" * 40 + "\n")

    # 自动打开浏览器
    import webbrowser
    webbrowser.open("http://localhost:9527")

    # 启动服务
    cmd = [VENV_PYTHON, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9527", "--app-dir", os.path.dirname(os.path.abspath(__file__))]
    subprocess.run(cmd)

if __name__ == "__main__":
    print("=" * 40)
    print("  三星管理平台 - 数据库修复工具")
    print("=" * 40 + "\n")

    if fix_db():
        start_server()
    else:
        print("\n[!] 数据库修复失败，请检查错误信息")
        print("[*] 按任意键退出...")
        input()
