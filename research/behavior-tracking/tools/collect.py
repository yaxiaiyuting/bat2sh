#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bat2sh 行为采集 —— CLI 入口

一条命令跑完：**回滚 → 等 agent → 传输 → 执行 → 采集 → 报告**

    python3 collect.py --sample samples/copy.bat --output results/copy.json

设计依据：`research/behavior-tracking/rollback-design.md`
  §6.1 目标循环 / §6.2 状态机 / §6.3 必查清单 / §6.4 环境检查必须硬失败 / §7.3 采集器产物归属

退出码：
  0  采集成功
  1  环境检查失败（**硬失败**，不降级）
  2  VM / 宿主层故障
  3  Guest / QGA 层故障
  4  用法错误
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vm import (  # noqa: E402
    DEFAULT_CONN, DEFAULT_DOMAIN, DEFAULT_SCOPE, GUEST_SAMPLES,
    EnvCheckError, GuestError, Qga, Vm, VmError,
    check_env, decode, diff, manifest_hash, sha256_file,
)

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_SAMPLES = os.path.normpath(os.path.join(TOOLS_DIR, "..", "samples"))
SCHEMA_VERSION = 2
HARNESS_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# 路径解析
# --------------------------------------------------------------------------


def resolve_input(path: str) -> str:
    """解析 `--sample` / `--output` 的相对路径。

    依次尝试：**cwd → tools/ → tools/samples/ → ../samples/**。
    这样两条被文档化的调用都成立：
        cd research/behavior-tracking/tools && python3 collect.py --sample samples/copy.bat
        cd research/behavior-tracking       && python3 tools/collect.py --sample samples/copy.bat
    """
    if os.path.isabs(path):
        return path
    for cand in (os.path.join(os.getcwd(), path),
                 os.path.join(TOOLS_DIR, path),
                 os.path.join(TOOLS_DIR, "samples", path),
                 os.path.join(REPO_SAMPLES, path)):
        if os.path.exists(cand):
            return os.path.normpath(cand)
    return os.path.normpath(os.path.join(os.getcwd(), path))


def resolve_output(path: str) -> str:
    """输出路径不做存在性搜索（文件还不存在）—— 相对 cwd 解析。"""
    return path if os.path.isabs(path) else os.path.abspath(path)


def normalize_scopes(raw) -> list[str]:
    """把 `--scope`（可重复 / 逗号分隔）规范化成去重有序列表。

    None ⇒ 默认 `[DEFAULT_SCOPE]`。（不能把 `default=DEFAULT_SCOPE` 配 `action="append"`：
    argparse 会去 append 那个 str，直接 AttributeError。）
    """
    if raw is None:
        return [DEFAULT_SCOPE]
    out: list[str] = []
    for item in (raw if isinstance(raw, list) else [raw]):
        for part in str(item).split(","):
            p = part.strip()
            if p and p not in out:
                out.append(p)
    return out


class Clock:
    """分段计时 —— `cycle_ms` 是批量吞吐的头号指标，必须能拆开看是谁慢。"""

    def __init__(self):
        self.marks: dict[str, int] = {}
        self._t: dict[str, float] = {}

    def tic(self, key: str):
        self._t[key] = time.monotonic() * 1000.0

    def toc(self, key: str) -> int:
        ms = int(time.monotonic() * 1000.0 - self._t.pop(key))
        self.marks[key] = ms
        return ms


