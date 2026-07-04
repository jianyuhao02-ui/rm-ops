# 三星事业部管理平台 - Windows 服务注册脚本
# 以管理员身份运行此脚本可将应用注册为 Windows 服务（开机自启）
# 运行方式: 右键 → 以管理员身份运行 PowerShell → 执行此脚本

param(
    [string]$Action = "install"
)

$ServiceName = "SamsungOpsPlatform"
$DisplayName = "三星事业部管理平台"
$Description = "贵州沣范通讯设备有限公司 - 三星事业部运营管理平台"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$PythonExe = Join-Path $ProjectDir "backend\.venv\Scripts\python.exe"
$MainScript = Join-Path $ProjectDir "main.py"

function Install-Service {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  安装三星事业部管理平台为 Windows 服务" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    # 检查管理员权限
    if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
        Write-Host "[X] 请以管理员身份运行此脚本！" -ForegroundColor Red
        Write-Host "    右键 PowerShell → 以管理员身份运行" -ForegroundColor Yellow
        return
    }

    # 检查 Python 环境
    if (-not (Test-Path $PythonExe)) {
        Write-Host "[X] 未找到虚拟环境，请先运行 install.bat" -ForegroundColor Red
        return
    }

    # 检查是否已安装
    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "[!] 服务已存在，正在更新..." -ForegroundColor Yellow
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        sc.exe delete $ServiceName
        Start-Sleep -Seconds 2
    }

    # 创建服务包装脚本
    $WrapperScript = @"
# 三星管理平台服务包装器
Set-Location '$ProjectDir'
& '$PythonExe' -m uvicorn main:app --host 0.0.0.0 --port 9527 --app-dir '$ProjectDir'
"@
    $WrapperPath = Join-Path $ScriptDir "service_wrapper.ps1"
    $WrapperScript | Out-File -FilePath $WrapperPath -Encoding UTF8

    # 使用 NSSM 或 sc 创建服务
    # 方法1: 使用 PowerShell 计划任务实现开机自启
    $TaskName = "SamsungOpsPlatform_AutoStart"
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    $Action = New-ScheduledTaskAction -Execute $PythonExe `
        -Argument "-m uvicorn main:app --host 0.0.0.0 --port 9527 --app-dir `"$ProjectDir`""

    $Trigger = New-ScheduledTaskTrigger -AtStartup

    $Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1)

    Register-ScheduledTask -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $Settings `
        -Description $Description `
        -Force

    # 立即启动
    Start-ScheduledTask -TaskName $TaskName

    Write-Host ""
    Write-Host "[OK] 服务安装成功！" -ForegroundColor Green
    Write-Host "    - 任务名称: $TaskName"
    Write-Host "    - 开机自启: 已启用"
    Write-Host "    - 访问地址: http://localhost:9527"
    Write-Host ""
    Write-Host "管理命令:" -ForegroundColor Yellow
    Write-Host "  启动: Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  停止: Stop-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  卸载: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
}

function Uninstall-Service {
    Write-Host "卸载三星事业部管理平台服务..." -ForegroundColor Yellow

    $TaskName = "SamsungOpsPlatform_AutoStart"
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[OK] 服务已卸载" -ForegroundColor Green
    } else {
        Write-Host "[!] 未找到已安装的服务" -ForegroundColor Yellow
    }
}

# 执行
switch ($Action) {
    "install" { Install-Service }
    "uninstall" { Uninstall-Service }
    "status" {
        $task = Get-ScheduledTask -TaskName "SamsungOpsPlatform_AutoStart" -ErrorAction SilentlyContinue
        if ($task) {
            Write-Host "服务状态: $($task.State)" -ForegroundColor Green
        } else {
            Write-Host "服务未安装" -ForegroundColor Yellow
        }
    }
    default { Write-Host "用法: .\run_as_service.ps1 [install|uninstall|status]" -ForegroundColor Yellow }
}
