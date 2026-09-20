#!/usr/bin/env bash
# 把 python/bat2sh/{__init__.py,core,mappings,data} 同步到 src/bat2sh/。
#
# 为什么是「同步」而不是「提交一份拷贝」：
#   * 纪律要求 core 零改动 —— 单一事实来源留在 python/bat2sh/，避免两份代码漂移；
#   * src/bat2sh/ 是**生成物**，已在 .gitignore 中排除。
# GUI 相关（gui/ / cli.py / __main__.py）不参与同步：前者依赖 PySide6，
# 后两者是桌面 CLI 入口，Android 用不到。
#
# 用法：  ./sync-core.sh
set -eo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
SRC="$REPO/python/bat2sh"
DST="$HERE/src/bat2sh"

[ -d "$SRC" ] || { echo "找不到 $SRC" >&2; exit 1; }

rm -rf "$DST"
mkdir -p "$DST"
cp "$SRC/__init__.py" "$DST/"
for sub in core mappings data; do
  [ -d "$SRC/$sub" ] || continue
  cp -a "$SRC/$sub" "$DST/$sub"
  find "$DST/$sub" -name __pycache__ -type d -prune -exec rm -rf {} +
  find "$DST/$sub" -name '*.pyc' -delete
done

echo "已同步 -> $DST"
find "$DST" -type f | wc -l | xargs echo "  文件数:"
du -sh "$DST" | cut -f1 | xargs echo "  体积:"
