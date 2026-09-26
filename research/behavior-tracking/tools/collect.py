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
  5  网络策略失败（**硬失败** —— 姿态没生效会产出"看起来正常的错误数据"）
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
from net import MODES as NET_MODES, NetPolicy, NetPolicyError  # noqa: E402

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_SAMPLES = os.path.normpath(os.path.join(TOOLS_DIR, "..", "samples"))
#: v3：`network` 由**列表**改为**对象**（破坏性变更，见 network-policy.md §7 第 3 条）。
#: 旧版（v2）指纹的 `network: []` 是占位符，**不代表"没有网络行为"**。
#: v4：新增顶层 `fixed_time`（**增量**，不破坏 v3 读取方）—— 记录 guest 时钟被对齐到
#:     T0 的实测残差，见 vm-time-fix.md。v3 指纹缺此字段 ⇒ 无法声称"跑在固定时间上"。
SCHEMA_VERSION = 4
HARNESS_VERSION = "1.2.0"


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
    ap.add_argument("--workdir", default=GUEST_SAMPLES,
                    help=rf"样本的工作目录（默认 {GUEST_SAMPLES}）。"
                         rf"**必须**在某个 --scope 之内，否则样本的相对路径写入不可见。"
                         rf"实测：不设时 guest-exec 的 cwd 是 C:\Windows\System32")
    ap.add_argument("--no-workdir", action="store_true",
                    help="不切换工作目录（恢复旧行为：cwd=System32；"
                         "相对路径写入将**落在清单范围之外**）")
    ap.add_argument("--guest-name", default=None,
                    help="上传到 guest 时使用的文件名（默认沿用原名）。"
                         "**原名含空格时必须指定**：QGA 的引号转义会让 `cmd /c` 收到 "
                         r"`\"` 而失败（实测）。用它可以给语料里的中文/含空格文件名"
                         "换一个安全的 ASCII 名，原名仍记入指纹")

    ap.add_argument("--network", choices=list(NET_MODES), default="isolated",
                    help="网络姿态（默认 isolated）。"
                         "isolated=vNIC 链路 down，报文发不出去（零外部性）；"
                         "recording=接无转发的专用网络 bat2sh-rec，可记录连接尝试但出不去；"
                         "nat=接 default(NAT)，⚠️ **显式放弃隔离，外部性不可撤回**。"
                         "详见 network-policy.md")
    ap.add_argument("--capture-window", choices=["exec", "cycle"], default="exec",
                    help="嗅探窗口（默认 exec）：exec=只覆盖样本执行；"
                         "cycle=覆盖启动到执行结束（含 DHCP 等环境噪声）")

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


def run_checks(vm: Vm, *, require_agent: bool,
               dhcp_relevant: bool = True) -> list[dict]:
    """环境检查 —— 硬失败（设计 §6.4）。"""
    print("== check_env ==", flush=True)
    checks = check_env(vm, require_agent=require_agent, dhcp_relevant=dhcp_relevant)
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


