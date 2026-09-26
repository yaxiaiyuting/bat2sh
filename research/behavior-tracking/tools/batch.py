#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bat2sh 行为采集 —— 批量执行器

    python3 tools/batch.py --samples batch-samples.txt --output results/

一个命令跑完清单里的所有样本。每个样本走**完整**的 collect.py 流程：

    回滚(覆盖层重建) → 施加网络姿态 → 冷启动 → 等 agent → 基线清单
      → 上传 → 嗅探就绪 → 执行 → 停止嗅探 → 事后清单 → 差分 → 指纹落盘 → 停机

设计依据：`research/behavior-tracking/rollback-design.md`（回滚与隔离判据）、
          `network-policy.md`（网络姿态）

三条硬要求（任务书 §2.2）：
  1. **每个样本都回滚** —— 否则前一个样本的副作用会污染后一个（J1/J2/J3 会失效）
  2. **失败不阻塞** —— 单个样本失败记录后继续，最后统一汇报
  3. **进度可见** —— 逐样本打印状态、耗时、产物

**为什么用子进程调 collect.py 而不是 import 它**：
  * 进程级隔离：单个样本把 QGA 通道搞挂、或留下僵尸嗅探进程，不会传染给后面的样本
  * `collect.py` 的退出码就是天然的分类结果（1 环境 / 2 VM / 3 Guest / 5 网络策略）
  * 崩溃（段错误 / OOM）也能被捕获成"该样本失败"，而不是整批中断

退出码：0 全部成功 / 1 有样本失败 / 4 用法错误
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
COLLECT = os.path.join(TOOLS_DIR, "collect.py")


class UsageError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# 清单解析
# --------------------------------------------------------------------------


def parse_samples(path: str) -> list[dict]:
    """解析 TSV 清单：`<guest_name>\\t<local_path>\\t<tags>\\t<sha256>`。

    `#` 开头是注释；空行跳过。**不对路径做存在性宽容** —— 找不到就报错，
    因为"样本静默消失"会让 N/N 变成一句空话。
    """
    if not os.path.isfile(path):
        raise UsageError(f"清单不存在：{path}")
    out: list[dict] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                raise UsageError(f"{path}:{lineno} 字段不足（需要至少 "
                                 f"<guest_name>\\t<local_path>）：{line!r}")
            gname, local = parts[0].strip(), parts[1].strip()
            tags = parts[2].strip() if len(parts) > 2 else ""
            sha = parts[3].strip() if len(parts) > 3 else ""
            if not gname or not local:
                raise UsageError(f"{path}:{lineno} 有空字段：{line!r}")
            if " " in gname:
                raise UsageError(
                    f"{path}:{lineno} guest_name 含空格（{gname!r}）—— "
                    f"QGA 传引号是坏的，含空格路径无法执行")
            if gname in seen:
                raise UsageError(f"{path}:{lineno} guest_name 重复：{gname!r} "
                                 f"（会互相覆盖 guest 内文件）")
            seen.add(gname)
            if not os.path.isfile(local):
                raise UsageError(f"{path}:{lineno} 样本文件不存在：{local}")
            out.append({"guest_name": gname, "local_path": local,
                        "tags": tags, "sha256_declared": sha,
                        "lineno": lineno})
    if not out:
        raise UsageError(f"清单里没有样本：{path}")
    return out


# --------------------------------------------------------------------------
# 执行
# --------------------------------------------------------------------------


