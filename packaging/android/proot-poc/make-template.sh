#!/usr/bin/env bash
# 生成一份打过补丁的 Flet 构建模板，把 proot 的 loader 作为 lib<abi>/libprootloader.so
# 塞进 APK 的 jniLibs。
#
# 背景：Android 10+（targetSdk>=29）禁止 execve() 应用私有数据目录里的文件
# （SELinux app_data_file:file execute_no_trans 被拒），但允许 mmap(PROT_EXEC)。
# proot 从不 execve() guest 程序 —— 它 execve() 一个 "loader"，由 loader 去 mmap
# guest ELF —— 所以只要把 loader 放进可执行的 nativeLibraryDir（apk_data_file），
# proot 就能跑起来。本脚本就是把 loader 送进 APK 的 lib/<abi>/ 的那一步。
#
# 用法：  ./make-template.sh [输出目录]      默认 ./build/template
set -eo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$1"
[ -n "$OUT" ] || OUT="$HERE/build/template"
ASSETS="$HERE/src/assets"

FLET_VERSION="$(python3 -c 'import flet,sys; print(flet.version.flet_version)' 2>/dev/null || echo 1.0.0)"
CACHE="$HOME/.flet/cache/build-template/v$FLET_VERSION/flet-build-template.zip"
URL="https://github.com/flet-dev/flet/releases/download/v$FLET_VERSION/flet-build-template.zip"

if [ ! -s "$CACHE" ]; then
  echo "下载 Flet 构建模板 v$FLET_VERSION ..."
  mkdir -p "$(dirname "$CACHE")"
  curl -sSL --fail -o "$CACHE.part" "$URL"
  mv "$CACHE.part" "$CACHE"
fi

# Flet 用 cookiecutter 渲染模板；cookiecutter.json 必须在模板根，而官方 zip 里
# 它在 build/ 下一层。zip 走 cookiecutter 自己的解包逻辑能自动下钻，普通目录不行，
# 所以这里直接把 build/ 的内容摊平为模板根。
rm -rf "$OUT"
mkdir -p "$OUT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
unzip -q "$CACHE" -d "$TMP"
cp -a "$TMP/build/." "$OUT/"

JNI="$OUT/{{cookiecutter.out_dir}}/android/app/src/main/jniLibs"
for ABI in aarch64 x86_64; do
  SRC="$ASSETS/loader-$ABI"
  [ -f "$SRC" ] || { echo "缺少 $SRC —— 先跑 ./fetch-assets.sh" >&2; exit 1; }
  case "$ABI" in
    aarch64) DIR="arm64-v8a" ;;
    x86_64)  DIR="x86_64" ;;
  esac
  mkdir -p "$JNI/$DIR"
  cp "$SRC" "$JNI/$DIR/libprootloader.so"
  chmod 644 "$JNI/$DIR/libprootloader.so"
done

python3 - "$OUT" <<'PYEOF'
import sys
from pathlib import Path

root = Path(sys.argv[1])
gradle = root / "{{cookiecutter.out_dir}}" / "android" / "app" / "build.gradle.kts"
s = gradle.read_text(encoding="utf-8")
anchor = '            pickFirsts += listOf("**/libc++_shared.so")\n'
if anchor not in s:
    sys.exit("模板结构变了：找不到 pickFirsts 锚点，请检查 flet-build-template")
if "libprootloader" not in s:
    s = s.replace(anchor, anchor + '''
            // bat2sh PoC: libprootloader.so 是 proot 自带的静态 loader（ET_EXEC，
            // 不是 DSO），改名成 lib*.so 只是为了让它被 AGP 收进 lib/<abi>/，
            // 再由 --android-legacy-packaging 解压到 nativeLibraryDir。
            // 必须原样保留，不能被 NDK strip 任务动过。
            keepDebugSymbols += listOf("**/libprootloader.so")
''', 1)
    gradle.write_text(s, encoding="utf-8")
PYEOF

echo "模板就绪：$OUT"
echo "  jniLibs:"
find "$JNI" -type f -printf '    %p (%s bytes)\n'
