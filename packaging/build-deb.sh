#!/usr/bin/env bash
# 构建 Debian / Ubuntu 安装包（.deb）
#
# 设计要点：
# - 本项目是纯 Python，无编译产物 -> Architecture: all（同一个包在 amd64/arm64 通用）。
# - PySide6 只被 GUI 使用，转换核心仅标准库（CLI 无 PySide6 也能运行），
#   因此放 **Recommends** 而非 Depends —— 避免在未打包 PySide6 的发行版
#   （如 Debian 12）上直接无法安装。
# - 依赖 python3 >= 3.12，与 pyproject.toml 的 requires-python 一致。
#
# 用法: ./packaging/build-deb.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

VER="$(grep -m1 '^version' pyproject.toml | sed 's/.*"\(.*\)".*/\1/')"
PKG=bat2sh
REL=1
OUT="$ROOT/dist"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "==> 构建 $PKG $VER-$REL (.deb, Architecture: all)"

install -d "$STAGE/DEBIAN" \
           "$STAGE/usr/bin" \
           "$STAGE/usr/lib/$PKG" \
           "$STAGE/usr/share/applications" \
           "$STAGE/usr/share/mime/packages" \
           "$STAGE/usr/share/icons/hicolor/scalable/apps" \
           "$STAGE/usr/share/doc/$PKG/examples"

cp -a python/bat2sh "$STAGE/usr/lib/$PKG/"
find "$STAGE/usr/lib/$PKG" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/usr/lib/$PKG" -name '*.pyc' -delete 2>/dev/null || true

install -Dm755 scripts/bat2sh-launcher        "$STAGE/usr/bin/$PKG"
install -Dm644 bat2sh.desktop                 "$STAGE/usr/share/applications/$PKG.desktop"
install -Dm644 data/mime/bat2sh.xml           "$STAGE/usr/share/mime/packages/$PKG.xml"
install -Dm644 python/bat2sh/data/bat2sh.svg  "$STAGE/usr/share/icons/hicolor/scalable/apps/$PKG.svg"
# Debian policy：copyright 文件必须**同时**含版权声明与分发许可证。
#   NOTICE  —— 版权人（Copyright (C) 2026 yaxiaiyuting）+ FSF 推荐 notice 块
#   LICENSE —— AGPL-3.0 官方正文（**不含**版权人：为让 GitHub SPDX matcher 能识别，
#              该文件必须只含标准许可证文本，见 docs/discoverability-report.md §4）
# 故此处两者拼接，缺一不可。
{
  cat NOTICE
  echo ""
  echo "---"
  echo ""
  cat LICENSE
} > "$STAGE/usr/share/doc/$PKG/copyright"
chmod 644 "$STAGE/usr/share/doc/$PKG/copyright"
install -Dm644 README.md                      "$STAGE/usr/share/doc/$PKG/README.md"
cp -a examples/. "$STAGE/usr/share/doc/$PKG/examples/"

SIZE="$(du -sk "$STAGE/usr" | cut -f1)"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VER-$REL
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.12)
Recommends: python3-pyside6.qtwidgets | python3-pyside6
Installed-Size: $SIZE
Maintainer: yaxiaiyuting <jiangtianyou189@qq.com>
Homepage: https://github.com/yaxiaiyuting/bat2sh
Description: Windows 批处理/PowerShell 转 Bash 的转换器
 bat2sh 把 Windows 批处理（.bat/.cmd）与 PowerShell（.ps1）脚本静态翻译为
 Bash 脚本，提供 PySide6 图形界面与命令行两种用法。
 .
 转换核心仅依赖 Python 标准库，CLI 无需 PySide6 即可运行；
 图形界面需要 python3-pyside6（见 Recommends）。
 .
 产物定位为「高级草稿」：无法自动转换的语句以 # TODO 显式标记，
 绝不静默产出可疑脚本。
EOF

for hook in postinst postrm; do
    cat > "$STAGE/DEBIAN/$hook" <<'EOF'
#!/bin/sh
set -e
if [ -x /usr/bin/update-mime-database ]; then
    update-mime-database /usr/share/mime || true
fi
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q /usr/share/applications || true
fi
EOF
    chmod 755 "$STAGE/DEBIAN/$hook"
done

( cd "$STAGE" && find usr -type f -exec md5sum {} + > DEBIAN/md5sums )

mkdir -p "$OUT"
DEB="$OUT/${PKG}_${VER}-${REL}_all.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$DEB" >/dev/null

echo "==> 产物: $DEB"
ls -lh "$DEB" | awk '{print "    大小:", $5}'
echo
echo "==> 控制信息"
dpkg-deb --info "$DEB" | sed -n '1,20p'
