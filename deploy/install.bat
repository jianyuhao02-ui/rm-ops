@echo off
chcp 65001 >nul
title 三星事业部管理平台 - 一键安装部署
echo.
echo  ========================================
echo    三星事业部管理平台 - 安装部署向导
echo  ========================================
echo.

cd /d "%~dp0.."

REM ==================== Step 1: Python 环境检查 ====================
echo [1/5] 检查 Python 环境...
set PYTHON_EXE=
where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('where python') do set PYTHON_EXE=%%i
    echo [OK] 找到 Python: %PYTHON_EXE%
) else (
    echo [X] 未找到 Python！请先安装 Python 3.10+
    echo     下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM ==================== Step 2: 创建虚拟环境 ====================
echo.
echo [2/5] 创建虚拟环境...
if exist "backend\.venv" (
    echo [!] 虚拟环境已存在，跳过创建
) else (
    %PYTHON_EXE% -m venv backend\.venv
    if errorlevel 1 (
        echo [X] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [OK] 虚拟环境创建成功
)

REM ==================== Step 3: 安装依赖 ====================
echo.
echo [3/5] 安装 Python 依赖...
backend\.venv\Scripts\pip.exe install -r requirements.txt
if errorlevel 1 (
    echo [X] 依赖安装失败，尝试单独安装...
    backend\.venv\Scripts\pip.exe install fastapi "uvicorn[standard]" pyjwt aiosqlite python-multipart APScheduler httpx xlrd openpyxl python-dotenv
)
echo [OK] 依赖安装完成

REM ==================== Step 4: 初始化目录 ====================
echo.
echo [4/5] 初始化目录结构...
if not exist "logs" mkdir logs
if not exist "data" mkdir data
echo [OK] 目录结构就绪

REM ==================== Step 5: 创建桌面快捷方式 ====================
echo.
echo [5/5] 创建桌面快捷方式...
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\三星事业部管理平台.lnk'); $Shortcut.TargetPath = '%~dp0..\launch.bat'; $Shortcut.WorkingDirectory = '%~dp0..'; $Shortcut.IconLocation = '%~dp0..\frontend\icons\icon-192.png'; $Shortcut.Save()" 2>nul
if errorlevel 1 (
    echo [!] 快捷方式创建失败（可手动创建）
) else (
    echo [OK] 桌面快捷方式已创建
)

REM ==================== 完成 ====================
echo.
echo ========================================
echo   安装完成！
echo.
echo   启动方式：
echo   1. 双击桌面上的「三星事业部管理平台」
echo   2. 或双击 launch.bat
echo   3. 访问 http://localhost:9527
echo.
echo   管理员账号: admin / admin123
echo   店长账号: store1~store10 / store123
echo ========================================
echo.
pause
