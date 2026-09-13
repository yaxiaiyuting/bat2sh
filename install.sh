#!/usr/bin/env bash
# bat2sh 用户级安装脚本（默认安装到 ~/.local，无需 root）
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'EOF'
用法: ./install.sh [--prefix <目录>]

  --prefix <目录>   安装前缀，默认 ~/.local
                    （系统级安装可执行: sudo PREFIX=/usr/local ./install.sh）

安装内容:
  <prefix>/lib/bat2sh/bat2sh        程序模块
  <prefix>/bin/bat2sh               启动器
  <prefix>/share/applications/bat2sh.desktop
  <prefix>/share/icons/hicolor/scalable/apps/bat2sh.svg

依赖: python (>=3.9)、python-pyside6
  Arch/CachyOS: sudo pacman -S python python-pyside6
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix) PREFIX="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 1 ;;
    esac
done

LIBDIR="$PREFIX/lib/bat2sh"
BINDIR="$PREFIX/bin"

echo "==> 检查依赖"
command -v python3 >/dev/null || { echo "缺少 python3"; exit 1; }
if ! python3 -c "import PySide6" 2>/dev/null; then
    echo "警告: 未检测到 PySide6，图形界面将无法启动。"
    echo "      Arch/CachyOS 请执行: sudo pacman -S python-pyside6"
fi

echo "==> 安装模块到 $LIBDIR"
rm -rf "$LIBDIR"
mkdir -p "$LIBDIR"
cp -a "$HERE/src/bat2sh" "$LIBDIR/"

echo "==> 安装启动器到 $BINDIR/bat2sh"
mkdir -p "$BINDIR"
sed "s|/usr/lib/bat2sh|$LIBDIR|g" "$HERE/scripts/bat2sh-launcher" > "$BINDIR/bat2sh"
chmod 755 "$BINDIR/bat2sh"

echo "==> 安装桌面项与图标"
mkdir -p "$PREFIX/share/applications" "$PREFIX/share/icons/hicolor/scalable/apps"
install -m644 "$HERE/bat2sh.desktop" "$PREFIX/share/applications/bat2sh.desktop"
install -m644 "$HERE/src/bat2sh/data/bat2sh.svg" \
    "$PREFIX/share/icons/hicolor/scalable/apps/bat2sh.svg"

echo "==> 完成。"
case ":$PATH:" in
    *":$BINDIR:"*) ;;
    *) echo "提示: 请将 $BINDIR 加入 PATH，例如:"; echo "  fish: fish_add_path $BINDIR" ;;
esac
echo "运行: bat2sh         （图形界面）"
echo "      bat2sh --cli file.bat -o file.sh   （命令行）"
