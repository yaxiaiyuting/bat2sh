#!/usr/bin/env bash
# 由 bat2sh 自动转换生成，源文件: hello.bat
# 带有 # TODO 标记的行无法自动转换，请人工检查
set -euo pipefail

# 简单的问候脚本
NAME="World"
GREETING="Hello"
echo "${GREETING}, ${NAME}!"
echo "当前目录: $(pwd)"
if [ -e "config.ini" ]; then
    echo "找到配置文件"
else
    echo "未找到 config.ini，使用默认配置"
fi
read -rp "Press Enter to continue..." || true
exit 0
