# 三星事业部管理平台 - Docker 镜像
FROM python:3.11-slim

LABEL maintainer="贵州沣范通讯"
LABEL description="三星事业部运营管理平台"

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY main.py .
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY data/ ./data/

# 创建必要目录
RUN mkdir -p logs data

# 暴露端口
EXPOSE 9527

# 环境变量
ENV SAMSUNG_HOST=0.0.0.0
ENV SAMSUNG_PORT=9527
ENV SAMSUNG_SCHEDULER_ENABLED=true

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9527/api/health')" || exit 1

# 启动服务
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9527"]
