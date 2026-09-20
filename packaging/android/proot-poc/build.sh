#!/usr/bin/env bash
# 构建 Phase 1 proot 探针 APK。
#
#   ./build.sh [arm64-v8a|x86_64]        默认 arm64-v8a
#
# 依赖（沿用上一 session 的 Flet PoC 环境）：
#   source /tmp/flet-termux-poc/env.sh    # JAVA_HOME / ANDROID_HOME / flutter / 代理
#   FLET=<flet 可执行文件>                 # Flet 1.0.0
set -eo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ARCH="$1"
[ -n "$ARCH" ] || ARCH="arm64-v8a"
FLET="$FLET_BIN"
[ -n "$FLET" ] || FLET="$(command -v flet)"

case "$ARCH" in
  arm64-v8a) ABI=aarch64 ;;
  x86_64)    ABI=x86_64 ;;
  *) echo "用法: $0 [arm64-v8a|x86_64]" >&2; exit 2 ;;
esac

[ -f "$HERE/src/assets/bootstrap-$ABI.zip" ] || { echo "先跑 ./fetch-assets.sh" >&2; exit 1; }
[ -f "$HERE/src/assets/loader-$ABI" ]        || { echo "先跑 ./fetch-assets.sh" >&2; exit 1; }

TEMPLATE="$HERE/build/template"
"$HERE/make-template.sh" "$TEMPLATE"

cd "$HERE"
"$FLET" build apk \
  --arch "$ARCH" \
  --android-legacy-packaging \
  --template "$TEMPLATE" \
  --yes --no-rich-output

echo
echo "APK:"
ls -la "$HERE/build/apk/"
