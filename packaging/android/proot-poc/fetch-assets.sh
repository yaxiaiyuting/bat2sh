#!/usr/bin/env bash
# 下载 Phase 1 proot PoC 所需的全部二进制资产到 src/assets/。
#
# 这些资产都很大（Termux bootstrap 每个 ABI ~33 MB；alpine rootfs 是 *.tar.gz），
# 且都被仓库 .gitignore 排除，因此不入库，改由本脚本按需拉取。
#
# 用法：  ./fetch-assets.sh [aarch64|x86_64|both]     默认 both
set -eo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ASSETS="$HERE/src/assets"

TARGETS="$1"
[ -n "$TARGETS" ] || TARGETS="aarch64 x86_64"
case "$TARGETS" in
  aarch64|x86_64|"aarch64 x86_64") ;;
  *) echo "用法: $0 [aarch64|x86_64|both]" >&2; exit 2 ;;
esac

# Termux 官方 bootstrap（tag / sha256 见 docs/flet-termux-poc-report.md）
TERMUX_TAG='bootstrap-2026.09.20-r1%2Bapt.android-7'
TERMUX_BASE="https://github.com/termux/termux-packages/releases/download/$TERMUX_TAG"
# Termux 软件仓库（proot 及其依赖 libtalloc / libandroid-shmem），NDK 构建、PT_INTERP=/system/bin/linker64
TERMUX_POOL="https://packages.termux.dev/apt/termux-main/pool/main"
PROOT_VER=5.1.107.92
TALLOC_VER=2.4.3
SHMEM_VER=0.7
# Alpine minirootfs（proot 的 guest rootfs）
ALPINE_VER=3.20.3
ALPINE_BASE="https://dl-cdn.alpinelinux.org/alpine/v3.20/releases"

mkdir -p "$ASSETS"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fetch() { # fetch <url> <dest>
  if [ -s "$2" ]; then echo "  = $(basename "$2") (已存在)"; return; fi
  echo "  + $(basename "$2")"
  curl -sSL --fail --retry 3 --max-time 600 -o "$2.part" "$1"
  mv "$2.part" "$2"
}

for ABI in $TARGETS; do
  echo "== $ABI =="
  fetch "$TERMUX_BASE/bootstrap-$ABI.zip" "$ASSETS/bootstrap-$ABI.zip"
  fetch "$ALPINE_BASE/$ABI/alpine-minirootfs-$ALPINE_VER-$ABI.tar.gz" "$ASSETS/alpine-$ABI.tar.gz"

  fetch "$TERMUX_POOL/p/proot/proot_$PROOT_VER"_"$ABI.deb"                         "$WORK/proot.deb"
  fetch "$TERMUX_POOL/libt/libtalloc/libtalloc_$TALLOC_VER"_"$ABI.deb"             "$WORK/talloc.deb"
  fetch "$TERMUX_POOL/liba/libandroid-shmem/libandroid-shmem_$SHMEM_VER"_"$ABI.deb" "$WORK/shmem.deb"

  rm -rf "$WORK/x"
  dpkg-deb -x "$WORK/proot.deb"  "$WORK/x"
  dpkg-deb -x "$WORK/talloc.deb" "$WORK/x"
  dpkg-deb -x "$WORK/shmem.deb"  "$WORK/x"
  U="$WORK/x/data/data/com.termux/files/usr"

  cp "$U/bin/proot"               "$ASSETS/proot-$ABI"
  cp "$U/libexec/proot/loader"    "$ASSETS/loader-$ABI"
  cp "$U/lib/libtalloc.so.2.4.3"  "$ASSETS/libtalloc.so.2-$ABI"
  cp "$U/lib/libandroid-shmem.so" "$ASSETS/libandroid-shmem.so-$ABI"
  chmod 644 "$ASSETS"/*
  rm -f "$WORK"/*.deb
done

echo
echo "资产就绪："
ls -la "$ASSETS"
echo
echo "aarch64 bootstrap sha256（应与 docs/flet-termux-poc-report.md 记录一致）："
[ -f "$ASSETS/bootstrap-aarch64.zip" ] && sha256sum "$ASSETS/bootstrap-aarch64.zip" || true
