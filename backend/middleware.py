"""
中间件和异常处理
提供请求日志、异常统一处理、请求限流
"""
import time
import traceback
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.logger import app_logger, error_logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件：记录每个API请求的耗时和状态码"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
            elapsed_ms = (time.time() - start_time) * 1000
            status_code = response.status_code

            # 只记录 API 请求
            if path.startswith("/api/"):
                app_logger.info(
                    f"{method} {path} → {status_code} ({elapsed_ms:.0f}ms)"
                )

            return response

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            error_logger.error(
                f"{method} {path} → 500 ({elapsed_ms:.0f}ms): {e}\n{traceback.format_exc()}"
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "服务器内部错误", "error": str(e) if app_logger.level <= 10 else ""}
            )


# ==================== 全局异常处理器 ====================

async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 异常统一处理"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code}
    )


async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理"""
    error_logger.error(
        f"未捕获异常 {request.method} {request.url.path}: {exc}\n{traceback.format_exc()}"
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误，请联系管理员",
            "status_code": 500
        }
    )


async def validation_exception_handler(request: Request, exc):
    """请求参数验证异常处理"""
    from fastapi.exceptions import RequestValidationError

    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })

    return JSONResponse(
        status_code=422,
        content={
            "detail": "请求参数验证失败",
            "errors": errors
        }
    )
