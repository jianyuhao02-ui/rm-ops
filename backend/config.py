"""
三星事业部管理平台 - 配置管理模块
支持环境变量覆盖，方便不同环境部署
"""
import os
from pathlib import Path

# 自动加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv 未安装，跳过自动加载

# ==================== 项目路径 ====================
PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"
LOGS_DIR = PROJECT_DIR / "logs"
FRONTEND_DIR = PROJECT_DIR / "frontend"
DB_PATH = DATA_DIR / "samsung_ops.db"

# ==================== 服务器配置 ====================
HOST = os.getenv("SAMSUNG_HOST", "0.0.0.0")
PORT = int(os.getenv("SAMSUNG_PORT", "9527"))
DEBUG = os.getenv("SAMSUNG_DEBUG", "false").lower() == "true"

# ==================== JWT 认证 ====================
SECRET_KEY = os.getenv("SAMSUNG_SECRET_KEY", "samsung-ops-2026-secret-key-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = int(os.getenv("SAMSUNG_TOKEN_EXPIRE_HOURS", "72"))

# ==================== 数据库 ====================
DB_JOURNAL_MODE = os.getenv("SAMSUNG_DB_JOURNAL_MODE", "delete")  # delete/wal
DB_BACKUP_DIR = os.getenv("SAMSUNG_BACKUP_DIR", str(Path.home() / "Desktop" / "samsung_ops_backup"))
DB_BACKUP_RETENTION_DAYS = int(os.getenv("SAMSUNG_BACKUP_RETENTION_DAYS", "7"))

# ==================== 钉钉配置 ====================
DINGTALK_ADMIN_USER_ID = os.getenv("SAMSUNG_DINGTALK_ADMIN_USER_ID", "16381712592737652")
DINGTALK_ROBOT_WEBHOOK = os.getenv("SAMSUNG_DINGTALK_ROBOT_WEBHOOK", "")
DINGTALK_ACCESS_TOKEN = os.getenv("SAMSUNG_DINGTALK_ACCESS_TOKEN", "")

# ==================== eBoss 配置 ====================
EBOSS_SCAN_DIR = os.getenv("SAMSUNG_EBOSS_DIR", r"C:\eBoss\Local")

# ==================== 定时任务配置 ====================
SCHEDULER_ENABLED = os.getenv("SAMSUNG_SCHEDULER_ENABLED", "true").lower() == "true"
INVENTORY_ALERT_DAYS = os.getenv("SAMSUNG_INVENTORY_ALERT_DAYS", "mon,thu")
INVENTORY_ALERT_HOUR = int(os.getenv("SAMSUNG_INVENTORY_ALERT_HOUR", "9"))
INVENTORY_ALERT_MINUTE = int(os.getenv("SAMSUNG_INVENTORY_ALERT_MINUTE", "30"))
PRICE_CHECK_HOUR = int(os.getenv("SAMSUNG_PRICE_CHECK_HOUR", "10"))
BACKUP_HOUR = int(os.getenv("SAMSUNG_BACKUP_HOUR", "3"))
EBOSS_SCAN_INTERVAL_MINUTES = int(os.getenv("SAMSUNG_EBOSS_SCAN_INTERVAL", "60"))

# ==================== 管理员默认配置 ====================
ADMIN_USERNAME = os.getenv("SAMSUNG_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("SAMSUNG_ADMIN_PASSWORD", "admin123")
STORE_MANAGER_PASSWORD = os.getenv("SAMSUNG_STORE_PASSWORD", "store123")

# ==================== CORS 配置 ====================
CORS_ORIGINS = os.getenv("SAMSUNG_CORS_ORIGINS", "*").split(",")

# ==================== AI 智能助手配置 ====================
AI_API_KEY = os.getenv("SAMSUNG_AI_API_KEY", "")
AI_BASE_URL = os.getenv("SAMSUNG_AI_BASE_URL", "https://api.deepseek.com/v1")
AI_MODEL = os.getenv("SAMSUNG_AI_MODEL", "deepseek-chat")
AI_MAX_TOKENS = int(os.getenv("SAMSUNG_AI_MAX_TOKENS", "2000"))
AI_TEMPERATURE = float(os.getenv("SAMSUNG_AI_TEMPERATURE", "0.3"))
AI_MAX_HISTORY = int(os.getenv("SAMSUNG_AI_MAX_HISTORY", "20"))
AI_RATE_LIMIT = int(os.getenv("SAMSUNG_AI_RATE_LIMIT", "30"))  # 每分钟请求数

# ==================== 日志配置 ====================
LOG_LEVEL = os.getenv("SAMSUNG_LOG_LEVEL", "INFO")
LOG_FILE = LOGS_DIR / "samsung-ops.log"
SCHEDULER_LOG_FILE = LOGS_DIR / "scheduler.log"


def ensure_dirs():
    """确保所有必要目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    # 上传文件目录（不存在时自动创建）
    os.makedirs(FRONTEND_DIR / "uploads", exist_ok=True)


def get_config_summary() -> dict:
    """获取配置摘要（隐藏敏感信息）"""
    return {
        "host": HOST,
        "port": PORT,
        "debug": DEBUG,
        "db_path": str(DB_PATH),
        "db_journal_mode": DB_JOURNAL_MODE,
        "eboss_scan_dir": EBOSS_SCAN_DIR,
        "scheduler_enabled": SCHEDULER_ENABLED,
        "backup_dir": str(DB_BACKUP_DIR),
        "log_level": LOG_LEVEL,
    }
