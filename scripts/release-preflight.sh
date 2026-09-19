#!/usr/bin/env bash
# bat2sh 发布前置检查（tag 之前必须跑）：在“类 CI”环境下验证，避免 tag 后才发现红。
#
# 背景 1（v1.8.1 事故）：某个测试依赖外部语料 ~/下载/非常批处理/（未入仓），
#   本地全绿但 CI 红，tag 打完后才发现。本脚本用**空 HOME** 复现 CI 的“无外部资源”条件。
#
# 背景 2（D-1 缺陷，2026-09-20 评估发现）：v2.1.0 至 v2.8.1 **连续 9 个 tag** 内，
#   PKGBUILD 的 pkgver 都停留在**上一版**（例如 tag v2.8.1 的 tarball 里 pkgver=2.8.0），
#   而同一棵树的 python/bat2sh/__init__.py 已是 2.8.1。根因是版本同步提交永远落在
#   tag 之后。后果：从 Release 源码包执行 makepkg -si 的用户会构建出上一个版本。
#   本脚本第 2 步即为该纪律的**强制执行点**：版本号必须在打 tag 之前就位。
#
# 用法: ./scripts/release-preflight.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

echo "==> 1/4 工作区必须干净（避免把未提交改动打进 tag）"
if [[ -n "$(git status --porcelain)" ]]; then
    echo "错误: 工作区不干净：" >&2
    git status --short >&2
    exit 1
fi
echo "    OK"

echo "==> 2/4 版本一致性（D-1 门）：pyproject / __init__ / PKGBUILD / .SRCINFO"
if ! ./scripts/release-bump.sh --check; then
    echo "错误: 四处版本号不一致，禁止 tag。" >&2
    echo "      先执行 ./scripts/release-bump.sh <版本> 并随 bump 提交一起入库。" >&2
    exit 1
fi

echo "==> 3/4 类 CI 环境跑 pytest（空 HOME，模拟 CI 无外部语料/配置）"
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT
if ! env HOME="$TMP_HOME" XDG_CONFIG_HOME="$TMP_HOME/.config" XDG_STATE_HOME="$TMP_HOME/.state" \
        pytest -q; then
    echo "错误: 类 CI 环境下 pytest 失败（CI 会红，禁止 tag）" >&2
    exit 1
fi

echo "==> 4/4 引用仓库外资源的测试必须带 pytest.skip 兜底（否则 CI 会红）"
# 旧版本此步只“提示、不判失败”，因此拦不住 v1.8.1 那类问题；现改为真失败。
violations=0
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if ! grep -q 'pytest\.skip' "$f"; then
        echo "  违规: $f 引用了仓库外路径，但没有 pytest.skip 兜底" >&2
        grep -nE '(Path\.home\(\)|os\.path\.expanduser\(|~/)' "$f" >&2 || true
        violations=1
    fi
done < <(grep -rlE '(Path\.home\(\)|os\.path\.expanduser\(|~/)' tests/ --include='*.py' || true)

if [[ "$violations" -ne 0 ]]; then
    echo "错误: 上述测试在 CI（无外部语料）会**失败**而非跳过。禁止 tag。" >&2
    echo "      修法: 在缺失外部资源时 pytest.skip(...)，或把语料入仓。" >&2
    exit 1
fi
echo "    OK"

echo "==> 发布前置检查通过（可安全打 tag）"
