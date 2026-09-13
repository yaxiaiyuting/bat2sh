#!/usr/bin/env bash
# 由 bat2sh 自动转换生成，源文件: deploy.bat
# 带有 # TODO 标记的行无法自动转换，请人工检查
set -euo pipefail
# 检测到通配符匹配：已启用 nullglob，无匹配时循环体不执行
shopt -s nullglob

label_copy_files() {
    for f in "${SRC}"/*.exe "${SRC}"/*.dll; do
        echo "复制 $(basename "${f}")"
        cp -f "${f}" "${DST}/"
    done
    return
}

label_summary() {
    echo "部署目录内容:"
    ls -1 "${DST}"
    echo "部署完成"
    read -rp "Press Enter to continue..." || true
    return
}
SRC="./build/release"
DST="./deploy"
if [ ! -e "${DST}" ]; then
    mkdir -p "${DST}"
fi
if ! label_copy_files; then
    exit 1
fi
label_summary
exit 0
