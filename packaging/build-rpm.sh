#!/usr/bin/env bash
# 构建 RPM 安装包（.rpm）
#
# 说明：
# - BuildArch: noarch（纯 Python，无编译产物）。
# - PySide6 只被 GUI 使用，转换核心仅标准库 -> Requires 仅 python3 >= 3.12，
#   PySide6 放弱依赖 Recommends（rpm >= 4.12 支持）。
# - 安装路径用 %{_prefix}/lib/bat2sh，与 scripts/bat2sh-launcher 里硬编码的
#   /usr/lib/bat2sh 一致（因此不用 %{_libdir}，它在 x86_64 上是 /usr/lib64）。
#
# 用法: ./packaging/build-rpm.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

VER="$(grep -m1 '^version' pyproject.toml | sed 's/.*"\(.*\)".*/\1/')"
OUT="$ROOT/dist"
TOP="${RPM_TOPDIR:-$HOME/rpmbuild}"

command -v rpmbuild >/dev/null 2>&1 || {
    echo "错误: 未找到 rpmbuild。Arch 上安装: sudo pacman -S rpm-tools" >&2
    exit 1
}

echo "==> 构建 bat2sh $VER-1 (.rpm, noarch)"
install -d "$TOP"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

# 使用**私有 rpm 数据库**：Arch/CachyOS 上 /var/lib/rpm 未初始化，
# rpmbuild 会持续报「无法从 /var/lib/rpm 打开软件包数据库 / 无法创建事务锁定」。
# rpm-tools 的安装提示也明确要求不要在 Arch 上使用系统级 rpm 库。
RPMDB="$TOP/rpmdb"
install -d "$RPMDB"
if [ ! -f "$RPMDB/rpmdb.sqlite" ] && [ ! -f "$RPMDB/Packages" ]; then
    rpm --dbpath "$RPMDB" --initdb >/dev/null 2>&1 || true
fi

rpmbuild -bb "$HERE/bat2sh.spec" \
    --define "ver $VER" \
    --define "repo $ROOT" \
    --define "_topdir $TOP" \
    --define "_dbpath $RPMDB" \
    --define "_build_id_links none" \
    2>&1 | sed 's/^/    /'

RPM="$(find "$TOP/RPMS" -name "bat2sh-$VER-*.rpm" | head -1)"
mkdir -p "$OUT"
cp "$RPM" "$OUT/"
echo
echo "==> 产物: $OUT/$(basename "$RPM")"
ls -lh "$OUT/$(basename "$RPM")" | awk '{print "    大小:", $5}'
echo
echo "==> 包信息"
rpm -qip "$OUT/$(basename "$RPM")" 2>/dev/null | head -14
