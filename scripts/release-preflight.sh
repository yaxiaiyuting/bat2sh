#!/usr/bin/env bash
# bat2sh 发布前置检查（tag 之前必须跑）：在“类 CI”环境下验证，避免 tag 后才发现红。
#
# 背景（v1.8.1 事故）：某个测试依赖外部语料 ~/下载/非常批处理/（未入仓），
# 本地全绿但 CI 红，tag 打完后才发现。本脚本用**空 HOME** 复现 CI 的“无外部资源”条件。
#
# 用法: ./scripts/release-preflight.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

echo "==> 1/3 工作区必须干净（避免把未提交改动打进 tag）"
if [[ -n "$(git status --porcelain)" ]]; then
    echo "错误: 工作区不干净：" >&2
    git status --short >&2
    exit 1
fi
echo "    OK"

echo "==> 2/3 类 CI 环境跑 pytest（空 HOME，模拟 CI 无外部语料/配置）"
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT
if ! env HOME="$TMP_HOME" XDG_CONFIG_HOME="$TMP_HOME/.config" XDG_STATE_HOME="$TMP_HOME/.state" \
        pytest -q; then
    echo "错误: 类 CI 环境下 pytest 失败（CI 会红，禁止 tag）" >&2
    exit 1
fi

echo "==> 3/3 校验测试不得依赖仓库外的外部资源路径"
if grep -rnE '(Path\.home\(\)|os\.path\.expanduser\(|~/)' tests/ --include='*.py' \
        | grep -vE 'test_skip|pytest\.skip|# ' >/dev/null; then
    echo "   提示: 以下位置引用了 HOME/外部路径，请确认在缺失时 skip（本步仅提示，不判失败）："
    grep -rnE '(Path\.home\(\)|os\.path\.expanduser\(|~/)' tests/ --include='*.py' \
        | grep -vE 'test_skip|pytest\.skip|# ' || true
fi

echo "==> 发布前置检查通过（可安全打 tag）"
