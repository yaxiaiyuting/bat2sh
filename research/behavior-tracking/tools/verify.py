#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
样本间隔离验证 —— 把 `rollback-design.md` §5.1 的 J1/J2/J3 判据固化为可复跑工具。

    python3 verify.py results/copy.json results/other.json results/copy-rerun.json

为什么要单独一个工具：**清单差分本身无法证明隔离**（差分自归一化，设计 §5.1）。
朴素判据"B 的差分不含 A 创建的文件"在回滚失败时**同样成立** —— 残留文件在
before/after 里都存在且哈希相同，落进 `unchanged`，差分里根本看不见。
所以隔离必须用三重判据，且必须**能反复跑**，不能靠一次性人工目检。

判据：
  J1  所有运行的 baseline_manifest_hash 完全相同
      ⇒ 各次运行的**起点是同一状态**。起点相同，结果之差只能来自样本。**最强的一条**
  J2  Y 的 after **绝对清单**中不含"X 创建、而 Y 自己没创建"的路径
      ⇒ 绕开差分自归一化，直接看绝对状态
  J3  每次运行都确有产物（created 非空且 ⊆ after_manifest）
      ⇒ 否则"Y 里没有 X 的产物"可能只是因为 **X 压根没生效** —— 反向假通过

退出码：0 全部通过 / 1 有判据失败 / 4 用法错误
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def load(paths):
    runs = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        fs = d.get("filesystem") or {}
        if not fs:
            print(f"⚠️  {p} 没有 filesystem 段，跳过", file=sys.stderr)
            continue
        runs.append({
            "path": p,
            "label": os.path.basename(p),
            "sample": (d.get("script") or {}).get("name", "?"),
            "sample_sha256": (d.get("script") or {}).get("sha256", ""),
            "baseline_hash": fs.get("baseline_manifest_hash"),
            "baseline_n": fs.get("before_count"),
            "created": list(fs.get("created") or []),
            "after": set((fs.get("after_manifest") or {}).keys()),
            "known": {a["path"] for a in (fs.get("known_artifacts") or [])},
            "exit_code": (d.get("execution") or {}).get("exit_code"),
            "stdout": ((d.get("stdout") or {}).get("text") or ""),
            "revert_op_ms": (d.get("rollback") or {}).get("revert_op_ms"),
            "base_intact": ((d.get("rollback") or {}).get("base_intact") or {}).get("unchanged"),
        })
    return runs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="verify.py",
                                 description="样本间隔离验证（J1/J2/J3）")
    ap.add_argument("fingerprints", nargs="+", help="collect.py 产出的指纹 JSON")
    args = ap.parse_args(argv)

    runs = load(args.fingerprints)
    if len(runs) < 2:
        print("用法错误：至少需要 2 份指纹才能验证隔离", file=sys.stderr)
        return 4

    failures: list[str] = []

    print("=" * 78)
    print("运行清单")
    print("=" * 78)
    for r in runs:
        print(f"  {r['label']:22s} 样本={r['sample']:12s} exit={r['exit_code']}  "
              f"baseline_n={r['baseline_n']}  created={len(r['created'])}  "
              f"revert_op={r['revert_op_ms']}ms")

    # ---------------- J1 ----------------
    print()
    print("=" * 78)
    print("J1  起点同一性 —— 所有运行的 baseline_manifest_hash 必须完全相同")
    print("=" * 78)
    hashes = {r["baseline_hash"] for r in runs}
    for r in runs:
        print(f"  {r['label']:22s} {r['baseline_hash']}")
    if len(hashes) == 1 and None not in hashes:
        print(f"\n  ✅ J1 通过：{len(runs)} 次运行的起点逐字节相同")
    else:
        print(f"\n  ❌ J1 失败：出现 {len(hashes)} 个不同的起点")
        failures.append("J1")

    # ---------------- J2 ----------------
    print()
    print("=" * 78)
    print("J2  无跨样本污染 —— Y 的 after 绝对清单不得含 'X 创建且 Y 未创建' 的路径")
    print("=" * 78)
    j2_bad = 0
    for x in runs:
        for y in runs:
            if x is y:
                continue
            # X 创建的路径中，Y 自己没创建、也不是 Y 采集器自身写入的 → 若出现在 Y 的 after 里即污染
            foreign = (set(x["created"]) & y["after"]) - set(y["created"]) - y["known"]
            if foreign:
                j2_bad += 1
                print(f"  ❌ {y['label']} 含 {x['label']} 的产物：{sorted(foreign)}")
    if j2_bad == 0:
        print(f"  ✅ J2 通过：{len(runs)}×{len(runs)-1} 组有向比对，无任何跨样本残留")
        # 额外正面证据：确认对侧样本的产物确实**曾经**存在过
        for x in runs:
            for y in runs:
                if x is y:
                    continue
                gone = [p for p in x["created"] if p not in y["after"]]
                if gone:
                    print(f"     · {x['label']} 的产物在 {y['label']} 中确认消失：{sorted(gone)}")
    else:
        failures.append("J2")

    # ---------------- J3 ----------------
    print()
    print("=" * 78)
    print("J3  样本有效性 —— 每次运行都必须确有产物（否则隔离结论平凡成立）")
    print("=" * 78)
    j3_bad = 0
    for r in runs:
        missing = [p for p in r["created"] if p not in r["after"]]
        if not r["created"]:
            j3_bad += 1
            print(f"  ❌ {r['label']}：created 为空 —— 样本**未生效**，"
                  f"它的隔离结论不构成证据")
        elif missing:
            j3_bad += 1
            print(f"  ❌ {r['label']}：created 中有路径不在 after_manifest 里：{missing}")
        else:
            print(f"  ✅ {r['label']}：{len(r['created'])} 项产物，且全部在 after 绝对清单中")
    if j3_bad:
        failures.append("J3")

    # ---------------- 附加：base 只读 + 重复性 ----------------
    print()
    print("=" * 78)
    print("附加  base 只读性 / 同一样本重复性")
    print("=" * 78)
    for r in runs:
        mark = {True: "✅", False: "❌", None: "–"}.get(r["base_intact"], "–")
        print(f"  {mark} {r['label']:22s} base 未被写入 = {r['base_intact']}")
        if r["base_intact"] is False:
            failures.append("base-intact")

    by_sample: dict[str, list] = {}
    for r in runs:
        by_sample.setdefault(r["sample"], []).append(r)
    for sample, group in by_sample.items():
        if len(group) < 2:
            continue
        sigs = {(g["exit_code"], g["stdout"], tuple(sorted(g["created"]))) for g in group}
        if len(sigs) == 1:
            print(f"  ✅ 重复性：{sample} 跑 {len(group)} 次，"
                  f"退出码/stdout/产物集合完全一致")
        else:
            print(f"  ⚠️  重复性：{sample} 跑 {len(group)} 次，行为指纹**不一致**")
            for g in group:
                print(f"       {g['label']}: exit={g['exit_code']} "
                      f"stdout={g['stdout']!r} created={sorted(g['created'])}")
            failures.append("repeatability")

    # ---------------- 判定 ----------------
    print()
    print("=" * 78)
    if failures:
        print(f"判定：❌ 未通过 —— 失败判据：{', '.join(sorted(set(failures)))}")
        print("=" * 78)
        return 1
    print("判定：✅ 隔离成立（J1 + J2 + J3 全部通过）")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
