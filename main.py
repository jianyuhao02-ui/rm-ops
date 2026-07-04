"""
三星事业部统一管理平台 - 主入口
FastAPI + SQLite + JWT Auth + APScheduler
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import os

from backend.config import (
    CORS_ORIGINS, FRONTEND_DIR, PROJECT_DIR, PORT, HOST, ensure_dirs, get_config_summary, DEBUG, SCHEDULER_ENABLED
)
from backend.logger import app_logger
from backend.middleware import (
    RequestLoggingMiddleware,
    http_exception_handler,
    general_exception_handler,
    validation_exception_handler,
)

# 确保必要目录存在
ensure_dirs()


# ==================== 生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理（FastAPI 推荐方式）"""
    # 启动
    app_logger.info("=" * 50)
    app_logger.info("零售管理平台 v2.1 正在启动...")
    app_logger.info(f"配置: {get_config_summary()}")

    from backend.models.database import init_db
    await init_db()
    app_logger.info("数据库初始化完成")

    # 启动定时任务调度器
    if SCHEDULER_ENABLED:
        from backend.services.scheduler_service import start_scheduler
        start_scheduler()
        app_logger.info("定时任务调度器已启动")
    else:
        app_logger.info("定时任务调度器已禁用（RM_SCHEDULER_ENABLED=false）")

    app_logger.info(f"服务已就绪，访问 http://localhost:{PORT}")
    app_logger.info("=" * 50)

    yield

    # 关闭
    from backend.services.scheduler_service import stop_scheduler
    from backend.models.database import close_db
    stop_scheduler()
    await close_db()
    app_logger.info("服务已安全关闭")


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="零售管理统一管理平台",
    version="2.1.0",
    description="贵州沣范通讯设备有限公司 - 零售管理运营平台",
    docs_url="/api/docs" if DEBUG else None,
    redoc_url=None,
    lifespan=lifespan,
)

# ==================== 中间件 ====================

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求日志中间件
app.add_middleware(RequestLoggingMiddleware)

# ==================== 异常处理器 ====================

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# ==================== API 路由 ====================

from backend.api import auth, sales, inventory, prices, knowledge, community, notify, eboss, member, analytics, staff, chat, upload, attendance, approval, tasks, orders

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(sales.router, prefix="/api/sales", tags=["销售"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["库存"])
app.include_router(prices.router, prefix="/api/prices", tags=["价格"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识库"])
app.include_router(community.router, prefix="/api/community", tags=["社区"])
app.include_router(notify.router, prefix="/api/notify", tags=["通知"])
app.include_router(eboss.router, prefix="/api/eboss", tags=["eBoss"])
app.include_router(member.router, prefix="/api/member", tags=["会员管理"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["数据分析"])
app.include_router(staff.router, prefix="/api/staff", tags=["店员管理"])
app.include_router(chat.router, prefix="/api/chat", tags=["AI助手"])
app.include_router(upload.router, prefix="/api/upload", tags=["文件上传"])
app.include_router(attendance.router, prefix="/api/attendance", tags=["考勤打卡"])
app.include_router(approval.router, prefix="/api/approval", tags=["审批"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["任务管理"])
app.include_router(orders.router, prefix="/api/orders", tags=["订单管理"])

# ==================== 健康检查与系统信息 ====================

@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "version": "2.1.0", "timestamp": __import__('datetime').datetime.now().isoformat()}


@app.get("/api/system/info")
async def system_info():
    """系统信息端点"""
    return {
        "version": "2.1.0",
        "config": get_config_summary(),
        "python_version": os.sys.version,
    }

# ==================== 前端页面路由 ====================

FRONTEND_PATH = str(FRONTEND_DIR)

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_PATH, "index.html"))

@app.get("/login")
def serve_login():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "login.html"))

@app.get("/dashboard")
def serve_dashboard():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "dashboard.html"))

@app.get("/sales")
def serve_sales():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "sales.html"))

@app.get("/inventory")
def serve_inventory():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "inventory.html"))

@app.get("/prices")
def serve_prices():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "prices.html"))

@app.get("/knowledge")
def serve_knowledge():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "knowledge.html"))

@app.get("/community")
def serve_community():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "community.html"))

@app.get("/admin")
def serve_admin():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "admin.html"))

@app.get("/members")
def serve_members():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "members.html"))

@app.get("/staff")
def serve_staff():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "staff.html"))

@app.get("/ai")
def serve_ai():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "ai.html"))

@app.get("/attendance")
def serve_attendance():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "attendance.html"))

@app.get("/approval")
def serve_approval():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "approval.html"))

@app.get("/tasks")
def serve_tasks():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "tasks.html"))

@app.get("/order-entry")
def serve_order_entry():
    return FileResponse(os.path.join(FRONTEND_PATH, "pages", "order-entry.html"))

# PWA 文件
@app.get("/manual")
def serve_manual():
    """使用手册（Markdown 渲染为 HTML）"""
    import markdown
    md_path = os.path.join(FRONTEND_PATH, "manual.md")
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()
    html_body = markdown.markdown(md_content, extensions=["tables", "fenced_code", "toc"])
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>使用手册 - 零售管理系统</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 40px 24px; color: #1a1a2e; line-height: 1.8; background: #f8fa[...]
  h1 {{ font-size: 2em; border-bottom: 3px solid #1428a0; padding-bottom: 12px; }}
  h2 {{ font-size: 1.5em; margin-top: 40px; color: #1428a0; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }}
  h3 {{ font-size: 1.2em; color: #2d3748; margin-top: 24px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
  th, td {{ border: 1px solid #e2e8f0; padding: 10px 14px; text-align: left; }}
  th {{ background: #1428a0; color: #fff; font-weight: 600; }}
  tr:nth-child(even) {{ background: #f1f5f9; }}
  code {{ background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }}
  pre {{ background: #1a1a2e; color: #e2e8f0; padding: 16px; border-radius: 8px; overflow-x: auto; }}
  blockquote {{ border-left: 4px solid #1428a0; padding: 8px 16px; margin: 16px 0; background: #eef2ff; border-radius: 0 8px 8px 0; }}
  hr {{ border: none; border-top: 1px solid #e2e8f0; margin: 32px 0; }}
  .back-link {{ display: inline-block; margin-bottom: 24px; color: #1428a0; text-decoration: none; font-weight: 500; }}
  a {{ color: #1428a0; }}
  @media (max-width: 768px) {{ body {{ padding: 16px; }} h1 {{ font-size: 1.5em; }} }}
</style>
</head>
<body>
<a class="back-link" href="/dashboard">← 返回系统</a>
{html_body}
<p style="margin-top:48px;padding-top:24px;border-top:1px solid #e2e8f0;color:#94a3b8;font-size:0.85em;">零售管理运营平台 v2.1 · 最后更新：2026年6月8日</p>
</body>
</html>"""
    return HTMLResponse(content=html)

@app.get("/manifest.json")
def serve_manifest():
    return FileResponse(os.path.join(FRONTEND_PATH, "manifest.json"), media_type="application/manifest+json")

@app.get("/sw.js")
def serve_sw():
    return FileResponse(os.path.join(FRONTEND_PATH, "sw.js"), media_type="application/javascript")

# 静态资源
app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_PATH, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_PATH, "js")), name="js")
app.mount("/icons", StaticFiles(directory=os.path.join(FRONTEND_PATH, "icons")), name="icons")
app.mount("/uploads", StaticFiles(directory=os.path.join(FRONTEND_PATH, "uploads")), name="uploads")


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    app_logger.info(f"启动开发服务器: http://{HOST}:{PORT}")
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False, log_level="info")
