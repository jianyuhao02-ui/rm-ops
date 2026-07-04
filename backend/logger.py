"""
统一日志管理模块
提供结构化日志、请求追踪、异常捕获
"""
import logging
import sys
import time
from pathlib import Path
from logging.handlers import RotatingFileHandler

from backend.config import LOG_LEVEL, LOGS_DIR, LOG_FILE, SCHEDULER_LOG_FILE


class ColoredFormatter(logging.Formatter):
    """带颜色的控制台日志格式化器"""
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
    }
    RESET = '\033[0m'

    def format(self, record):
        log_msg = super().format(record)
        color = self.COLORS.get(record.levelname, '')
        if color:
            log_msg = f"{color}{log_msg}{self.RESET}"
        return log_msg


def setup_logger(
    name: str,
    log_file: Path = None,
    level: str = None,
    console: bool = True,
    file: bool = True,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5
) -> logging.Logger:
    """
    创建并配置日志器

    Args:
        name: 日志器名称
        log_file: 日志文件路径
        level: 日志级别
        console: 是否输出到控制台
        file: 是否输出到文件
        max_bytes: 日志文件最大大小
        backup_count: 备份文件数量

    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level or LOG_LEVEL)
    logger.propagate = False

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColoredFormatter(log_format, date_format))
        logger.addHandler(console_handler)

    if file and log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        logger.addHandler(file_handler)

    return logger


def setup_access_logger() -> logging.Logger:
    """创建 API 访问日志器"""
    log_file = LOGS_DIR / "access.log"
    return setup_logger("access", log_file, level="INFO", console=False)


def get_request_logger():
    """创建带请求追踪的日志器"""
    return setup_logger("request", LOGS_DIR / "requests.log", level="INFO", console=False)


# 预创建常用日志器
app_logger = setup_logger("app", LOG_FILE, console=True)
scheduler_logger = setup_logger("scheduler", SCHEDULER_LOG_FILE, console=True)
db_logger = setup_logger("database", LOGS_DIR / "database.log", console=False)
error_logger = setup_logger("error", LOGS_DIR / "error.log", console=True)


def log_execution_time(logger: logging.Logger = None):
    """装饰器：记录函数执行时间"""
    logger = logger or app_logger

    def decorator(func):
        from functools import wraps

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start
                logger.debug(f"{func.__name__} 执行耗时: {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"{func.__name__} 执行失败 ({elapsed:.3f}s): {e}")
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                logger.debug(f"{func.__name__} 执行耗时: {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"{func.__name__} 执行失败 ({elapsed:.3f}s): {e}")
                raise

        import asyncio
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
