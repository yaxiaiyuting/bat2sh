#!/usr/bin/env bash
# 构建 bat2sh Android APK。
#
#   ./build.sh [arm64-v8a|x86_64]        默认 arm64-v8a
#
# 依赖（沿用上一 session 的 Flet PoC 环境）：
#   source /tmp/flet-termux-poc/env.sh     # JAVA_HOME / ANDROID_HOME / flutter / 代理
#   FLET_BIN=<flet 可执行文件>              # Flet 1.0.0，默认从 PATH 找 flet
#
# 关键配置：pyproject.toml 里 [tool.flet.android] target_sdk_version = 28
#   —— Phase A 实测出来的硬要求，降到 28 才能拿回完整 shell 能力。
set -eo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ARCH="$1"
[ -n "$ARCH" ] || ARCH="arm64-v8a"
FLET="$FLET_BIN"
[ -n "$FLET" ] || FLET="$(command -v flet)"

case "$ARCH" in
  arm64-v8a) ABI=aarch64; OTHER_ABI=x86_64 ;;
  x86_64)    ABI=x86_64;  OTHER_ABI=aarch64 ;;
  *) echo "用法: $0 [arm64-v8a|x86_64]" >&2; exit 2 ;;
esac

# 1) 同步 core（core 零改动：事实来源始终是 python/bat2sh/）
"$HERE/sync-core.sh"

# 2) 资产自检
BOOT="$HERE/src/assets/bootstrap-$ABI.zip"
if [ ! -s "$BOOT" ]; then
  echo "缺少 $BOOT" >&2
  echo "取法见 docs/android-poc-v2-report.md 的复现命令" >&2
  exit 1
fi

# 3) 构建
# 只带本 ABI 的 bootstrap：另一份 32 MB，打进去纯属浪费下载量。
# （--exclude 的路径相对于 [tool.flet.app].path，也就是 src/）
cd "$HERE"
"$FLET" build apk --arch "$ARCH" \
  --exclude "assets/bootstrap-$OTHER_ABI.zip" \
  --yes --no-rich-output

echo
echo "APK:"
ls -la "$HERE/build/apk/"
