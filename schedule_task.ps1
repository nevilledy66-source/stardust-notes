# 星尘笔记 — Windows 每日定时任务注册脚本
# 功能：注册 Windows 任务计划，每晚 20:00 自动运行文章生成引擎
# 用法：以管理员身份运行 PowerShell，执行此脚本
#   powershell -ExecutionPolicy Bypass -File schedule_task.ps1

param(
    [string]$BlogPath = "d:\AI MASTER\blog",
    [string]$PythonPath = "python",
    [switch]$Unregister
)

$TaskName = "StardustNotes-DailyUpdate"
$ScriptPath = Join-Path $BlogPath "generator\fetch_news.py"

if ($Unregister) {
    Write-Host "正在删除定时任务: $TaskName ..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "任务已删除。"
    exit 0
}

# 检查文件存在
if (-not (Test-Path $ScriptPath)) {
    Write-Error "找不到生成脚本: $ScriptPath"
    Write-Error "请确保 BlogPath 参数指向正确的博客目录。"
    Write-Error "用法: .\schedule_task.ps1 -BlogPath 'D:\你的博客路径'"
    exit 1
}

# 检查 ANTHROPIC_API_KEY 环境变量
if (-not $env:ANTHROPIC_API_KEY) {
    Write-Warning "⚠ ANTHROPIC_API_KEY 环境变量未设置！"
    Write-Warning "  请先设置环境变量，或将此脚本中的 $env:ANTHROPIC_API_KEY 替换为你的 API Key。"
    Write-Warning "  设置方法: setx ANTHROPIC_API_KEY ""your-key-here"""
}

# 创建任务操作
$Action = New-ScheduledTaskAction -Execute $PythonPath `
    -Argument "`"$ScriptPath`"" `
    -WorkingDirectory $BlogPath

# 创建触发器：每天 20:00
$Trigger = New-ScheduledTaskTrigger -Daily -At "20:00"

# 任务设置
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

# 使用当前用户注册任务
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

try {
    # 先删除旧任务（如果存在）
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    # 注册新任务
    Register-ScheduledTask -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "星尘笔记每日文章生成 — 每晚20:00抓取并交叉验证AI新闻，生成中文分析文章" `
        -Force

    Write-Host ""
    Write-Host "✅ 定时任务已注册成功！" -ForegroundColor Green
    Write-Host ""
    Write-Host "任务详情:" -ForegroundColor Cyan
    Write-Host "  名称:     $TaskName"
    Write-Host "  执行时间: 每晚 20:00"
    Write-Host "  执行脚本: $ScriptPath"
    Write-Host "  工作目录: $BlogPath"
    Write-Host ""
    Write-Host "管理命令:" -ForegroundColor Cyan
    Write-Host "  查看任务:   taskschd.msc (搜索 '$TaskName')"
    Write-Host "  手动运行:   Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  删除任务:   .\schedule_task.ps1 -Unregister"
    Write-Host ""
    Write-Host "‼ 重要提醒:" -ForegroundColor Yellow
    Write-Host "  1. 确保 ANTHROPIC_API_KEY 设置为系统环境变量"
    Write-Host "  2. 确保 Python 在 PATH 中 (当前: $PythonPath)"
    Write-Host "  3. 安装依赖: pip install -r generator/requirements.txt"
    Write-Host ""

} catch {
    Write-Error "注册任务失败: $_"
    Write-Error "请尝试以管理员身份运行 PowerShell 后重试。"
    exit 1
}
