#!/usr/bin/env bash
# 由 bat2sh 自动转换生成，源文件: cleanup.ps1
# 带有 # TODO 标记的行无法自动转换，请人工检查
set -euo pipefail
# 清理临时日志
Remove_OldLogs() {
    local Path="${1:-/tmp/logs}"
    local Keep="${2:-5}"
    if [[ ! (-e "${Path:-}") ]]; then
        echo "目录不存在: ${Path}" >&2
        return 0
    fi
    logs=("${Path}"/*.log)
    for log in "${logs[@]}"; do
        echo "删除 ${log}"
        rm -f "${log}"
    done
}

set -e
Remove_OldLogs -Path "${TEMP}/logs" -Keep 3
clear
echo "清理完成"
