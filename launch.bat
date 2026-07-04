@echo off
chcp 65001 >nul
title 三星事业部管理平台 v2.1
echo.
echo  ========================================
echo    三星事业部统一管理平台 v2.1
echo    贵州沣范通讯设备有限公司
echo  ========================================
echo.

cd /d "%~dp0"

REM ==================== 环境检查 ====================

REM 检查 Python
set PYTHON_EXE=
if exist "backend\.venv\Scripts\python.exe" (
    set PYTHON_EXE=backend\.venv\Scripts\python.exe
) else (
    REM 尝试系统 Python
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        for /f "delims=" %%i in ('where python') do set PYTHON_EXE=%%i
        goto :found_python
    )
    echo [X] 未找到 Python，请安装 Python 3.10+
    pause
    exit /b 1
)
:found_python

REM 检查/创建虚拟环境
if not exist "backend\.venv\Scripts\python.exe" (
    echo [!] 未找到虚拟环境，正在创建...
    %PYTHON_EXE% -m venv backend\.venv
    if errorlevel 1 (
        echo [X] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [OK] 虚拟环境创建成功
)

REM 设置虚拟环境 Python
set VENV_PYTHON=backend\.venv\Scripts\python.exe

REM 检查依赖
echo [*] 检查依赖...
%VENV_PYTHON% -c "import fastapi, uvicorn, jwt, aiosqlite, apscheduler" 2>nul
if errorlevel 1 (
    echo [!] 安装依赖...
    backend\.venv\Scripts\pip.exe install fastapi "uvicorn[standard]" pyjwt aiosqlite python-multipart APScheduler httpx xlrd openpyxl
    if errorlevel 1 (
        echo [X] 依赖安装失败
        pause
        exit /b 1
    )
    echo [OK] 依赖安装完成
)

REM ==================== 目录准备 ====================

if not exist "logs" mkdir logs
if not exist "data" mkdir data

REM ==================== 数据库修复 ====================

echo [*] 检查数据库状态...
%VENV_PYTHON% -c "import sqlite3, os; p=r'data\samsung_ops.db'; db=sqlite3.connect(p) if os.path.exists(p) else None; db.execute('PRAGMA journal_mode=DELETE') if db else None; db.commit() if db else None; db.close() if db else None; print('[OK] 数据库正常')" 2>nul
if errorlevel 1 (
    echo [!] 数据库WAL修复中...
    if exist "data\samsung_ops.db-wal" del /f "data\samsung_ops.db-wal" 2>nul
    if exist "data\samsung_ops.db-shm" del /f "data\samsung_ops.db-shm" 2>nul
    %VENV_PYTHON% -c "import sqlite3, os; p=r'data\samsung_ops.db'; db=sqlite3.connect(p) if os.path.exists(p) else None; db.execute('PRAGMA journal_mode=DELETE') if db else None; db.commit() if db else None; db.close() if db else None; print('[OK] WAL已清理')" 2>nul
)

REM ==================== 启动服务 ====================

echo.
echo [*] 启动服务...
echo [*] 访问地址: http://localhost:9527
echo [*] 管理员账号: 见 .env 文件中的 SAMSUNG_ADMIN_USERNAME / SAMSUNG_ADMIN_PASSWORD
echo [*] 按 Ctrl+C 停止服务
echo.

REM 自动打开浏览器
start http://localhost:9527

REM 启动服务
%VENV_PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 9527 --app-dir .

if errorlevel 1 (
    echo.
    echo [X] 服务启动失败！请检查错误信息
    echo.
    pause
)
