#!/usr/bin/env bash
# 把 docs/releases/<ver>.md 同步为对应 GitHub Release 的说明（release notes）。
#
# 背景（2026-09-20 评估）：
#   历代 release 说明的格式在 **v1.10.0a1** 起漂移——标题由 H2 变成 H1
#   （`# bat2sh vX.Y.Z 发布说明 —— xxx`），并且 v1.10.0a1 之后**全部 15 个版本
#   都缺少 Full Changelog 页脚**；而 v1.2.2–v1.9.2 的既有格式是
#   `## bat2sh vX.Y.Z` + 结尾 `**Full Changelog**: .../compare/<prev>...<ver>`。
#
#   本次已把这 15 个漂移文档对齐（标题 + 页脚），本脚本负责把对齐后的内容
#   推送到 GitHub Release，使仓库文档与线上 Release 保持一致。
#
# 说明：v1.2.2 / v1.2.3 两个 Release 没有对应的仓库文档（它们本就是参考格式），
#       本脚本会跳过 —— 不从渲染后的 HTML 反向重建，避免杜撰内容。
#
# 前置: gh auth login（token 失效时无法执行）
# 用法:
#   ./tools/publish/sync-release-notes.sh --dry-run         # 只列出将同步什么
#   ./tools/publish/sync-release-notes.sh                   # 同步全部有文档的版本
#   ./tools/publish/sync-release-notes.sh v2.8.1 v2.8.0     # 只同步指定版本
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$HERE"

DRY=0
TARGETS=()
for arg in "$@"; do
    case "$arg" in
        --dry-run|-n) DRY=1 ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *) TARGETS+=("$arg") ;;
    esac
done

if [[ "${#TARGETS[@]}" -eq 0 ]]; then
    while IFS= read -r f; do
        TARGETS+=("$(basename "$f" .md)")
    done < <(ls docs/releases/*.md | grep -v -- '-verification\.md$' | sort -V)
fi

if [[ "$DRY" -eq 0 ]]; then
    if ! command -v gh >/dev/null 2>&1; then
        echo "错误: 未找到 gh CLI。" >&2; exit 1
    fi
    if ! gh auth status >/dev/null 2>&1; then
        echo "错误: gh 未登录或 token 已失效。请先执行: gh auth login" >&2
        echo "      （本脚本只改 Release 说明，不会动代码或 tag）" >&2
        exit 1
    fi
fi

ok=0; skip=0; fail=0
for ver in "${TARGETS[@]}"; do
    doc="docs/releases/${ver}.md"
    if [[ ! -f "$doc" ]]; then
        echo "  跳过 $ver: 无 $doc" >&2
        skip=$((skip+1)); continue
    fi
    if ! git rev-parse -q --verify "refs/tags/$ver" >/dev/null; then
        echo "  跳过 $ver: 本地无该 tag" >&2
        skip=$((skip+1)); continue
    fi

    title="$(head -1 "$doc")"
    if [[ "$title" != "## bat2sh $ver" ]]; then
        echo "  警告 $ver: 标题未对齐 -> $title" >&2
    fi
    if ! grep -q 'Full Changelog' "$doc"; then
        echo "  警告 $ver: 缺 Full Changelog 页脚" >&2
    fi

    if [[ "$DRY" -eq 1 ]]; then
        printf '  [dry-run] gh release edit %-12s --notes-file %s\n' "$ver" "$doc"
        ok=$((ok+1)); continue
    fi

    if gh release edit "$ver" --notes-file "$doc" >/dev/null 2>&1; then
        echo "  已同步 $ver"
        ok=$((ok+1))
    else
        echo "  失败   $ver" >&2
        fail=$((fail+1))
    fi
done

echo
echo "==> 完成: 成功 $ok / 跳过 $skip / 失败 $fail"
[[ "$fail" -eq 0 ]]
