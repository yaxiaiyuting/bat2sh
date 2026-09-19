#!/usr/bin/env bash
# tag 之后的 PKGBUILD 校验和同步（D-1 修复的第 4 步）。
#
# 为什么必须放在 tag 之后：PKGBUILD 的 sha256sums 校验的是
#   https://github.com/<owner>/<repo>/archive/refs/tags/v<X.Y.Z>.tar.gz
# 而该 tarball 的内容由 tag 指向的 commit 决定 —— 也就是说哈希**依赖 tag 自身**，
# 在打 tag 之前无法算出。这是自指约束，不是可以靠流程规避的问题。
#
# 因此 v2.8.1 及之前各版把它和 pkgver 一起推到 tag 之后，导致 tag 内
# **版本号也不自洽**（真正的缺陷）。本脚本只负责哈希这一半，
# 版本号必须由 scripts/release-bump.sh 在 tag 前写好。
#
# 用法: ./scripts/release-sync-pkg.sh 2.9.0
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

VER="${1:-}"
if [[ ! "$VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "用法: $0 <版本号>   例如 $0 2.9.0" >&2
    exit 2
fi

TAG="v$VER"
URL="https://github.com/yaxiaiyuting/bat2sh/archive/refs/tags/$TAG.tar.gz"

echo "==> 确认 tag $TAG 存在"
if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    echo "错误: 本地不存在 tag $TAG，先打 tag 再运行本脚本。" >&2
    exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> 下载 $URL"
if ! curl -fsSL --retry 3 --connect-timeout 20 -o "$TMP/src.tar.gz" "$URL"; then
    echo "错误: 下载失败。若本机需要代理，请先导出 https_proxy 后重试：" >&2
    echo "      export https_proxy=http://127.0.0.1:10808" >&2
    exit 1
fi

NEW_SHA="$(sha256sum "$TMP/src.tar.gz" | cut -d' ' -f1)"
OLD_SHA="$(grep -m1 '^sha256sums=' PKGBUILD | sed "s/.*'\\(.*\\)'.*/\1/")"
echo "    旧 sha256: $OLD_SHA"
echo "    新 sha256: $NEW_SHA"

if [[ "$OLD_SHA" == "$NEW_SHA" ]]; then
    echo "    (无需改动)"
else
    sed -i "0,/^sha256sums=.*/s//sha256sums=('$NEW_SHA')/" PKGBUILD
    echo "    PKGBUILD sha256sums 已更新"
fi

if command -v makepkg >/dev/null 2>&1 && makepkg --printsrcinfo > .SRCINFO.tmp 2>/dev/null; then
    mv .SRCINFO.tmp .SRCINFO
    echo "    .SRCINFO 已重新生成"
else
    rm -f .SRCINFO.tmp
    sed -i "0,/^[[:space:]]*sha256sums[[:space:]]*=.*/s//\tsha256sums = $NEW_SHA/" .SRCINFO
    echo "    警告: makepkg 不可用，.SRCINFO 以 sed 回退更新" >&2
fi

echo "==> 版本一致性复核"
./scripts/release-bump.sh --check

cat <<EOF

==> 后续
  git add PKGBUILD .SRCINFO
  git commit -m "chore(pkg): sync PKGBUILD hashes for $TAG"
  git push origin main
EOF
