@echo off
chcp 437 >nul
title RM Ops Platform
echo.
echo  ========================================
echo    RM Ops - Fix and Start
echo  ========================================
echo.

cd /d "%~dp0"

echo [1/3] Fix database WAL mode...
backend\.venv\Scripts\python.exe -c "import sqlite3,os;db=sqlite3.connect(r'data\rm_ops.db');db.execute('PRAGMA wal_checkpoint(TRUNCATE)');db.execute('PRAGMA journal_mode=DELETE');db.commit();db.close();print('[OK] WAL fix applied')"
if errorlevel 1 (
    echo [!] Standard fix failed, trying force fix...
    if exist "data\rm_ops.db-wal" del /f "data\rm_ops.db-wal" 2>nul
    if exist "data\rm_ops.db-shm" del /f "data\rm_ops.db-shm" 2>nul
    backend\.venv\Scripts\python.exe -c "import sqlite3;db=sqlite3.connect(r'data\rm_ops.db');db.execute('PRAGMA journal_mode=DELETE');db.commit();db.close();print('[OK] Force fix OK')" 2>nul
    if errorlevel 1 (
        echo [X] Fix failed, rebuild database...
        backend\.venv\Scripts\python.exe -c "import os;[os.remove(p) for p in [r'data\rm_ops.db',r'data\rm_ops.db-wal',r'data\rm_ops.db-shm'] if os.path.exists(p)];print('[OK] Old DB removed, restarting initialization')"
    )
)

echo.
echo [2/3] Check dependencies...
if not exist "backend\.venv\Scripts\python.exe" (
    echo [!] Creating venv...
    python -m venv backend\.venv
    backend\.venv\Scripts\pip.exe install fastapi "uvicorn[standard]" pyjwt aiosqlite python-multipart APScheduler httpx xlrd openpyxl
)

if not exist "logs" mkdir logs
if not exist "data" mkdir data

echo.
echo [3/3] Starting server...
echo.
echo   URL:  http://localhost:9527
echo   User: admin / admin123
echo   Press Ctrl+C to stop
echo.

start http://localhost:9527

backend\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 9527 --app-dir .

if errorlevel 1 (
    echo.
    echo [X] Server start FAILED!
    echo     Take a screenshot and send to me
    echo.
    pause
)
