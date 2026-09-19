#!/usr/bin/env bash
# 版本号统一 bump（D-1 修复）——**必须在打 tag 之前运行**，并随 bump 提交一起入库。
#
# 背景（D-1 缺陷）：v2.1.0 至 v2.8.1 连续 9 个 tag 内，PKGBUILD 的 pkgver 都停留在
# **上一版**（例如 tag v2.8.1 的 tarball 里 pkgver=2.8.0），而同一棵树的
# python/bat2sh/__init__.py 已是 2.8.1。根因是发布顺序为
#   tag -> 下载 tarball -> 算 sha256 -> commit "chore(pkg): sync PKGBUILD hashes"
# 版本同步提交永远落在 tag 之后，于是 tag 内容永远不自洽。
# 任何从 Release 源码包执行 makepkg -si 的用户都会构建出上一个版本。
#
# 修复策略：把**版本号**（pkgver / .SRCINFO pkgver）提前到 tag 之前，
# 与 pyproject.toml、__init__.py 在同一次提交内完成；**sha256** 因为自指
# （哈希依赖 tag 指向的 commit）无法在 tag 前算出，仍留到 tag 之后，
# 由 scripts/release-sync-pkg.sh 显式同步。
#
# 用法:
#   ./scripts/release-bump.sh 2.9.0        # 写入版本号（不提交，由你 review 后提交）
#   ./scripts/release-bump.sh --check      # 只校验四处版本是否一致（preflight 亦调用）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

PYPROJECT="pyproject.toml"
INIT="python/bat2sh/__init__.py"
PKGBUILD="PKGBUILD"
SRCINFO=".SRCINFO"

read_pyproject() { grep -m1 '^version[[:space:]]*=' "$PYPROJECT" | sed 's/.*"\(.*\)".*/\1/'; }
read_init()      { grep -m1 '__version__' "$INIT" | sed 's/.*"\(.*\)".*/\1/'; }
read_pkgbuild()  { grep -m1 '^pkgver=' "$PKGBUILD" | cut -d= -f2; }
read_srcinfo()   { grep -m1 '^[[:space:]]*pkgver[[:space:]]*=' "$SRCINFO" | awk '{print $3}'; }

check() {
    local a b c d
    a="$(read_pyproject)"; b="$(read_init)"; c="$(read_pkgbuild)"; d="$(read_srcinfo)"
    printf '  pyproject.toml            %s\n' "$a"
    printf '  python/bat2sh/__init__.py %s\n' "$b"
    printf '  PKGBUILD pkgver           %s\n' "$c"
    printf '  .SRCINFO pkgver           %s\n' "$d"
    if [[ "$a" != "$b" || "$a" != "$c" || "$a" != "$d" ]]; then
        echo "错误: 四处版本号不一致（这正是 D-1 缺陷）。" >&2
        echo "      修复: ./scripts/release-bump.sh <版本>  且必须在打 tag 之前提交。" >&2
        return 1
    fi
    echo "    OK: 四处版本一致 = $a"
}

if [[ "${1:-}" == "--check" ]]; then
    echo "==> 版本一致性检查（D-1 门）"
    check
    exit $?
fi

NEW="${1:-}"
if [[ -z "$NEW" ]]; then
    echo "用法: $0 <版本号>   例如 $0 2.9.0" >&2
    echo "      $0 --check     只校验版本一致性" >&2
    exit 2
fi
if [[ ! "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "错误: 版本号须形如 X.Y.Z（收到: $NEW）" >&2
    exit 2
fi

OLD="$(read_pyproject)"
echo "==> 版本 bump: $OLD -> $NEW"

sed -i "0,/^version[[:space:]]*=.*/s//version = \"$NEW\"/" "$PYPROJECT"
sed -i "0,/^__version__[[:space:]]*=.*/s//__version__ = \"$NEW\"/" "$INIT"
sed -i "0,/^pkgver=.*/s//pkgver=$NEW/" "$PKGBUILD"

if command -v makepkg >/dev/null 2>&1 && makepkg --printsrcinfo > "$SRCINFO.tmp" 2>/dev/null; then
    mv "$SRCINFO.tmp" "$SRCINFO"
    echo "    .SRCINFO 已由 makepkg --printsrcinfo 重新生成"
else
    rm -f "$SRCINFO.tmp"
    sed -i "0,/^[[:space:]]*pkgver[[:space:]]*=.*/s//\tpkgver = $NEW/" "$SRCINFO"
    # source 行格式是 "<本地文件名>::<URL>"，两半都要更新；
    # 只改 URL 会让本地文件名停留在旧版本（本次修复过程中实测到的缺陷）。
    sed -i "s|bat2sh-[0-9][0-9.]*\.tar\.gz::|bat2sh-$NEW.tar.gz::|" "$SRCINFO"
    sed -i "s|/refs/tags/v[0-9][0-9.]*\.tar\.gz|/refs/tags/v$NEW.tar.gz|" "$SRCINFO"
    echo "    警告: makepkg 不可用，.SRCINFO 以 sed 回退更新" >&2
fi

echo "==> 结果"
check

cat <<'EOF'

==> 后续（顺序不可颠倒）
  1. git add -A && git commit -m "chore: bump version to v<NEW>"
  2. ./scripts/release-preflight.sh          # 必须通过
  3. git tag -a v<NEW> -m "v<NEW>" && git push origin main v<NEW>
  4. ./scripts/release-sync-pkg.sh <NEW>     # tag 之后同步 sha256（自指哈希，无法提前算）
  5. ./scripts/release-assets.sh <NEW>       # 上传二进制资产到 GitHub Release

注意: PKGBUILD 的 sha256sums 此刻仍指向上一个版本的 tarball，这是自指哈希的
      客观限制，第 4 步会纠正。**不要**为了让哈希看起来对而推迟 pkgver。
EOF
