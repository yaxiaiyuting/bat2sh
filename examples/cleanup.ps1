# 清理临时日志
function Remove-OldLogs {
    param(
        [string]$Path = "/tmp/logs",
        [int]$Keep = 5
    )
    if (-not (Test-Path $Path)) {
        Write-Warning "目录不存在: $Path"
        return
    }
    $logs = Get-ChildItem "$Path\*.log"
    foreach ($log in $logs) {
        Write-Host "删除 $log"
        Remove-Item -Path $log -Force
    }
}

$ErrorActionPreference = "Stop"
Remove-OldLogs -Path "$env:TEMP\logs" -Keep 3
Clear-Host
Write-Host "清理完成"
