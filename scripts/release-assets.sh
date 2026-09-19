#!/usr/bin/env bash
# 发布二进制资产到 GitHub Release（D-2 修复）。
#
# 背景（D-2 缺陷）：抽查 v1.0.0 / v1.11.0 / v2.0.0 / v2.4.0 / v2.7.0 / v2.8.1，
# 每个 Release 的**上传资产数都是 0** —— GitHub 只挂了自动生成的
# "Source code (zip/tar.gz)"。而项目本地其实为每个版本都构建了
# bat2sh-<ver>.tar.gz（sdist）与 bat2sh-<ver>-1-any.pkg.tar.zst（Arch 包），
# 这些成果从未发布，外部用户拿不到开箱即用的包。
#
# 本脚本把"本地已构建"变成"已发布"这一步固化下来。
#
# 前置: gh 已登录（gh auth status 通过）；tag 已推送。
# 用法:
#   ./scripts/release-assets.sh 2.9.0            # 构建并上传
#   ./scripts/release-assets.sh 2.9.0 --no-build # 只上传已存在的产物
#   ./scripts/release-assets.sh 2.9.0 --dry-run  # 只显示将要上传什么
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

VER="${1:-}"
MODE="${2:-}"
if [[ ! "$VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "用法: $0 <版本号> [--no-build|--dry-run]" >&2
    exit 2
fi
TAG="v$VER"

files=()

if [[ "$MODE" != "--no-build" ]]; then
    echo "==> 构建 sdist"
    rm -rf dist
    if command -v python3 >/dev/null 2>&1 && python3 -m build --sdist >/dev/null 2>&1; then
        echo "    dist/ 已生成"
    else
        echo "    警告: python3 -m build 失败或不可用，跳过 sdist" >&2
        echo "          修复: pip install build" >&2
    fi

    echo "==> 构建 Arch 包（makepkg）"
    if command -v makepkg >/dev/null 2>&1; then
        if makepkg -f --noconfirm >/dev/null 2>&1; then
            echo "    Arch 包已生成"
        else
            echo "    警告: makepkg 失败（可能缺少 makedepends），跳过 Arch 包" >&2
        fi
    else
        echo "    警告: 本机无 makepkg，跳过 Arch 包" >&2
    fi

    echo "==> 构建 Debian 包（.deb）"
    if [[ -x packaging/build-deb.sh ]]; then
        if ./packaging/build-deb.sh >/dev/null 2>&1; then
            echo "    .deb 已生成"
        else
            echo "    警告: build-deb.sh 失败，跳过 .deb" >&2
        fi
    else
        echo "    警告: 无 packaging/build-deb.sh，跳过 .deb" >&2
    fi

    echo "==> 构建 RPM 包（.rpm）"
    if [[ -x packaging/build-rpm.sh ]]; then
        if ./packaging/build-rpm.sh >/dev/null 2>&1; then
            echo "    .rpm 已生成"
        else
            echo "    警告: build-rpm.sh 失败（可能缺 rpmbuild），跳过 .rpm" >&2
        fi
    else
        echo "    警告: 无 packaging/build-rpm.sh，跳过 .rpm" >&2
    fi
fi

# 收集产物：sdist / .deb / .rpm 在 dist/，Arch 包在仓库根
while IFS= read -r -d '' f; do files+=("$f"); done < <(find dist -maxdepth 1 -name "bat2sh-$VER.tar.gz" -print0 2>/dev/null)
while IFS= read -r -d '' f; do files+=("$f"); done < <(find dist -maxdepth 1 -name "bat2sh*$VER*.deb" -print0 2>/dev/null)
while IFS= read -r -d '' f; do files+=("$f"); done < <(find dist -maxdepth 1 -name "bat2sh-$VER-*.rpm" -print0 2>/dev/null)
while IFS= read -r -d '' f; do files+=("$f"); done < <(find . -maxdepth 1 -name "bat2sh-$VER-*.pkg.tar.*" -print0 2>/dev/null)

if [[ ${#files[@]} -eq 0 ]]; then
    echo "错误: 未找到 $VER 的任何产物。" >&2
    echo "      期望 dist/bat2sh-$VER.tar.gz 或 ./bat2sh-$VER-1-any.pkg.tar.zst" >&2
    exit 1
fi

echo "==> 将上传到 Release $TAG:"
for f in "${files[@]}"; do
    printf '    %-48s %s\n' "$f" "$(du -h "$f" | cut -f1)"
done

if [[ "$MODE" == "--dry-run" ]]; then
    echo "==> --dry-run：未执行上传"
    exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "错误: 未找到 gh CLI。安装后执行 gh auth login。" >&2
    exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
    echo "错误: gh 未登录或 token 失效。请执行: gh auth login  (或 gh auth refresh)" >&2
    exit 1
fi

if ! gh release view "$TAG" >/dev/null 2>&1; then
    echo "错误: GitHub 上不存在 Release $TAG。" >&2
    echo "      先在网页创建 Release（或用 gh release create $TAG --title ... --notes-file ...）" >&2
    exit 1
fi

echo "==> 上传"
gh release upload "$TAG" "${files[@]}" --clobber
echo "==> 完成: https://github.com/yaxiaiyuting/bat2sh/releases/tag/$TAG"
