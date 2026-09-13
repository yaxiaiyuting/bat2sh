# 简单备份脚本
param(
    [string]$Source = "C:\Data",
    [string]$Destination = "D:\Backup"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Destination)) {
    New-Item -ItemType Directory -Path $Destination | Out-Null
}

$files = Get-ChildItem "$Source\*.txt"
$count = 0
foreach ($file in $files) {
    $target = Join-Path $Destination $file
    Write-Host "备份 $file -> $target"
    Copy-Item -Path $file -Destination $target -Force
    $count = $count + 1
}

if ($count -gt 0) {
    Write-Host "共备份 $count 个文件"
} else {
    Write-Warning "没有可备份的文件"
}

exit 0
