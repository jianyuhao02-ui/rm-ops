@echo off
chcp 65001 >nul
title 三星事业部管理平台 - 一键部署

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║    三星事业部运营管理平台 v2.1 - 部署向导    ║
echo  ╚══════════════════════════════════════════════╝
echo.

REM ==================== 检查管理员权限 ====================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 建议以管理员身份运行以注册 Windows 服务
    echo.
)

REM ==================== 步骤 1: 检查 Python ====================
echo [1/5] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo       已找到 Python %%v

REM ==================== 步骤 2: 创建虚拟环境 ====================
echo.
echo [2/5] 配置虚拟环境...
if not exist "backend\.venv" (
    echo       正在创建虚拟环境...
    python -m venv backend\.venv
    echo       虚拟环境创建完成
) else (
    echo       虚拟环境已存在，跳过
)

REM ==================== 步骤 3: 安装依赖 ====================
echo.
echo [3/5] 安装 Python 依赖...
call backend\.venv\Scripts\activate.bat
pip install -r requirements.txt -q
echo       依赖安装完成

REM ==================== 步骤 4: 配置环境变量 ====================
echo.
echo [4/5] 配置环境变量...
if not exist ".env" (
    echo       创建默认 .env 配置文件...
    copy .env.example .env >nul
    echo       已创建 .env，请根据需要修改配置
) else (
    echo       .env 文件已存在，跳过
)

REM ==================== 步骤 5: 创建快捷方式 ====================
echo.
echo [5/5] 创建桌面快捷方式...
set DESKTOP=%USERPROFILE%\Desktop
set SHORTCUT=%DESKTOP%\三星事业部管理平台.bat

echo @echo off > "%SHORTCUT%"
echo title 三星事业部管理平台 >> "%SHORTCUT%"
echo cd /d "%~dp0" >> "%SHORTCUT%"
echo echo 正在启动三星事业部管理平台... >> "%SHORTCUT%"
echo echo 访问地址: http://localhost:9527 >> "%SHORTCUT%"
echo echo 按 Ctrl+C 停止服务 >> "%SHORTCUT%"
echo echo. >> "%SHORTCUT%"
echo call backend\.venv\Scripts\activate.bat >> "%SHORTCUT%"
echo python main.py >> "%SHORTCUT%"
echo pause >> "%SHORTCUT%"

echo       桌面快捷方式已创建

REM ==================== 完成 ====================
echo.
echo ╔══════════════════════════════════════════════╗
echo ║           部署完成！                         ║
echo ╠══════════════════════════════════════════════╣
echo ║  访问地址: http://localhost:9527             ║
echo ║  管理员账号: admin                           ║
echo ║  管理员密码: (查看 .env 文件)                ║
echo ║                                            ║
echo ║  启动方式:                                  ║
echo ║  1. 双击桌面快捷方式                        ║
echo ║  2. 运行 launch.bat                         ║
echo ╚══════════════════════════════════════════════╝
echo.

pause