def git_head() -> str | None:
    """锁定 HEAD（纪律 #4）。"""
    try:
        import subprocess
        p = subprocess.run(["git", "-C", TOOLS_DIR, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=15)
        return (p.stdout or "").strip() or None if p.returncode == 0 else None
    except Exception:
        return None


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="collect.py",
        description="bat2sh 行为采集：回滚 → 等 agent → 传输 → 执行 → 采集 → 报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python3 collect.py --sample samples/copy.bat --output results/copy.json\n"
            "  python3 collect.py --sample samples/other.bat --output results/other.json\n"
            "  python3 collect.py --establish-baseline          # 一次性：冻结当前盘为基线\n"
            "  python3 collect.py --sample samples/copy.bat --no-revert   # 调试：跳过回滚\n"))
    ap.add_argument("--sample", help="样本 .bat 路径（相对路径按 cwd→tools→samples 解析）")
    ap.add_argument("--output", help="指纹输出 .json 路径（相对 cwd）")

    ap.add_argument("--domain", default=DEFAULT_DOMAIN)
    ap.add_argument("--connect", default=DEFAULT_CONN, dest="conn",
                    help=f"libvirt URI（默认 {DEFAULT_CONN}；注意默认 URI 是 session）")
    ap.add_argument("--scope", default=None, action="append",
                    help=rf"guest 内清单递归范围；可重复或用逗号分隔（默认 {DEFAULT_SCOPE}）。"
                         rf"把探针目录放在 C:\poc 之外可验证**整盘**回滚")
    ap.add_argument("--timeout", type=int, default=180,
                    help="guest 内样本执行超时秒数（默认 180；超时**记录并继续**）")

    ap.add_argument("--no-revert", action="store_true",
                    help="跳过回滚（调试用；**会破坏样本间隔离**）")
    ap.add_argument("--no-start", action="store_true",
                    help="不启动域（假定已在运行）")
    ap.add_argument("--keep-running", action="store_true",
                    help="采集后不停机（调试用）")
    ap.add_argument("--stop-mode", choices=["destroy", "shutdown"], default="destroy",
                    help="停机方式（默认 destroy 硬断电；脏状态只落被丢弃的覆盖层）")
    ap.add_argument("--settle-ms", type=int, default=0,
                    help="agent 就绪后额外静置毫秒数（默认 0）。实测：settle=0 总周期更短"
                         "（agent就绪→首清单 ~21s），settle=15000 更稳（~35s，次清单 2.4s "
                         "vs 11.8s 的抖动）。需要时序稳定时再开。见 rollback-result.md §5")
    ap.add_argument("--skip-env-check", action="store_true",
                    help="⚠️ 跳过环境检查（会产生**看起来正常但错误**的数据，见设计 §6.4）")

    ap.add_argument("--establish-baseline", action="store_true",
                    help="一次性：把当前关机状态的磁盘冻结为 base 并生成覆盖层")
    ap.add_argument("--force", action="store_true",
                    help="配合 --establish-baseline：覆盖已有基线")
    return ap


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def run_checks(vm: Vm, *, require_agent: bool) -> list[dict]:
    """环境检查 —— 硬失败（设计 §6.4）。"""
    print("== check_env ==", flush=True)
    checks = check_env(vm, require_agent=require_agent)
    bad = []
    for c in checks:
        mark = "ok  " if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['check']}: {c['detail']}", flush=True)
        if not c["ok"]:
            bad.append(c)
    if bad:
        lines = "\n".join(f"  - {c['check']}: {c['detail']}" for c in bad)
        raise EnvCheckError(
            f"环境检查未通过（{len(bad)}/{len(checks)} 项）—— **拒绝继续**。\n{lines}\n"
            f"  理由：环境故障会静默污染指纹（设计 §6.4）。修复后重跑。")
    print(f"  全部 {len(checks)} 项通过\n", flush=True)
    return checks


def cmdline_for(guest_path: str) -> str:
    r"""构造 `cmd /c` 的命令串。

    PoC §5.3：`cmd /c` 对**以引号开头**的命令串有剥离规则，路径无空格时**不加引号**；
    含空格时用 `cmd /c ""<path>" < nul"` 形式。
    `< nul` 让 stdin 处于 EOF，`pause` 立即返回（wine 预验证已证）。
    """
    if " " in guest_path:
        return f'""{guest_path}" < nul"'
    return f"{guest_path} < nul"


