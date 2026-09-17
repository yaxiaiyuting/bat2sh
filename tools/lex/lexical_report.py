#!/usr/bin/env python3
"""tools/lex —— 词法层残余额账只读报告（v1.10.0rc1 / Session C-lex）。

用途：
  python3 tools/lex/lexical_report.py [--corpus DIR] [--no-corpus]

1. 校验台账（`validate_lexical_residuals()`）；
2. **漂移检测**：把每条残余的 `trigger` 跑过转换器，确认仍复现「逸出」守卫
   （台账若失效则报 DRIFT，便于后续版本发现已修）；
3. **语料复现**（可选）：扫描语料，统计 degraded 文件中触发守卫的集合，
   与台账 `ids` 交叉核对。

**只读**：不写仓库、不改转换器、不跑沙箱。无语料时 `--corpus` 请求会退出码 2。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))

from bat2sh.core.lexical_residuals import (  # noqa: E402
    LEXICAL_RESIDUALS,
    LEAK_GUARD_MESSAGE,
    summarize_residuals,
    validate_lexical_residuals,
)

DEFAULT_CORPUS = Path.home() / "下载" / "非常批处理"


def _symptom_present(report) -> bool:
    """产物是否仍触发「逸出」守卫（台账漂移检测，不涉及沙箱/rc）。"""
    return any("逸出 for 循环" in d.message for d in report.todos)


def drift_check() -> int:
    """把每条残余的 trigger 跑过转换器，确认仍复现守卫。返回失败数。"""
    from bat2sh.core.engine import convert_file
    from bat2sh.core.settings import ConvertSettings

    failures = 0
    for r in LEXICAL_RESIDUALS:
        tmp = Path("/tmp") / f"lex_drift_{r.id}.bat"
        tmp.write_text("@echo off\n" + r.trigger + "\n", encoding="utf-8")
        res = convert_file(tmp, ConvertSettings(bash_check=False), write=False)
        if res.error:
            print(f"  [{r.id}] CONVERT-ERROR {res.error}")
            failures += 1
            continue
        hit = _symptom_present(res.report)
        status = "REPRODUCES" if hit else "DRIFT(可能已修)"
        print(f"  [{r.id}] {r.mechanism} {status}  todo={res.report.todo_count} "
              f"warn={res.report.warning_count}")
        if not hit:
            failures += 1
    return failures


def corpus_check(corpus: Path) -> int:
    if not corpus.exists():
        print(f"语料不存在: {corpus}（CI 无外部语料，退出码 2）")
        return 2
    from bat2sh.core.engine import convert_file
    from bat2sh.core.settings import ConvertSettings

    files = sorted(
        (p for p in corpus.rglob("*") if p.is_file() and p.suffix.lower() in (".bat", ".cmd")),
        key=lambda p: str(p.relative_to(corpus)),
    )
    hits: dict[str, str] = {}
    for idx, path in enumerate(files, 1):
        res = convert_file(path, ConvertSettings(bash_check=False), write=False)
        if res.error:
            continue
        if any("逸出 for 循环" in d.message for d in res.report.todos):
            rel = str(path.relative_to(corpus))
            hits[f"{idx:03d}"] = rel
    print(f"  语料 {len(files)} 文件；触发守卫 {len(hits)} 个:")
    for cid, rel in hits.items():
        print(f"    {cid} {rel}")
    # 本工具不跑沙箱，故无法判定 rc==0；台账的 4 条是「触发守卫 ∩ degraded」
    # （degraded 需沙箱确认）。此处只做「台账 ids ⊆ 触发集合」的子集核对 + 差异披露。
    expected = {r.id for r in LEXICAL_RESIDUALS}
    extra = sorted(set(hits) - expected)
    missing = sorted(expected - set(hits))
    ok = not missing
    print(f"  台账交叉核对: 期望 ⊆ 实测 → {'OK' if ok else 'MISSING ' + str(missing)}")
    if extra:
        print(f"  额外触发（非本台账靶子；含语法失败/rc≠0，需沙箱确认 degraded）: {extra}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="词法层残余额账只读报告")
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--no-corpus", action="store_true", help="跳过语料扫描")
    args = ap.parse_args()

    print("== 台账校验 ==")
    problems = validate_lexical_residuals()
    if problems:
        for p in problems:
            print(f"  ! {p}")
        return 3
    summary = summarize_residuals()
    print(f"  OK：{summary['count']} 条 / 机制 {summary['mechanisms']}")

    print("== 漂移检测（trigger 复现守卫） ==")
    failures = drift_check()
    if failures:
        print(f"  {failures} 条未复现（可能已修，请更新台账）")

    corpus_rc = 0
    if not args.no_corpus:
        print("== 语料复现 ==")
        corpus_rc = corpus_check(args.corpus)
        if corpus_rc == 2 and args.corpus == DEFAULT_CORPUS:
            corpus_rc = 0  # 默认语料缺失不算失败（CI 无外部语料）

    return max(1 if failures else 0, corpus_rc)


if __name__ == "__main__":
    raise SystemExit(main())
