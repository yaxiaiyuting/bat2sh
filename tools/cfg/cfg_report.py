#!/usr/bin/env python3
"""CFG 只读数据模型报告（v2.1.0 P4）。

用途
----
复现 ``core/cfg.py`` 的标签位置表与 goto→标签边统计，并与 C4 形态台账
（``core/control_flow.py``）交叉核对；输出多入口标签、重复标签、冗余 goto 等
**v2.2 goto 语义转换**所需的 CFG 事实。

**只读**：不写仓库、不改转换器、不跑沙箱。

用法
----
    python3 tools/cfg/cfg_report.py [--corpus DIR] [--json OUT]

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


def _corpus_files(corpus: Path):
    return sorted(
        (p for p in corpus.rglob("*") if p.is_file() and p.suffix.lower() in (".bat", ".cmd")),
        key=lambda p: str(p.relative_to(corpus)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="CFG 只读数据模型报告")
    parser.add_argument("--corpus", default=str(Path.home() / "下载/非常批处理"))
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"语料目录不存在：{corpus}（CI/无外部语料环境跳过）", file=sys.stderr)
        return 2

    from bat2sh.core import control_flow as cf
    from bat2sh.core.cfg import build_cfg_from_text, summarize_cfg, validate_cfg

    ledger_problems = cf.validate_control_flow_patterns()
    if ledger_problems:
        print("C4 台账校验失败：", file=sys.stderr)
        for problem in ledger_problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    total_by_shape: Counter[str] = Counter()
    total_by_direction: Counter[str] = Counter()
    files_by_shape: dict[str, set[str]] = {}
    labels = edges = labels_in_block = files_with_duplicates = 0
    multi_entry: dict[str, list[str]] = {}
    problems: list[str] = []

    for path in _corpus_files(corpus):
        rel = str(path.relative_to(corpus))
        cfg = build_cfg_from_text(path.read_text(encoding="utf-8", errors="replace"))
        problems.extend(f"{rel}: {item}" for item in validate_cfg(cfg))
        summary = summarize_cfg(cfg)
        labels += int(summary["labels"])
        edges += int(summary["edges"])
        labels_in_block += int(summary["labels_in_block"])
        total_by_shape.update(summary["by_shape"])
        total_by_direction.update(summary["by_direction"])
        for key in summary["by_shape"]:
            files_by_shape.setdefault(key, set()).add(rel)
        if summary["duplicate_labels"]:
            files_with_duplicates += 1
        if summary["multi_entry_labels"]:
            multi_entry[rel] = list(summary["multi_entry_labels"])

    print("== CFG 数据模型（core/cfg.py，只读） ==")
    print(f"标签位置 = {labels}；goto 边 = {edges}")
    print()
    print("== goto 形态（与 C4 台账逐项交叉核对） ==")
    for pattern in cf.GOTO_PATTERNS:
        if not pattern.primary:
            continue
        actual = total_by_shape.get(pattern.key, 0)
        files = len(files_by_shape.get(pattern.key, ()))
        flag = "OK" if (actual, files) == (pattern.corpus_statements, pattern.corpus_files) else "CHECK"
        print(f"  [{flag:>5}] {pattern.key:<16} 台账 {pattern.corpus_statements:>4}/{pattern.corpus_files:<3}  实测 {actual:>4}/{files:<3}")
    print()
    print("== 标签位置（CFG 括号净值口径；非 goto 边） ==")
    print(f"label_in_block（净值近似） = {labels_in_block}；C4 台账 97/4 为转换器口径（report.errors），两者口径不同")
    print()
    print(f"方向分布 = {dict(total_by_direction)}")
    print(f"多入口标签文件 = {len(multi_entry)}；重复标签文件 = {files_with_duplicates}")
    print(f"逐文件 validate_cfg 问题 = {len(problems)}")
    for problem in problems[:20]:
        print(f"  - {problem}")

    payload = {
        "labels": labels,
        "labels_in_block": labels_in_block,
        "edges": edges,
        "by_shape": dict(total_by_shape),
        "files_by_shape": {k: len(v) for k, v in files_by_shape.items()},
        "by_direction": dict(total_by_direction),
        "multi_entry": multi_entry,
        "duplicate_label_files": files_with_duplicates,
        "validate_problems": problems,
    }
    if args.json:
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已写出 {args.json}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