def cmdline_for(guest_path: str, workdir: str | None = None) -> str:
    r"""构造 `cmd /c` 的命令串。

    `< nul` 让 stdin 处于 EOF，`pause` 立即返回（wine 预验证已证）。

    ⚠️ **本函数不再产生任何引号 —— 因为通过 QGA 传引号是坏的**（本 session 实测）：

        cmd /c echo "hello world"            → 输出 `\"hello world\"`
        cmd /c cd /d "C:\Program Files"      → rc=1 文件名、目录名或卷标语法不正确
        cmd /c ""C:\poc\x y.bat" < nul"      → rc=1 指定的网络名不再可用

    QGA 的 `guest-exec` 在拼 CreateProcess 命令行时会给参数里的 `"` **加反斜杠转义**，
    而 `cmd.exe` 不认识 `\"`（它用 `""` 转义）。结论：**含空格的路径根本无法通过
    `guest-exec` 传给 `cmd /c`**。

    所以本函数的两个调用前提由调用方**硬保证**（见 `collect()` 里的检查）：
      1. `guest_path` 不含空格（用 `--guest-name` 改名）
      2. `workdir` 不含空格
    含空格时**硬失败**而不是"尽力而为" —— 旧版会静默跑出 `rc=1`，
    看起来像"样本执行失败"，实际是**采集器的引号 bug**。

    `workdir`（Phase 2 实测驱动）：`guest-exec` 继承 qemu-ga 的工作目录 =
    **`C:\Windows\System32`**（实测）。语料绝大多数用**相对路径**（本来是被
    "在文件夹里双击"运行的），于是 `echo x>a.txt` 会写进 System32 —— 而清单范围是
    `C:\poc`，**这些文件行为完全不可见**。所以用 `cd /d <workdir> &&` 把样本放进
    一个受控且在范围内的目录里跑。命令串以 `cd` 开头（不是引号）⇒ 不触发
    `cmd /c` 的引号剥离规则。
    """
    base = f"{guest_path} < nul"
    if workdir:
        return f"cd /d {workdir} && {base}"
    return base


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
    # `--guest-name`：QGA 传引号是坏的（见 cmdline_for），所以 guest 侧文件名必须无空格。
    # 语料里的中文名/含空格名在这里换成安全的 ASCII 名；**原名与 sha256 仍进指纹**。
    guest_name = args.guest_name or name
    guest_path = GUEST_SAMPLES + "\\" + guest_name
    workdir = None if args.no_workdir else args.workdir
    for label, val in (("guest 侧样本路径", guest_path), ("workdir", workdir or "")):
        if " " in val:
            raise SystemExit(
                f"用法错误：{label} 含空格 → `{val}`\n"
                f"  QGA 的 `guest-exec` 会给参数里的引号加反斜杠转义，而 cmd.exe 不认 `\\\"`，\n"
                f"  所以**含空格路径无法通过 guest-exec 传给 cmd /c**（本 session 实测）。\n"
                f"  解决：用 --guest-name 指定一个不含空格的 guest 侧文件名，"
                f"或把样本放到不含空格的路径下。")
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
            "guest_name": guest_name,
            "renamed": guest_name != name,
        },
        "environment": {}, "rollback": {}, "execution": {},
        "stdout": {}, "stderr": {},
        "filesystem": {}, "process": [], "network": {},
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
        fp["env_checks"] = run_checks(vm, require_agent=vm.is_running(),
                                      dhcp_relevant=(args.network != "isolated"))
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

    # ---- 2.5 网络姿态（**必须在冷启动之前**，network-policy.md §7 第 2 条）----
    net = NetPolicy(vm, args.network)
    if args.no_start or args.no_revert:
        # 调试路径：域可能正在运行，改域定义会引入竞态 ⇒ 拒不声称隔离
        net_applied = False
        print(f"== network == ⚠️ **未施加**（--no-start/--no-revert）："
              f"请求 {args.network}，但无法保证生效\n", flush=True)
        fp["notes"].append(
            f"network policy NOT applied (requested={args.network}); "
            f"isolation NOT claimed")
    else:
        print(f"== network == mode={args.network}", flush=True)
        clk.tic("network_apply")
        st = net.apply()
        clk.toc("network_apply")
        net_applied = True
        print(f"  {st['before']['network']}/{st['before']['link_state']} → "
              f"{st['after']['network']}/{st['after']['link_state']}  "
              f"bridge={st['bridge']}", flush=True)
        if args.network == "nat":
            print("  ⚠️ **nat 模式：外部性真实存在，出网不可撤回**", flush=True)

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

    # ---- 3.5 固定 guest 时间（见 vm-time-fix.md）----
    # 必须在**任何行为观测之前**：`%date%`/`%time%` 依赖样本（如 `md %date%`）与
    # 文件时间戳都要求起点时间固定，否则指纹随真实日历漂移。
    # ⚠️ 只靠域 XML 的 `<clock offset='absolute'>` **不够**：Windows 会拒绝比"上次已知时间"
    #    早很多的 RTC 值（实测 2026-06-01 被拒、2026-10-01 被接受）。这里是硬保证。
    print("== fixed time ==", flush=True)
    clk.tic("fixed_time")
    ft = qga.enforce_fixed_time()
    clk.toc("fixed_time")
    fp["fixed_time"] = ft
    print(f"  T0 = {ft['target_utc']} == guest 本地 {ft['target_local']}  "
          f"({ft['action']}，残差 {ft['after_offset_s']:+.3f}s)", flush=True)
    print(flush=True)

    # recording 模式：`forward mode='none'` 下 libvirt **不通告默认网关**，
    # guest 有 IP 却没有默认路由 ⇒ 样本连"尝试"都发不出（假阴性）。
    # 这里补一条默认路由 + 一个 DNS 地址；安全性由"无 NAT 规则"保证（net.py 有详解）。
    if net_applied and args.network == "recording":
        print("== network: guest egress ==", flush=True)
        clk.tic("guest_egress")
        ge = net.configure_guest_egress()
        clk.toc("guest_egress")
        print(f"  ifIndex={ge['guest_ifindex']} gw={ge['requested_gateway']} "
              f"route_ok={ge['route_ok']} dns_ok={ge['dns_ok']}", flush=True)

    # `cycle` 窗口：覆盖启动→执行（会把 DHCP 等**环境噪声**一起记进指纹）
    if net_applied and args.capture_window == "cycle":
        r = net.start_capture()
        fp["notes"].append(f"capture window = cycle (含启动期环境噪声); "
                           f"sniffer ready in {r['ready_ms']} ms")

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
    before_dirs = qga.dirs(scopes)
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
    cl = cmdline_for(guest_path, workdir)
    fp["execution_workdir"] = workdir
    if workdir:
        # 工作目录必须在清单范围内，否则样本的相对路径写入**看不见**
        in_scope = any(workdir.lower().startswith(s.lower().rstrip("\\") + "\\")
                       or workdir.lower() == s.lower().rstrip("\\") for s in scopes)
        if not in_scope:
            fp["notes"].append(
                f"⚠️ workdir {workdir} 不在任何 --scope {scopes} 之内 —— "
                f"样本的相对路径写入将不可见")
            print(f"  ⚠️ workdir {workdir} **不在清单范围** {scopes} 内 —— "
                  f"相对路径写入不可见", flush=True)
    timed_out = False
    # 嗅探窗口：**紧贴执行**。就绪握手保证不漏掉最早的帧（netsniff.py 实测坑）。
    if net_applied and args.capture_window == "exec":
        r = net.start_capture()
        print(f"  嗅探已就绪 {r['ready_ms']} ms (iface={r['iface']})", flush=True)
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
    finally:
        if net_applied:
            clk.tic("capture")
            cap = net.stop_capture()
            clk.toc("capture")

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

    # ---- 7.5 网络指纹（network-policy.md §4.1）----
    if net_applied:
        nf = net.fingerprint()
        nf["setup"] = net.setup
        fp["network"] = nf
        print("== network fingerprint ==", flush=True)
        print(f"  mode={nf['mode']} isolated={nf['isolated']} "
              f"method={nf['isolation_method']}", flush=True)
        print(f"  attempted={nf['attempted']}  "
              f"egress_frames={nf['egress_frames']}  "
              f"bytes_sent={nf['bytes_sent']} bytes_recv={nf['bytes_recv']}", flush=True)
        for c in nf["connections"][:20]:
            print(f"    [{c['first_seen_ms']:>7}ms] {c['proto']:5s} "
                  f"{c['dst']:<28s} {c['result']}", flush=True)
        if len(nf["connections"]) > 20:
            print(f"    … 另有 {len(nf['connections']) - 20} 条", flush=True)
        for n in nf["notes"]:
            print(f"  note: {n}", flush=True)
        print(flush=True)
    else:
        fp["network"] = {
            "mode": args.network, "isolated": False, "applied": False,
            "isolation_method": None,
            "attempted": None,
            "attempted_basis": "网络姿态未施加 —— **不声称任何隔离**",
            "connections": [], "bytes_sent": 0, "bytes_recv": 0,
            "egress_frames": None,
            "notes": ["⚠️ --no-start/--no-revert 调试路径：网络隔离**不成立**"],
        }

    # ---- 8. 事后清单 + 差分（判据 J2：保留绝对清单）----
    print("== after manifest ==", flush=True)
    clk.tic("after_manifest")
    after = qga.manifest(scopes)
    after_dirs = qga.dirs(scopes)
    clk.toc("after_manifest")
    d = diff(before, after)
    created_dirs = sorted(set(after_dirs) - set(before_dirs))
    deleted_dirs = sorted(set(before_dirs) - set(after_dirs))
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
        # 目录行为（**不进 J1 哈希**，见 vm.dirs() 的说明）：
        # `md` 类样本若只看文件差分会被误判成"什么都没做"
        "dirs_method": "recurse-directory-listing",
        "baseline_dirs": before_dirs,
        "after_dirs": after_dirs,
        "created_dirs": created_dirs,
        "deleted_dirs": deleted_dirs,
        # 判据 J3 的素材：created 非空即证明本样本**确实有效**
        "blind_spots": ["reads", "transient-effects", "metadata-only-writes",
                        "cwd-if-workdir-unset"],
    }
    print(f"  created  = {created_behav}", flush=True)
    print(f"  modified = {modified_behav}", flush=True)
    print(f"  deleted  = {d['deleted']}", flush=True)
    print(f"  created_dirs = {created_dirs}", flush=True)
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
    print(f"  network     : mode={fp['network'].get('mode')} "
          f"isolated={fp['network'].get('isolated')} "
          f"egress_frames={fp['network'].get('egress_frames')} "
          f"conns={len(fp['network'].get('connections') or [])}", flush=True)
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
    except NetPolicyError as e:
        print(f"\n❌ 网络策略失败（**拒绝继续**，否则指纹会静默失真）：\n{e}",
              file=sys.stderr)
        return 5
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
