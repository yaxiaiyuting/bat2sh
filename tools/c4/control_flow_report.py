#!/usr/bin/env python3
"""C4 goto 控制流只读报告（v1.10.0b1）。

用途
----
复现 ``core/control_flow.py`` 台账中的 goto 形态分布，并给出**转换器口径**的
goto TODO 统计（权威），用于 `docs/session-c4-design.md` / 报告的证据核对。

**只读**：不写仓库、不改转换器、不跑沙箱。

用法
----
    python3 tools/c4/control_flow_report.py [--corpus DIR] [--json OUT]

corpus 缺省为 ``~/下载/非常批处理``；不存在时以退出码 2 提示（CI 无外部语料）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))


def _load_control_flow():
    from bat2sh.core import control_flow

    return control_flow


def _corpus_files(corpus: Path):
    return sorted(
        (p for p in corpus.rglob("*") if p.is_file() and p.suffix.lower() in (".bat", ".cmd")),
        key=lambda p: str(p.relative_to(corpus)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="C4 goto 控制流只读报告")
    parser.add_argument("--corpus", default=str(Path.home() / "下载/非常批处理"))
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"语料目录不存在：{corpus}（CI/无外部语料环境跳过）", file=sys.stderr)
        return 2

    cf = _load_control_flow()
    problems = cf.validate_control_flow_patterns()
    if problems:
        print("台账校验失败：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(REPO / "python"))
    from bat2sh.core.engine import convert_file  # noqa: E402
    from bat2sh.core.settings import ConvertSettings  # noqa: E402

    statements: Counter[str] = Counter()
    files_by_shape: dict[str, set[str]] = {}
    converter_todo_files: dict[str, int] = {}
    label_in_block: Counter[str] = Counter()

    for path in _corpus_files(corpus):
        rel = str(path.relative_to(corpus))
        summary = cf.summarize_goto_lines(
            path.read_text(encoding="utf-8", errors="replace").splitlines()
        )
        statements.update(summary)
        for key in summary:
            files_by_shape.setdefault(key, set()).add(rel)
        result = convert_file(path, ConvertSettings(bash_check=False), write=False)
        if result.error:
            continue
        gotos = [
            d for d in result.report.todos
            if d.category == "control_flow" and "goto" in d.message
        ]
        if gotos:
            converter_todo_files[rel] = len(gotos)
        blocked = [d for d in result.report.errors if d.category == "control_flow"]
        if blocked:
            label_in_block[rel] = len(blocked)

    if label_in_block:
        statements["label_in_block"] = sum(label_in_block.values())
        files_by_shape["label_in_block"] = set(label_in_block)

    print("== 扫描器口径（summarize_goto_lines；echo/rem 与 CJK 标签已处理） ==")
    print(f"goto 语句总数 = {sum(v for k, v in statements.items() if k in cf.PRIMARY_SHAPE_KEYS)}")
    for pattern in cf.GOTO_PATTERNS:
        actual = statements.get(pattern.key, 0)
        files = len(files_by_shape.get(pattern.key, ()))
        flag = "OK" if (actual, files) == (pattern.corpus_statements, pattern.corpus_files) else "MISMATCH"
        kind = "主" if pattern.primary else "辅"
        print(
            f"  [{flag:>8}] {kind} {pattern.key:<16} 台账 {pattern.corpus_statements:>4}/{pattern.corpus_files:<3}"
            f"  实测 {actual:>4}/{files:<3}  conf={pattern.confidence}"
        )

    print()
    print("== 转换器口径（权威；goto TODO） ==")
    print(f"含 goto TODO 的文件 = {len(converter_todo_files)}")
    print(f"goto TODO 总数     = {sum(converter_todo_files.values())}")

    payload = {
        "scanner_total": sum(statements.values()),
        "scanner_by_shape": dict(statements),
        "scanner_files_by_shape": {k: len(v) for k, v in files_by_shape.items()},
        "converter_todo_files": len(converter_todo_files),
        "converter_todo_total": sum(converter_todo_files.values()),
        "ledger": [
            {"key": p.key, "primary": p.primary, "confidence": p.confidence}
            for p in cf.GOTO_PATTERNS
        ],
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"已写出 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