def run_one(s: dict, outdir: str, *, network: str, workdir: str | None,
            timeout: int, connect: str, domain: str) -> dict:
    """跑一个样本。**任何异常都转成结果字典，不向上抛**（失败不阻塞）。"""
    stem = os.path.splitext(s["guest_name"])[0]
    out_json = os.path.join(outdir, f"{stem}.json")
    out_log = os.path.join(outdir, f"{stem}.log")

    argv = [sys.executable, COLLECT,
            "--sample", s["local_path"],
            "--guest-name", s["guest_name"],
            "--output", out_json,
            "--network", network,
            "--timeout", str(timeout),
            "--domain", domain,
            "--connect", connect]
    if workdir:
        argv += ["--workdir", workdir]

    rec = {"guest_name": s["guest_name"], "local_path": s["local_path"],
           "tags": s["tags"], "output": out_json, "log": out_log,
           "argv": argv[1:], "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    t0 = time.monotonic()
    try:
        with open(out_log, "w", encoding="utf-8") as lf:
            lf.write("$ " + " ".join(argv) + "\n\n")
            lf.flush()
            p = subprocess.run(argv, stdout=lf, stderr=subprocess.STDOUT,
                               timeout=timeout + 600)
        rec["exit_code"] = p.returncode
    except subprocess.TimeoutExpired:
        rec["exit_code"] = 124
        rec["error"] = f"batch 级超时（{timeout + 600}s）"
    except Exception as e:  # noqa: BLE001 —— 失败不阻塞是硬要求
        rec["exit_code"] = 125
        rec["error"] = f"{type(e).__name__}: {e}"
    rec["batch_wall_ms"] = int((time.monotonic() - t0) * 1000)

    # ---- 取回指纹里的关键事实（缺了就如实留空，不猜）----
    rec["ok"] = False
    if os.path.isfile(out_json):
        try:
            with open(out_json, encoding="utf-8") as f:
                fp = json.load(f)
            rb = fp.get("rollback") or {}
            fs = fp.get("filesystem") or {}
            nw = fp.get("network") or {}
            rec.update({
                "ok": rec.get("exit_code") == 0,
                "schema_version": fp.get("schema_version"),
                "script_sha256": (fp.get("script") or {}).get("sha256"),
                "guest_path": (fp.get("script") or {}).get("guest_path"),
                "exit_code_guest": (fp.get("execution") or {}).get("exit_code"),
                "exec_timeout": (fp.get("execution") or {}).get("timeout"),
                "exec_ms": (fp.get("execution") or {}).get("duration_ms"),
                "cycle_ms": rb.get("cycle_ms"),
                "total_ms": (fp.get("timings") or {}).get("total_ms"),
                "revert_op_ms": rb.get("revert_op_ms"),
                "agent_ready_ms": rb.get("agent_ready_ms"),
                "base_intact": (rb.get("base_intact") or {}).get("unchanged"),
                "baseline_manifest_hash": fs.get("baseline_manifest_hash"),
                "created": fs.get("created") or [],
                "modified": fs.get("modified") or [],
                "deleted": fs.get("deleted") or [],
                "created_dirs": fs.get("created_dirs") or [],
                "deleted_dirs": fs.get("deleted_dirs") or [],
                "network_mode": nw.get("mode"),
                "network_isolated": nw.get("isolated"),
                "egress_frames": nw.get("egress_frames"),
                "network_connections": len(nw.get("connections") or []),
                # v4 指纹才有 fixed_time；v3 指纹如实留 None（不假装跑在固定时间上）
                "fixed_time_ok": (fp.get("fixed_time") or {}).get("ok"),
                "fixed_time_offset_s": (fp.get("fixed_time") or {}).get("after_offset_s"),
                "stdout_head": ((fp.get("stdout") or {}).get("text") or "")[:400],
                "notes": fp.get("notes") or [],
            })
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"指纹解析失败：{type(e).__name__}: {e}"
    else:
        rec["error"] = rec.get("error") or "未产出指纹文件（collect.py 提前失败）"
    return rec


# --------------------------------------------------------------------------
# 汇总与验证
# --------------------------------------------------------------------------


def verify(records: list[dict], *, net_mode: str) -> dict:
    """批量级验证（任务书 §2.3 的四条判据）。"""
    done = [r for r in records if r.get("ok")]
    failed = [r for r in records if not r.get("ok")]

    # 判据 1：全部完成
    v1 = {"name": "全部完成", "pass": len(failed) == 0,
          "detail": f"{len(done)}/{len(records)} 成功"}

    # 判据 2：样本独立 —— J1（起点同一状态）
    hashes = {r.get("baseline_manifest_hash") for r in done}
    hashes.discard(None)
    j1 = len(hashes) == 1
    v2 = {"name": "样本独立(J1 起点哈希一致)", "pass": bool(j1 and len(done) > 1),
          "detail": (f"baseline_manifest_hash 取值 {len(hashes)} 种："
                     f"{sorted(hashes)[:3]}")}

    # 判据 3：网络隔离保持（每个样本都必须 0 出网帧）
    leaks = [r for r in done
             if r.get("egress_frames") not in (0,) or r.get("network_isolated") is not True]
    v3 = {"name": "网络隔离保持(无意外出网)", "pass": len(leaks) == 0,
          "detail": (f"{len(done) - len(leaks)}/{len(done)} 个样本 egress_frames=0"
                     if not leaks else
                     "泄漏：" + ", ".join(f"{r['guest_name']}({r.get('egress_frames')})"
                                         for r in leaks))}

    # 判据 4：时间可接受（平均 < 60s/样本，用 cycle_ms；缺则用 batch_wall_ms）
    cycles = [r["cycle_ms"] for r in done if r.get("cycle_ms")]
    avg_cycle = (sum(cycles) / len(cycles)) if cycles else None
    walls = [r["batch_wall_ms"] for r in records if r.get("batch_wall_ms")]
    avg_wall = (sum(walls) / len(walls)) if walls else None
    v4 = {"name": "时间可接受(平均 < 60s/样本)", "pass":
          (avg_cycle is not None and avg_cycle < 60000),
          "detail": (f"平均 cycle {avg_cycle/1000:.1f}s，"
                     f"平均 wall {avg_wall/1000:.1f}s" if avg_cycle else "无计时数据")}

    # 附加：基线完整性（隔离的前提）
    bad_base = [r["guest_name"] for r in done if r.get("base_intact") is not True]
    v5 = {"name": "基线未被写入(base 完整性)", "pass": len(bad_base) == 0,
          "detail": "全部 base_intact=true" if not bad_base else f"异常：{bad_base}"}

    checks = [v1, v2, v3, v4, v5]
    return {"checks": checks, "pass": all(c["pass"] for c in checks),
            "requested_network_mode": net_mode}


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="batch.py",
        description="批量采集：对清单里每个样本跑一遍完整的 collect.py 流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("示例：\n"
                "  python3 batch.py --samples batch-samples.txt --output results/\n"
                "  python3 batch.py --samples batch-samples.txt --output results/ --only s03,s04\n"
                "  python3 batch.py --samples batch-samples.txt --output results/ --resume\n"))
    ap.add_argument("--samples", required=True, help="样本清单（TSV；见 batch-samples.txt）")
    ap.add_argument("--output", required=True, help="结果目录（不存在则创建）")
    ap.add_argument("--network", default="isolated",
                    choices=["isolated", "recording", "nat"],
                    help="网络姿态（默认 isolated；批量**不应**用 nat）")
    ap.add_argument("--workdir", default=r"C:\poc\samples",
                    help=r"guest 内工作目录（默认 C:\poc\samples，必须在 scope 内）")
    ap.add_argument("--no-workdir", action="store_true")
    ap.add_argument("--timeout", type=int, default=120,
                    help="单样本 guest 内执行超时秒数（默认 120）")
    ap.add_argument("--domain", default="win-behavior")
    ap.add_argument("--connect", default="qemu:///system")
    ap.add_argument("--only", default=None,
                    help="只跑指定 guest_name（逗号分隔，如 s03,s04）")
    ap.add_argument("--limit", type=int, default=0, help="最多跑前 N 个（0=全部）")
    ap.add_argument("--resume", action="store_true",
                    help="跳过已经产出指纹的样本（断点续跑）")
    args = ap.parse_args(argv)

    try:
        samples = parse_samples(args.samples)
    except UsageError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 4

    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        samples = [s for s in samples
                   if s["guest_name"] in want
                   or os.path.splitext(s["guest_name"])[0] in want]
        if not samples:
            print(f"❌ --only {args.only} 没有匹配到任何样本", file=sys.stderr)
            return 4
    if args.limit:
        samples = samples[:args.limit]
    if args.resume:
        before = len(samples)
        samples = [s for s in samples
                   if not os.path.isfile(os.path.join(
                       args.output, os.path.splitext(s["guest_name"])[0] + ".json"))]
        print(f"--resume：跳过 {before - len(samples)} 个已有指纹的样本")

    os.makedirs(args.output, exist_ok=True)
    if args.network == "nat":
        print("⚠️  ⚠️  --network=nat：批量会产生**不可撤回的真实出网**。" 
              "确认这是你要的。\n", file=sys.stderr)

    print(f"== batch ==", flush=True)
    print(f"  清单     : {args.samples}", flush=True)
    print(f"  样本数   : {len(samples)}", flush=True)
    print(f"  网络     : {args.network}", flush=True)
    print(f"  工作目录 : {'(不切换)' if args.no_workdir else args.workdir}", flush=True)
    print(f"  结果目录 : {os.path.abspath(args.output)}", flush=True)
    print(flush=True)

    records: list[dict] = []
    t_batch0 = time.monotonic()
    for i, s in enumerate(samples, 1):
        stem = os.path.splitext(s["guest_name"])[0]
        print(f"--- [{i}/{len(samples)}] {stem}  {os.path.basename(s['local_path'])}",
              flush=True)
        if s["tags"]:
            print(f"      tags: {s['tags']}", flush=True)
        rec = run_one(s, args.output, network=args.network,
                      workdir=None if args.no_workdir else args.workdir,
                      timeout=args.timeout, connect=args.connect, domain=args.domain)
        records.append(rec)
        status = "ok  " if rec.get("ok") else f"FAIL(rc={rec.get('exit_code')})"
        bits = []
        if rec.get("cycle_ms"):
            bits.append(f"cycle={rec['cycle_ms'] / 1000:.1f}s")
        if rec.get("created"):
            bits.append(f"created={len(rec['created'])}")
        if rec.get("created_dirs"):
            bits.append(f"dirs={len(rec['created_dirs'])}")
        if rec.get("network_isolated") is not None:
            bits.append(f"iso={rec['network_isolated']} fr={rec.get('egress_frames')}")
        if rec.get("exit_code_guest") is not None:
            bits.append(f"guest_rc={rec['exit_code_guest']}")
        print(f"      [{status}] {'  '.join(bits)}", flush=True)
        if not rec.get("ok"):
            print(f"      error: {rec.get('error')}", flush=True)
            print(f"      log  : {rec.get('log')}", flush=True)
        print(flush=True)

    wall = time.monotonic() - t_batch0
    v = verify(records, net_mode=args.network)
    summary = {
        "harness": {"tool": "batch.py", "version": "1.0.0",
                    "samples_file": os.path.abspath(args.samples),
                    "requested_network": args.network,
                    "workdir": None if args.no_workdir else args.workdir,
                    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
        "counts": {"total": len(records),
                   "ok": sum(1 for r in records if r.get("ok")),
                   "failed": sum(1 for r in records if not r.get("ok"))},
        "wall_ms": int(wall * 1000),
        "verification": v,
        "records": records,
    }
    sp = os.path.join(args.output, "batch-summary.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("== 汇总 ==", flush=True)
    print(f"  完成     : {summary['counts']['ok']}/{summary['counts']['total']}", flush=True)
    print(f"  总墙钟   : {wall:.0f}s", flush=True)
    for c in v["checks"]:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c['detail']}",
              flush=True)
    print(f"  汇总已写入: {sp}", flush=True)
    print(f"\n  隔离/独立性复核可另跑：", flush=True)
    print(f"    python3 verify.py " +
          " ".join(os.path.join(args.output, os.path.splitext(r["guest_name"])[0] + ".json")
                   for r in records[:3]) + " …", flush=True)
    return 0 if summary["counts"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
