#!/usr/bin/env bash
# 由 bat2sh 自动转换生成，源文件: backup.ps1
# 带有 # TODO 标记的行无法自动转换，请人工检查
set -euo pipefail
# 简单备份脚本
Source="${1:-C:/Data}"
Destination="${2:-D:/Backup}"

set -e

if [[ ! (-e "${Destination:-}") ]]; then
    mkdir -p "${Destination}" > /dev/null
fi

files=("${Source}"/*.txt)
count=0
for file in "${files[@]}"; do
    target="${Destination}/${file}"
    echo "备份 ${file} -> ${target}"
    cp -f "${file}" "${target}"
    count=$(( ${count:-0} + 1 ))
done

if [[ ${count:-} -gt 0 ]]; then
    echo "共备份 ${count} 个文件"
else
    echo "没有可备份的文件" >&2
fi

exit 0
