"""
系统健康监控脚本
可用于 Windows 计划任务或外部监控系统调用
用法: python scripts/monitor.py [--alert]
"""
import os
import sys
import json
import sqlite3
import urllib.request
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path(__file__).parent.parent / "data" / "samsung_ops.db"
LOGS_DIR = Path(__file__).parent.parent / "logs"
HEALTH_URL = "http://localhost:9527/api/health"


def check_api_health():
    """检查 API 是否正常运行"""
    try:
        req = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "ok"
    except Exception:
        return False


def check_database():
    """检查数据库完整性"""
    if not DB_PATH.exists():
        return {"status": "error", "message": "数据库文件不存在"}

    try:
        db = sqlite3.connect(str(DB_PATH))
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        size_kb = DB_PATH.stat().st_size / 1024

        # 检查各表记录数
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_stats = {}
        for (name,) in tables:
            if name.startswith("_"):
                continue
            table_stats[name] = db.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]

        db.close()
        return {
            "status": "ok" if integrity == "ok" else "error",
            "integrity": integrity,
            "size_kb": round(size_kb, 1),
            "tables": table_stats
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_disk_space():
    """检查磁盘空间"""
    try:
        import shutil
        usage = shutil.disk_usage(str(Path(__file__).parent.parent))
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        percent = (1 - usage.free / usage.total) * 100
        return {
            "status": "warning" if free_gb < 1 else "ok",
            "free_gb": round(free_gb, 2),
            "total_gb": round(total_gb, 2),
            "used_percent": round(percent, 1)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_recent_errors():
    """检查最近的错误日志"""
    log_file = LOGS_DIR / "error.log"
    if not log_file.exists():
        return {"status": "ok", "recent_errors": 0}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 统计最近1小时的错误
        import re
        recent_errors = 0
        for line in lines[-200:]:  # 检查最后200行
            if "ERROR" in line or "CRITICAL" in line:
                recent_errors += 1

        return {
            "status": "warning" if recent_errors > 10 else "ok",
            "recent_errors": recent_errors
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def run_health_check():
    """运行完整健康检查"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "api": check_api_health(),
        "database": check_database(),
        "disk": check_disk_space(),
        "errors": check_recent_errors(),
    }

    # 综合状态
    all_ok = all(
        r == "ok" or r == True
        for k, v in results.items()
        if k != "timestamp" and isinstance(v, (str, bool))
    )

    results["overall"] = "healthy" if all_ok else "unhealthy"

    return results


def print_report(results: dict):
    """打印健康报告"""
    status_icon = {
        "healthy": "🟢",
        "unhealthy": "🔴",
        "ok": "✅",
        "error": "❌",
        "warning": "⚠️",
        True: "✅",
        False: "❌",
    }

    print("=" * 50)
    print(f"  系统健康检查报告")
    print(f"  时间: {results['timestamp']}")
    print("=" * 50)
    print()

    overall = results["overall"]
    print(f"综合状态: {status_icon.get(overall, '❓')} {overall.upper()}")
    print()

    # API 状态
    api_ok = results["api"]
    print(f"API 服务:  {status_icon.get(api_ok, '❓')} {'正常' if api_ok else '异常'}")
    print(f"  地址: {HEALTH_URL}")

    # 数据库
    db = results["database"]
    if isinstance(db, dict):
        db_status = db.get("status", "unknown")
        print(f"数据库:    {status_icon.get(db_status, '❓')} {db.get('integrity', db_status)}")
        if "size_kb" in db:
            print(f"  大小: {db['size_kb']} KB")
        if "tables" in db:
            print(f"  数据表: {len(db['tables'])} 张")
    else:
        print(f"数据库:    {status_icon.get('error', '❓')} 检查失败")

    # 磁盘
    disk = results["disk"]
    if isinstance(disk, dict) and "free_gb" in disk:
        d_status = disk.get("status", "unknown")
        print(f"磁盘空间:  {status_icon.get(d_status, '❓')} {disk['free_gb']} GB 可用 / {disk['total_gb']} GB 总计 ({disk['used_percent']}%)")

    # 错误日志
    errors = results["errors"]
    if isinstance(errors, dict) and "recent_errors" in errors:
        e_status = errors.get("status", "unknown")
        print(f"近期错误:  {status_icon.get(e_status, '❓')} {errors['recent_errors']} 条")

    print()
    print("=" * 50)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="系统健康监控")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--alert", action="store_true", help="异常时发送告警")

    args = parser.parse_args()

    results = run_health_check()

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_report(results)

    # 异常时退出码为 1
    if results["overall"] != "healthy":
        sys.exit(1)