def collect(args) -> dict:
    vm = Vm(args.domain, args.conn)

    # ---- 一次性：建立基线（设计 §4.3）----
    if args.establish_baseline:
        print("== establish_baseline ==", flush=True)
        info = vm.establish_baseline(force=args.force)
        for k, v in info.items():
            print(f"  {k}: {v}", flush=True)
        print("\n基线已建立。**必须启动并确认 agent 就绪后**再开始采集。", flush=True)
        vm.start()
        ms = vm.wait_for_agent()
        print(f"  域已启动，agent 就绪耗时 {ms:.0f} ms  "
              f"(state={vm.channel_state()})", flush=True)
        return {"establish_baseline": info, "agent_ready_ms": ms}

    if not args.sample:
        raise SystemExit("用法错误：需要 --sample（或 --establish-baseline）")
    if not args.output:
        raise SystemExit("用法错误：需要 --output")

    sample_local = resolve_input(args.sample)
    if not os.path.isfile(sample_local):
        raise SystemExit(f"用法错误：找不到样本 {args.sample}（解析为 {sample_local}）")
    output_path = resolve_output(args.output)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    t_total0 = time.monotonic() * 1000.0
    name = os.path.basename(sample_local)
    guest_path = GUEST_SAMPLES + "\\" + name
    scopes = normalize_scopes(args.scope)
    clk = Clock()
    fp: dict = {
        "schema_version": SCHEMA_VERSION,
        "harness": {"tool": "collect.py", "version": HARNESS_VERSION,
                    "git_head": git_head(), "invocation": sys.argv[1:]},
        "script": {
            "name": name,
            "sha256": sha256_file(sample_local),
            "size": os.path.getsize(sample_local),
            "local_path": sample_local,
            "guest_path": guest_path,
        },
        "environment": {}, "rollback": {}, "execution": {},
        "stdout": {}, "stderr": {},
        "filesystem": {}, "process": [], "network": [],
        "timings": {}, "notes": [],
    }

    # ---- 1. 环境检查（硬失败）----
    if args.skip_env_check:
        print("== check_env == ⚠️ **已跳过**（--skip-env-check）—— "
              "结果可能含静默错误，见设计 §6.4\n", flush=True)
        fp["notes"].append("env check SKIPPED by --skip-env-check")
        fp["env_checks"] = []
    else:
        clk.tic("env_check")
        fp["env_checks"] = run_checks(vm, require_agent=vm.is_running())
        clk.toc("env_check")

    # ---- 2. 回滚 ----
    if args.no_revert:
        print("== revert == ⚠️ **已跳过**（--no-revert）—— 样本间隔离**不成立**\n", flush=True)
        fp["rollback"] = {"skipped": True,
                          "warning": "sample-to-sample isolation NOT established"}
        fp["notes"].append("rollback SKIPPED by --no-revert")
    else:
        print("== revert ==", flush=True)
        clk.tic("revert")
        rb = vm.revert(stop_mode=args.stop_mode)
        clk.toc("revert")
        print(f"  停机({rb['stop_mode']}) {rb.get('stop_ms', 0)} ms", flush=True)
        print(f"  **纯回滚操作 revert_op_ms = {rb['revert_op_ms']} ms**  "
              f"(判据 < 30000 ms)", flush=True)
        fp["rollback"] = rb

    # ---- 3. 启动 + 等 agent（轮询，非 sleep）----
    t_cycle0 = time.monotonic() * 1000.0
    if not args.no_start:
        print("== boot ==", flush=True)
        clk.tic("agent_wait")
        if not vm.is_running():
            vm.start()
        ms = vm.wait_for_agent()
        clk.toc("agent_wait")
        print(f"  agent 就绪 {ms:.0f} ms  (state={vm.channel_state()})", flush=True)
        fp["rollback"]["agent_ready_ms"] = round(ms)
        if args.settle_ms > 0:
            time.sleep(args.settle_ms / 1000.0)
            fp["rollback"]["settle_ms"] = args.settle_ms
    else:
        fp["rollback"]["agent_ready_ms"] = None
        print("== boot == 已跳过（--no-start）", flush=True)

    qga = vm.qga

    # ---- 4. 环境快照 ----
    print("== environment ==", flush=True)
    clk.tic("environment")
    try:
        oi = qga.osinfo()
        fp["environment"] = {
            "guest_os": oi.get("pretty-name"), "guest_version": oi.get("version"),
            "kernel_release": oi.get("kernel-release"), "machine": oi.get("machine"),
        }
        ai = qga.agent_info()
        fp["environment"]["guest_agent_version"] = ai.get("version")
        fp["environment"]["guest_agent_commands"] = len(ai.get("supported_commands", []))
    except GuestError as e:
        fp["notes"].append(f"osinfo/agent-info 失败：{e}")

    cp = qga.codepage()
    clk.toc("environment")
    fp["environment"]["console_codepage"] = cp
    for k, v in fp["environment"].items():
        print(f"  {k}: {v}", flush=True)
    print(flush=True)

    # ---- 5. 基线清单（判据 J1）----
    # ⚠️ **必须在 upload 之前**：否则清单会把采集器自己刚上传的样本算进去，
    # 导致两次运行的 baseline_manifest_hash **必然不同**（J1 失效）。
    # 本工具第一版就踩了这个 —— 是 J1 判据自己把它抓出来的（见 rollback-result.md）。
    print("== baseline manifest ==", flush=True)
    clk.tic("baseline_manifest")
    before = qga.manifest(scopes)
    clk.toc("baseline_manifest")
    bh = manifest_hash(before)
    print(f"  {len(before)} 项，baseline_manifest_hash = {bh}", flush=True)
    print(flush=True)

    # ---- 6. 传输 ----
    print("== upload ==", flush=True)
    clk.tic("upload")
    n = qga.write_file(guest_path, sample_local)
    clk.toc("upload")
    print(f"  {n} 字节 → {guest_path}", flush=True)
    print(flush=True)

    # ---- 7. 执行 ----
    print("== execute ==", flush=True)
    cl = cmdline_for(guest_path)
    timed_out = False
    clk.tic("execute")
    try:
        res = qga.exec_wait("cmd.exe", ["/c", cl], timeout=args.timeout)
    except TimeoutError as e:
        # 超时是**要记录的行为**，不是基础设施故障（设计 §6.2）
        timed_out = True
        fp["notes"].append(f"execution timeout after {args.timeout}s: {e}")
        print(f"  ⚠️ 执行超时（{args.timeout}s）—— 记录为行为，继续采集", flush=True)
        res = {"argv": ["cmd.exe", "/c", cl], "pid": None,
               "duration_ms": args.timeout * 1000, "exit_code": None, "signal": None,
               "out_truncated": False, "err_truncated": False,
               "stdout_b64": "", "stderr_b64": ""}

    clk.toc("execute")
    fp["execution"] = {
        "argv": res["argv"], "pid": res["pid"], "duration_ms": res["duration_ms"],
        "exit_code": res["exit_code"], "signal": res["signal"],
        "timeout": timed_out,
        "out_truncated": res["out_truncated"], "err_truncated": res["err_truncated"],
    }
    fp["stdout"] = {"b64": res["stdout_b64"], "text": decode(res["stdout_b64"], cp or 936)}
    fp["stderr"] = {"b64": res["stderr_b64"], "text": decode(res["stderr_b64"], cp or 936)}
    print(f"  exit_code = {res['exit_code']}  signal = {res['signal']}  "
          f"duration_ms = {res['duration_ms']}", flush=True)
    print(f"  out_truncated = {res['out_truncated']}  "
          f"err_truncated = {res['err_truncated']}", flush=True)
    print(f"  stdout = {fp['stdout']['text']!r}", flush=True)
    print(f"  stderr = {fp['stderr']['text']!r}", flush=True)
    print(flush=True)

    # ---- 8. 事后清单 + 差分（判据 J2：保留绝对清单）----
    print("== after manifest ==", flush=True)
    clk.tic("after_manifest")
    after = qga.manifest(scopes)
    clk.toc("after_manifest")
    d = diff(before, after)
    print(f"  {len(after)} 项", flush=True)

    # 采集器自身写入的产物与**行为**产物分离（设计 §7.3：分离是为了可读，不是隐藏）
    known = [guest_path]
    known_hit = [p for p in known if p in after]
    created_behav = [p for p in d["created"] if p not in known]
    modified_behav = [p for p in d["modified"] if p not in known]

    fp["filesystem"] = {
        "method": "manifest-diff-v2",
        "scope": scopes,
        # 判据 J1：起点是否同一状态
        "baseline_manifest_hash": bh,
        # 存档 baseline 全量：否则 J1 差异**无法复核**（哪个文件不同？）
        "baseline_manifest": before,
        "before_count": len(before), "after_count": len(after),
        # 行为产物（已剔除采集器自身写入）
        "created": created_behav, "modified": modified_behav,
        "deleted": d["deleted"], "unchanged_count": len(d["unchanged"]),
        # 分离出去的部分 + 理由（nothing hidden）
        "known_artifacts": [{"path": p, "reason": "harness upload"} for p in known_hit],
        "created_raw": d["created"],
        # 判据 J2：绝对状态（差分自归一化，必须留全量）
        "after_manifest": after,
        # 判据 J3 的素材：created 非空即证明本样本**确实有效**
        "blind_spots": ["reads", "transient-effects", "metadata-only-writes"],
    }
    print(f"  created  = {created_behav}", flush=True)
    print(f"  modified = {modified_behav}", flush=True)
    print(f"  deleted  = {d['deleted']}", flush=True)
    print(f"  known_artifacts = {known_hit}", flush=True)
    print(flush=True)

    # ---- 9. base 完整性（隔离的前提）----
    if fp["rollback"].get("base_ident_before"):
        vi = vm.verify_base_intact(fp["rollback"]["base_ident_before"])
        fp["rollback"]["base_intact"] = vi
        print(f"== base 完整性 == {'未被写入 ✅' if vi['unchanged'] else '**被写入 ❌**'}",
              flush=True)

    # ---- 10. 收尾 ----
    fp["rollback"]["cycle_ms"] = int(time.monotonic() * 1000.0 - t_cycle0) \
        if not args.no_start else None

    if not args.keep_running and not args.no_start and not args.no_revert:
        print("\n== stop ==", flush=True)
        t0 = time.monotonic() * 1000.0
        vm.destroy()
        fp["rollback"]["final_stop_ms"] = int(time.monotonic() * 1000.0 - t0)

    fp["timings"] = clk.marks
    fp["timings"]["total_ms"] = int(time.monotonic() * 1000.0 - t_total0)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(fp, f, indent=2, ensure_ascii=False, sort_keys=False)

    print(f"\n== report ==", flush=True)
    print(f"  样本        : {name}  sha256={fp['script']['sha256'][:16]}…", flush=True)
    print(f"  exit_code   : {fp['execution']['exit_code']}", flush=True)
    print(f"  stdout      : {fp['stdout']['text']!r}", flush=True)
    print(f"  created     : {created_behav}", flush=True)
    print(f"  revert_op_ms: {fp['rollback'].get('revert_op_ms')}", flush=True)
    print(f"  agent_ready : {fp['rollback'].get('agent_ready_ms')}", flush=True)
    print(f"  cycle_ms    : {fp['rollback'].get('cycle_ms')}", flush=True)
    print(f"  指纹已写入  : {output_path}", flush=True)
    print("  --- 分段计时 (ms) ---", flush=True)
    for k, v in fp["timings"].items():
        print(f"    {k:20s} {v}", flush=True)
    return fp


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        collect(args)
        return 0
    except EnvCheckError as e:
        print(f"\n❌ 环境检查失败：\n{e}", file=sys.stderr)
        return 1
    except VmError as e:
        print(f"\n❌ VM/宿主层故障：\n{e}", file=sys.stderr)
        return 2
    except GuestError as e:
        print(f"\n❌ Guest/QGA 层故障：\n{e}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\n中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
