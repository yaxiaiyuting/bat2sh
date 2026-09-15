#!/usr/bin/env bash
# 由 bat2sh 自动转换生成，源文件: backup.ps1
# 带有 # TODO 标记的行无法自动转换，请人工检查
set -euo pipefail
# 检测到通配符匹配：已启用 nullglob，无匹配时数组为空、循环体不执行
shopt -s nullglob

# Join-Path 辅助函数：子路径为绝对路径时重置（对齐 PowerShell/.NET Path.Combine 语义）
__bat2sh_join_path() {
    local __result="" __part
    for __part in "$@"; do
        if [[ "${__part}" == /* || "${__part}" == [A-Za-z]:/* || "${__part}" == [A-Za-z]:\\* ]]; then
            __result="${__part}"
        elif [[ -z "${__result}" || "${__result}" == */ ]]; then
            __result="${__result}${__part}"
        else
            __result="${__result}/${__part}"
        fi
    done
    printf '%s' "${__result}"
}
# 简单备份脚本
# 注意: Windows 路径，请改为 Linux 路径，例如 ${HOME}/data
Source="${1:-C:/Data}"
# 注意: Windows 路径，请改为 Linux 路径，例如 ${HOME}/data
Destination="${2:-D:/Backup}"

# $ErrorActionPreference = "Stop"（脚本头已启用严格模式）

if [[ ! (-e "${Destination:-}") ]]; then
    mkdir -p "${Destination}" > /dev/null
fi

files=("${Source}"/*.txt)
count=0
for file in "${files[@]}"; do
    target=$(__bat2sh_join_path "${Destination}" "${file}")
    echo "备份 ${file} -> ${target:-}"
    cp -f "${file}" "${target:-}"
    count=$(( ${count:-0} + 1 ))
done

if [[ ${count:-} -gt 0 ]]; then
    echo "共备份 ${count} 个文件"
else
    echo "没有可备份的文件" >&2
fi

exit 0
