#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bat2sh 行为采集 —— VM 原语层

职责：域状态 / 启停 / **覆盖层回滚** / QGA 通道通信 / 文件传输 / 文件系统清单与差分。

设计依据：`research/behavior-tracking/rollback-design.md`
  - §3  方案 C：独立 overlay qcow2（`qemu-img create -b base`）
  - §4.2 `wait_for_agent()` 必须**轮询** `guest-ping`，不得 `sleep N`
  - §5.1 清单差分**自归一化** → 必须记录 baseline_manifest_hash 与 after 绝对清单
  - §6.3 两个根因坑（ufw / vioser）固化为 `check_env()` 硬检查

依赖：仅标准库 + 宿主 `virsh` / `qemu-img`。
  - `virsh` 走**非 root**（用户需在 `libvirt` 组内；实测可用）
  - 镜像文件操作走 `sudo -n`（`/var/lib/libvirt/images` 为 root 所有）
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import subprocess
import time

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

DEFAULT_DOMAIN = "win-behavior"
# ⚠️ 默认 URI 是 qemu:///session，裸 `virsh` 看不到本域（实测第一坑，见 rollback-design §2）
DEFAULT_CONN = "qemu:///system"
IMAGES_DIR = "/var/lib/libvirt/images"

# 覆盖层 owner/mode：与 libvirt 自建磁盘一致（libvirt-qemu:libvirt-qemu 0600）
QEMU_OWNER = "libvirt-qemu:libvirt-qemu"
QEMU_MODE = "0600"

GUEST_ROOT = r"C:\poc"
GUEST_SAMPLES = GUEST_ROOT + r"\samples"
DEFAULT_SCOPE = GUEST_ROOT  # 递归范围：样本写哪儿都能看见

# guest-exec-status 每流上限（qga/commands.c），超出即置 truncated
GUEST_EXEC_MAX_OUTPUT = 16 * 1024 * 1024

# ---- 固定 guest 时间（`research/behavior-tracking/vm-time-fix.md`）----
# 目的：让指纹在**日历上**也可复现 —— `%date%`/`%time%`/文件时间戳/日志时间
# 都不再随真实日期漂移（语料里 s07 这类 `md %date%` 样本直接依赖它）。
#
# T0 = **guest 本地** 2026-06-01 12:00:00（Asia/Shanghai，UTC+8）= **UTC** 2026-06-01 04:00:00。
#   取值理由：晚于镜像构建时间 2026-05-20（构建号 260520-1434），且早于实测可用的 2026-09-26，
#   落在 Insider 时间炸弹的已知安全区间内。
#
# ⚠️ 两个数字**故意不同**，不是笔误：
#   · `guest-set-time` 收的是 **UTC 纪元秒** ⇒ FIXED_TIME_UTC_EPOCH。
#   · libvirt `<clock offset='absolute' start=…>` 写进 CMOS RTC，而 **Windows 把 RTC 当本地时间**读
#     ⇒ `start` 必须是"目标本地墙钟的 UTC 字面量"（2026-06-01T12:00:00Z ⇒ guest 显示 12:00）。
#   两条路径落到**同一个 guest 墙钟**（实测，见 vm-time-fix.md §3）。
FIXED_TIME_UTC_EPOCH = 1780286400          # 2026-06-01T04:00:00Z == 本地 12:00:00 (UTC+8)
FIXED_TIME_RTC_START = 1780315200          # XML start；RTC 字面量 2026-06-01T12:00:00
FIXED_TIME_LOCAL = "2026-06-01 12:00:00"   # guest 侧应看到的墙钟（Asia/Shanghai）
FIXED_TIME_UTC = "2026-06-01T04:00:00Z"
FIXED_TIME_TOLERANCE_S = 2.0               # 设置后允许的残差（QGA 往返 + 时钟粒度）


class VmError(RuntimeError):
    """VM / 宿主层故障。"""


class GuestError(RuntimeError):
    """Guest 内 / QGA 通道故障。"""


class EnvCheckError(RuntimeError):
    """前置环境检查失败 —— **必须硬失败**，不得降级继续。

    理由（rollback-design §6.4）：ufw 丢 DHCP 会让样本的网络行为**静默**变成空集，
    产生"看起来完全正常的错误数据"。
    """


# --------------------------------------------------------------------------
# 宿主命令封装
# --------------------------------------------------------------------------


def sh(argv, *, sudo: bool = False, timeout: int = 120, check: bool = True,
       text: bool = True):
    """跑一条宿主命令。

    `sudo=True` 时用 `sudo -n`（非交互）—— 无免密 sudo 会**立即失败**而不是挂住。
    """
    cmd = (["sudo", "-n"] if sudo else []) + list(argv)
    try:
        p = subprocess.run(cmd, capture_output=True, text=text, timeout=timeout)
    except FileNotFoundError as e:
        raise VmError(f"命令不存在：{cmd[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise VmError(f"命令超时（{timeout}s）：{shlex.join(cmd)}") from e
    if check and p.returncode != 0:
        err = (p.stderr or "").strip() if text else (p.stderr or b"").decode("utf-8", "replace")
        out = (p.stdout or "").strip() if text else (p.stdout or b"").decode("utf-8", "replace")
        raise VmError(
            f"命令失败 rc={p.returncode}：{shlex.join(cmd)}\n"
            f"  stderr: {err}\n  stdout: {out}")
    return p


def _now_ms() -> float:
    return time.monotonic() * 1000.0


# --------------------------------------------------------------------------
# 清单工具（模块级，便于单独测试）
# --------------------------------------------------------------------------


def manifest_hash(manifest: dict) -> str:
    """对清单算稳定指纹 —— **判据 J1**（rollback-design §5.1）。

    两次运行的 `baseline_manifest_hash` 相同 ⇒ 起点是同一状态。
    这是"隔离"最强的证据：起点相同，结果之差只能来自样本。
    """
    items = sorted(
        f"{path}\0{rec.get('Hash') or ''}\0{rec.get('Length')}"
        for path, rec in manifest.items())
    return "sha256:" + hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()


def diff(before: dict, after: dict) -> dict:
    """清单差分。

    ⚠️ **此结果不能单独用于判定隔离**（rollback-design §5.1）：
    残留文件在 before/after 中都存在且哈希相同 → 落进 `unchanged`，**差分里看不见**。
    判隔离必须同时用 `manifest_hash()`（J1）与 after 绝对清单（J2）。
    """
    created = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified = sorted(p for p in set(before) & set(after)
                      if before[p].get("Hash") != after[p].get("Hash"))
    unchanged = sorted(p for p in set(before) & set(after)
                       if before[p].get("Hash") == after[p].get("Hash"))
    return {"created": created, "modified": modified,
            "deleted": deleted, "unchanged": unchanged}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def decode(b64: str, codepage: int = 936) -> str:
    """QGA 返回的是**原始字节**的 base64 → 按控制台代码页解码（设计 §4.5）。"""
    if not b64:
        return ""
    enc = f"cp{codepage}" if codepage else "cp936"
    try:
        return base64.b64decode(b64).decode(enc, errors="replace")
    except LookupError:
        return base64.b64decode(b64).decode("cp936", errors="replace")


# --------------------------------------------------------------------------
# QGA 通道
# --------------------------------------------------------------------------


class Qga:
    """通过 `virsh qemu-agent-command` 与 guest 内 qemu-ga 通信。"""

    def __init__(self, domain: str = DEFAULT_DOMAIN, conn: str = DEFAULT_CONN,
                 timeout: int = 120):
        self.domain = domain
        self.conn = conn
        self.timeout = timeout

    def raw(self, payload: dict, timeout: int | None = None):
        """发一条 QGA 命令，返回 `return` 字段。错误原文不吞。"""
        cmd = ["virsh", "--connect", self.conn, "qemu-agent-command",
               self.domain, json.dumps(payload)]
        p = sh(cmd, timeout=timeout or self.timeout, check=False)
        out = (p.stdout or "").strip()
        if not out:
            raise GuestError(
                f"QGA 空回复 rc={p.returncode}\n  cmd: {payload.get('execute')}\n"
                f"  stderr: {(p.stderr or '').strip()}")
        try:
            d = json.loads(out)
        except json.JSONDecodeError:
            raise GuestError(f"QGA 非 JSON 回复：{out[:300]}")
        if "error" in d:
            raise GuestError(f"QGA 错误（{payload.get('execute')}）：{d['error']}")
        return d.get("return")

    # ---- 健康 ----

    def ping(self) -> bool:
        try:
            return self.raw({"execute": "guest-ping"}, timeout=20) == {}
        except Exception:
            return False

    def osinfo(self) -> dict:
        return self.raw({"execute": "guest-get-osinfo"}) or {}

    def agent_info(self) -> dict:
        return self.raw({"execute": "guest-info"}) or {}

    # ---- 时间（固定 T0）----

    def get_time(self) -> float:
        """guest 时钟，返回 **UTC 纪元秒**（QGA `guest-get-time` 的纳秒 / 1e9）。"""
        return self.raw({"execute": "guest-get-time"}) / 1e9

    def set_time(self, epoch_s: float = FIXED_TIME_UTC_EPOCH) -> None:
        """把 guest 时钟设为指定 UTC 纪元秒（QGA `guest-set-time`，纳秒）。

        这是**方向无关**的显式设置：Windows 启动时若发现 RTC 比自己的"上次已知时间"
        早很多，会**拒绝**该 RTC 值（实测，见 vm-time-fix.md §3.2），
        因此"只改 RTC"不足以把时钟拨到过去的固定点。
        """
        self.raw({"execute": "guest-set-time",
                  "arguments": {"time": int(round(epoch_s * 1e9))}})

    def enforce_fixed_time(self, *, target: float = FIXED_TIME_UTC_EPOCH,
                           tolerance_s: float = FIXED_TIME_TOLERANCE_S) -> dict:
        """把 guest 时钟对齐到 T0 并**读回验证**；失败即硬失败。

        返回 dict 进指纹（证明"这一轮确实跑在固定时间上"）。
        """
        before = self.get_time()
        before_off = before - target
        action = "already"
        if abs(before_off) > tolerance_s:
            self.set_time(target)
            action = "set"
        after = self.get_time()
        after_off = after - target
        result = {
            "target_utc": FIXED_TIME_UTC,
            "target_utc_epoch": target,
            "target_local": FIXED_TIME_LOCAL,
            "local_timezone": "Asia/Shanghai (UTC+8)",
            "rtc_start_epoch": FIXED_TIME_RTC_START,
            "action": action,
            "before_offset_s": round(before_off, 3),
            "after_offset_s": round(after_off, 3),
            "tolerance_s": tolerance_s,
            "ok": abs(after_off) <= tolerance_s,
        }
        if not result["ok"]:
            raise GuestError(
                f"固定时间失败：设置后仍偏离 {after_off:+.3f}s（容差 {tolerance_s}s）"
                f" —— 拒绝在未知时钟下采集")
        return result

    # ---- 执行 ----

    def exec_wait(self, path: str, args: list, *, timeout: int = 180,
                  poll: float = 0.3) -> dict:
        """`guest-exec` + 轮询 `guest-exec-status` 直到退出。

        返回结构化结果：退出码 / 信号 / 截断标志 / 原始 base64 输出 / 墙钟耗时。
        """
        r = self.raw({"execute": "guest-exec", "arguments": {
            "path": path, "arg": list(args), "capture-output": True}})
        pid = r["pid"]
        t0 = _now_ms()
        while True:
            st = self.raw({"execute": "guest-exec-status", "arguments": {"pid": pid}})
            if st.get("exited"):
                break
            if _now_ms() - t0 > timeout * 1000:
                # 超时**不是**基础设施故障：样本死循环是一种要记录的行为
                # （rollback-design §6.2：记录并继续，由调用方决定）
                raise TimeoutError(f"pid {pid} 在 {timeout}s 内未退出")
            time.sleep(poll)
        return {
            "argv": [path] + list(args),
            "pid": pid,
            "duration_ms": int(_now_ms() - t0),
            "exit_code": st.get("exitcode"),
            "signal": st.get("signal"),
            "out_truncated": bool(st.get("out-truncated")),
            "err_truncated": bool(st.get("err-truncated")),
            "stdout_b64": st.get("out-data") or "",
            "stderr_b64": st.get("err-data") or "",
        }

    # ---- 文件传输 ----

    def write_file(self, guest_path: str, local_path: str) -> int:
        """`guest-file-*` 上传一个本地文件，返回字节数。"""
        with open(local_path, "rb") as f:
            data = f.read()
        handle = self.raw({"execute": "guest-file-open",
                           "arguments": {"path": guest_path, "mode": "wb"}})
        try:
            off = 0
            while off < len(data):
                chunk = data[off:off + 512 * 1024]
                self.raw({"execute": "guest-file-write", "arguments": {
                    "handle": handle,
                    "buf-b64": base64.b64encode(chunk).decode()}})
                off += len(chunk)
        finally:
            try:
                self.raw({"execute": "guest-file-close", "arguments": {"handle": handle}})
            except Exception:
                pass
        return len(data)

    # ---- 清单 ----

    def manifest(self, scope=DEFAULT_SCOPE, *, timeout: int = 300) -> dict:
        """PowerShell 递归清单（含 SHA256）。

        PowerShell + `ConvertTo-Json` 而非 `dir` 解析：**结构化、与语言环境无关**，
        且哈希使内容变化可检测（PoC 已验证）。

        `scope` 可以是**多个路径**（str 或 list）—— 用于把探针目录放在 `C:\\poc` **之外**，
        从而验证的是**整盘 CoW 回滚**，而不只是"采集器自己那个目录被清理了"。

        ⚠️ **必须先 `Test-Path` 过滤不存在的路径**（实测坑，见 rollback-result.md §5）：
        `Get-ChildItem -Path` 收到不存在的路径会产生 **~30-40 秒**的固定开销
        （实测：`C:\\poc` 单独 2.7s；加上尚不存在的 `C:\\iso-probe` → 39.7s）。
        这在本场景是**必然发生**的 —— 探针目录正是被回滚掉的，每次基线清单时都不存在。
        """
        scopes = [scope] if isinstance(scope, str) else list(scope)
        ps_paths = ",".join("'" + s.replace("'", "''") + "'" for s in scopes)
        ps = (
            f"$ErrorActionPreference='SilentlyContinue';"
            f"$p=@({ps_paths}) | Where-Object {{ Test-Path -LiteralPath $_ }};"
            f"if($p){{"
            f"Get-ChildItem -Path $p -Recurse -Force -File |"
            f" Select-Object FullName,Length,"
            f"@{{n='Hash';e={{(Get-FileHash $_.FullName -Algorithm SHA256).Hash}}}} |"
            f" ConvertTo-Json -Compress"
            f"}}"
        )
        r = self.exec_wait("powershell.exe",
                           ["-NoProfile", "-NonInteractive", "-Command", ps],
                           timeout=timeout)
        raw = decode(r["stdout_b64"]).strip()
        if not raw:
            return {}
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            # 不静默吞掉：把原文带出去
            raise GuestError(f"清单 JSON 解析失败，原始输出前 500 字符：\n{raw[:500]}")
        if isinstance(obj, dict):
            obj = [obj]
        return {o["FullName"]: o for o in obj if isinstance(o, dict) and "FullName" in o}

    def dirs(self, scope=DEFAULT_SCOPE, *, timeout: int = 120) -> list[str]:
        """递归**目录**清单（只列目录，不算哈希）。

        为什么单独一个方法：`manifest()` 只收 `-File`，于是 `md`/`mkdir` 这类
        **只建目录**的样本在指纹里表现为"什么都没做" —— 一个安静的假阴性
        （`快速创建文件夹.bat`、`每天自动创建文件夹.bat` 正是这类）。

        ⚠️ 刻意**不**把它并进 `manifest()`：清单哈希是 J1 判据的基础
        （`rollback-design.md` §5.1），改变它的构成会让新旧运行的
        `baseline_manifest_hash` 不可比。目录单独记，J1 一字不动。
        """
        scopes = [scope] if isinstance(scope, str) else list(scope)
        ps_paths = ",".join("'" + s.replace("'", "''") + "'" for s in scopes)
        ps = (
            f"$ErrorActionPreference='SilentlyContinue';"
            f"$p=@({ps_paths}) | Where-Object {{ Test-Path -LiteralPath $_ }};"
            f"if($p){{"
            f"Get-ChildItem -Path $p -Recurse -Force -Directory |"
            f" Select-Object -ExpandProperty FullName | ConvertTo-Json -Compress"
            f"}}"
        )
        r = self.exec_wait("powershell.exe",
                           ["-NoProfile", "-NonInteractive", "-Command", ps],
                           timeout=timeout)
        raw = decode(r["stdout_b64"]).strip()
        if not raw:
            return []
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            raise GuestError(f"目录清单 JSON 解析失败：{raw[:300]}")
        if isinstance(obj, str):
            obj = [obj]
        return sorted(str(x) for x in obj)

    def codepage(self, *, timeout: int = 60) -> int | None:
        """程序化取得控制台代码页 —— 解码 stdout 的前提（PoC §5.4）。"""
        r = self.exec_wait("cmd.exe", ["/c", "chcp"], timeout=timeout)
        txt = decode(r["stdout_b64"]).replace("\r", " ").replace("\n", " ")
        for tok in txt.split():
            if tok.isdigit():
                return int(tok)
        return None


# --------------------------------------------------------------------------
# 域 / 覆盖层
# --------------------------------------------------------------------------


class Vm:
    """一个 libvirt 域 + 它的 qcow2 覆盖层。"""

    def __init__(self, domain: str = DEFAULT_DOMAIN, conn: str = DEFAULT_CONN,
                 images_dir: str = IMAGES_DIR):
        self.domain = domain
        self.conn = conn
        self.images_dir = images_dir
        self.qga = Qga(domain, conn)

    # ---- 路径 ----

    @property
    def disk(self) -> str:
        """域 XML 里**当前**的磁盘源路径 —— 回滚必须写回这个路径（设计 §3.3）。"""
        return self.disk_source()

    @property
    def base(self) -> str:
        return os.path.join(self.images_dir, f"{self.domain}.base.qcow2")

    # ---- 域状态 ----

    def state(self) -> str:
        p = sh(["virsh", "--connect", self.conn, "domstate", self.domain],
               check=False, timeout=30)
        if p.returncode != 0:
            raise VmError(
                f"无法查询域 '{self.domain}'（conn={self.conn}）：\n"
                f"  {(p.stderr or '').strip()}\n"
                f"  提示：默认 URI 是 qemu:///session，看不到 system 上的域 —— "
                f"必须显式 --connect qemu:///system")
        s = (p.stdout or "").strip()
        return {"运行": "running", "关闭": "shut off", "暂停": "paused",
                "paused": "paused", "running": "running",
                "shut off": "shut off"}.get(s, s)

    def is_running(self) -> bool:
        return self.state() == "running"

    def disk_source(self) -> str:
        p = sh(["virsh", "--connect", self.conn, "domblklist", self.domain,
                "--details"], timeout=30)
        for line in (p.stdout or "").splitlines():
            f = line.split()
            if len(f) >= 4 and f[1] == "disk":
                return f[3]
        raise VmError(f"域 '{self.domain}' 未找到 device=disk 的磁盘")

    def start(self) -> None:
        sh(["virsh", "--connect", self.conn, "start", self.domain], timeout=120)

    def destroy(self) -> None:
        """硬断电。设计方案 §5.2：脏状态只落**即将丢弃**的覆盖层，不污染 base。"""
        sh(["virsh", "--connect", self.conn, "destroy", self.domain], timeout=60)

    def shutdown(self, *, wait_s: int = 120) -> float:
        """优雅关机（ACPI），返回耗时 ms。仅**建立基线**时需要（设计 §4.3）。"""
        t0 = _now_ms()
        sh(["virsh", "--connect", self.conn, "shutdown", self.domain], timeout=60)
        while _now_ms() - t0 < wait_s * 1000:
            if self.state() != "running":
                return _now_ms() - t0
            time.sleep(2)
        raise VmError(f"优雅关机超时（{wait_s}s）")

    def wait_for_agent(self, *, timeout_s: int = 180, poll_s: float = 2.0) -> float:
        """轮询 `guest-ping` 直到通道就绪，返回耗时 ms。

        **必须轮询而非 sleep**（设计 §4.2）：固定 sleep 在慢启动时假失败、快启动时白等。
        """
        t0 = _now_ms()
        attempt = 0
        while _now_ms() - t0 < timeout_s * 1000:
            attempt += 1
            if self.qga.ping():
                return _now_ms() - t0
            time.sleep(poll_s)
        raise GuestError(
            f"Guest Agent 在 {timeout_s}s 内未就绪（轮询 {attempt} 次）。\n"
            f"  排查顺序（vm-setup.md §6.7）：\n"
            f"  1) dumpxml 中 org.qemu.guest_agent.0 的 state 是否为 'connected'\n"
            f"  2) guest 内 C:\\Windows\\System32\\drivers\\vioser.sys 是否存在\n"
            f"     —— 缺失则装 virtio-win-gt-x64.msi（qemu-ga 走 virtio-serial，"
            f"不是装上 MSI 就行）\n"
            f"  3) Qemu-ga 服务是否在运行")

    def channel_state(self) -> str | None:
        p = sh(["virsh", "--connect", self.conn, "dumpxml", self.domain],
               check=False, timeout=30)
        m = re.search(r"<target type='virtio' name='org\.qemu\.guest_agent\.0' "
                      r"state='([^']+)'", p.stdout or "")
        return m.group(1) if m else None

    # ---- 覆盖层 ----

    @staticmethod
    def _backing_file(path: str) -> str | None:
        p = sh(["qemu-img", "info", "-U", "--output=json", path], sudo=True, timeout=60)
        return json.loads(p.stdout or "{}").get("backing-filename")

    @staticmethod
    def _file_ident(path: str) -> dict:
        """size/mtime/inode —— 用于验证 **base 全程未被写入**（设计 §5.2 待验项）。"""
        p = sh(["stat", "-c", "%s %Y %i", path], sudo=True, timeout=30)
        size, mtime, inode = (p.stdout or "").split()
        return {"size": int(size), "mtime": int(mtime), "inode": int(inode)}

    def revert(self, *, stop_mode: str = "destroy") -> dict:
        """**回滚**：丢弃覆盖层，从 base 重建。

        返回计时与 base 完整性证据。
        `stop_mode`:
          - `destroy`（默认）硬断电，最快；脏状态落覆盖层，不污染 base（设计 §5.2）
          - `shutdown` 优雅关机；用于对照实验
        """
        out = {"method": "overlay-qcow2", "stop_mode": stop_mode}
        overlay = self.disk_source()
        base = self.base

        if not os.path.exists(base):
            raise VmError(f"基线不存在：{base}\n  先跑 --establish-baseline（设计 §4.3）")
        if os.path.abspath(overlay) == os.path.abspath(base):
            raise VmError(
                f"域仍在直接使用基线 {base} —— 回滚会破坏基线。\n"
                f"  先执行一次 --establish-baseline 建立覆盖层。")
        if self._backing_file(base) is not None:
            raise VmError(f"基线 {base} 自身有 backing file —— 它已是覆盖层，拒绝回滚")

        st = self.state()
        if st == "running":
            t0 = _now_ms()
            if stop_mode == "shutdown":
                out["stop_ms"] = int(self.shutdown())
            else:
                self.destroy()
                out["stop_ms"] = int(_now_ms() - t0)
        elif st == "paused":
            self.destroy()
            out["stop_ms"] = 0
        else:
            out["stop_ms"] = 0

        ident_before = self._file_ident(base)

        # ---- 纯回滚操作（硬判据 < 30s 测的就是这一段）----
        t0 = _now_ms()
        if os.path.exists(overlay):
            sh(["rm", "-f", overlay], sudo=True, timeout=60)
        sh(["qemu-img", "create", "-f", "qcow2", "-b", base, "-F", "qcow2", overlay],
           sudo=True, timeout=120)
        sh(["chown", QEMU_OWNER, overlay], sudo=True, timeout=30)
        sh(["chmod", QEMU_MODE, overlay], sudo=True, timeout=30)
        out["revert_op_ms"] = int(_now_ms() - t0)

        out["base_ident_before"] = ident_before
        out["overlay"] = overlay
        out["base"] = base
        return out

    def verify_base_intact(self, ident_before: dict) -> dict:
        """验证 base 在整轮之后**未被写入**（隔离的前提条件）。"""
        after = self._file_ident(self.base)
        return {
            "unchanged": after == ident_before,
            "before": ident_before,
            "after": after,
            "note": "qcow2 以只读方式打开 backing file，写入只落覆盖层",
        }

    # ---- 建立基线（一次性；设计 §4.3）----

    def establish_baseline(self, *, force: bool = False) -> dict:
        """把当前磁盘冻结为 base，并生成覆盖层。**破坏性**，需域已关机。"""
        if self.state() == "running":
            raise VmError("建立基线需要域已关机（先 `virsh shutdown`）—— 见设计 §4.3 第 5 条")
        disk = self.disk_source()
        base = self.base
        if self._backing_file(disk) is not None:
            raise VmError(f"当前磁盘 {disk} 已有 backing file，不能直接作为基线")
        if os.path.exists(base) and not force:
            raise VmError(f"基线已存在：{base}（--force 会覆盖，丢失当前基线）")

        t0 = _now_ms()
        sh(["mv", "-f", disk, base], sudo=True, timeout=60)
        sh(["qemu-img", "create", "-f", "qcow2", "-b", base, "-F", "qcow2", disk],
           sudo=True, timeout=120)
        sh(["chown", QEMU_OWNER, disk], sudo=True, timeout=30)
        sh(["chmod", QEMU_MODE, disk], sudo=True, timeout=30)
        return {"base": base, "overlay": disk,
                "establish_ms": int(_now_ms() - t0),
                "base_ident": self._file_ident(base)}


# --------------------------------------------------------------------------
# 环境检查（设计 §6.3）—— 任何一项失败都必须硬报错
# --------------------------------------------------------------------------


def _check_ufw() -> tuple[bool, str]:
    """坑 #1（vm-setup §6.6）：ufw 默认 deny(incoming)+deny(routed)，不放行 virbr0
    会导致 guest 拿不到 DHCP、没有 NAT —— 症状与"网络配置错误"难以区分。

    ⚠️ 解析陷阱（本工具实测踩到两次）：`ufw status` 与 `ufw status verbose` 的**列不同** ——
    入站规则在前者渲染为 `ALLOW`、在后者渲染为 `ALLOW IN`；而转发规则两者都是 `ALLOW FWD`。
    所以判定**不能依赖固定列顺序，也不能依赖 `ALLOW IN` 字面量**。
    """
    p = sh(["ufw", "status", "verbose"], sudo=True, check=False, timeout=30)
    if p.returncode != 0:
        return False, f"无法读取 ufw 状态：{(p.stderr or '').strip()}"
    txt = p.stdout or ""
    if "Status: active" not in txt:
        return True, "ufw 未启用（不构成风险）"
    lines = txt.splitlines()
    # 同时兼容 `ALLOW` 与 `ALLOW IN`；转发规则必须靠 `FWD` 排除掉，否则会误判为已放行入站
    has_in = any("virbr0" in ln and "ALLOW" in ln and "FWD" not in ln for ln in lines)
    has_fwd = any("virbr0" in ln and "ALLOW FWD" in ln for ln in lines)
    if has_in and has_fwd:
        return True, "virbr0 已放行（in + route）"
    missing = []
    if not has_in:
        missing.append("`ufw allow in on virbr0`")
    if not has_fwd:
        missing.append("`ufw route allow in on virbr0`")
    return False, ("ufw 未放行 virbr0，缺：" + "、".join(missing) +
                   " —— guest 会拿不到 DHCP/NAT（vm-setup.md §6.6）")


def _dhcp_drop_count() -> int | None:
    p = sh(["nft", "list", "ruleset"], sudo=True, check=False, timeout=30)
    if p.returncode != 0:
        return None
    m = re.search(r"udp dport 67\s+counter packets (\d+)", p.stdout or "")
    return int(m.group(1)) if m else None


def _check_dhcp_drops(gap_s: float = 5.0) -> tuple[bool, str]:
    """DHCP drop 计数**两次采样不增长** —— 证明放行规则真的生效（PoC §6.2 #1）。"""
    c1 = _dhcp_drop_count()
    if c1 is None:
        return True, "无法读取 nftables 计数（跳过；需 root）"
    time.sleep(gap_s)
    c2 = _dhcp_drop_count()
    if c2 is None:
        return True, "无法读取 nftables 计数（跳过）"
    if c2 == c1:
        return True, f"udp dport 67 drop 计数静止（{c1} → {c2}）"
    return False, (f"DHCP 仍在被丢弃（{c1} → {c2}，+{c2 - c1}）—— "
                   f"guest 网络会静默失效（vm-setup.md §6.6）")


def check_env(vm: Vm, *, require_agent: bool = True,
              dhcp_gap_s: float = 5.0, dhcp_relevant: bool = True) -> list[dict]:
    """采集前**必查清单**（设计 §6.3）。返回检查结果列表；调用方负责硬失败。

    `dhcp_relevant=False`（`--network=isolated`）时，DHCP 检查**没有鉴别力** ——
    链路 down ⇒ 不会有 DHCP ⇒ 丢弃计数必然静止 ⇒ 检查恒真。
    这种情况必须**如实标注**，否则会给出"通过了检查"的假安全感
    （见 `network-policy.md` §7 第 5 条）。
    """
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # 0) sudo 免密（镜像文件操作 + 网络嗅探的前提）
    p = sh(["true"], sudo=True, check=False, timeout=15)
    add("sudo(免密)", p.returncode == 0,
        "sudo -n 可用" if p.returncode == 0
        else "需要免密 sudo（镜像文件为 root 所有；嗅探需要 CAP_NET_RAW）")

    # 1) 连接 + 域（URI 坑，设计 §2）
    try:
        st = vm.state()
        add("域存在/可查询", True, f"{vm.domain} @ {vm.conn} → {st}")
    except VmError as e:
        add("域存在/可查询", False, str(e))
        return checks  # 后续检查无意义

    # 2) ufw 放行
    ok, detail = _check_ufw()
    add("ufw 放行 virbr0", ok, detail)

    # 3) DHCP drop 计数静止
    if dhcp_relevant:
        ok, detail = _check_dhcp_drops(dhcp_gap_s)
    else:
        ok, detail = True, ("**本模式下无鉴别力**：链路 down ⇒ 不会有 DHCP ⇒ "
                            "计数必然静止（恒真，不构成证据）")
    add("DHCP 未被丢弃", ok, detail)

    # 4) 基线存在且自身无 backing（否则回滚会递归）
    if os.path.exists(vm.base):
        try:
            bk = Vm._backing_file(vm.base)
            add("基线存在/无 backing", bk is None,
                f"{vm.base}" + ("" if bk is None else f" —— 却有 backing {bk}"))
        except Exception as e:
            add("基线存在/无 backing", False, f"qemu-img info 失败：{e}")
    else:
        add("基线存在/无 backing", False,
            f"基线不存在：{vm.base}（先 --establish-baseline）")

    # 5) 域磁盘 == 覆盖层（回滚写回同一路径，设计 §3.3）
    try:
        src = vm.disk_source()
        same = os.path.abspath(src) == os.path.abspath(vm.base)
        add("域磁盘非基线", not same,
            f"域磁盘 = {src}" + ("（**就是基线**，回滚会破坏基线！）" if same else ""))
    except VmError as e:
        add("域磁盘非基线", False, str(e))

    # 6/7) agent 通道
    if require_agent:
        if vm.is_running():
            ok = vm.qga.ping()
            add("guest-ping", ok, "通道就绪" if ok else
                "不通 —— 查 vioser.sys（vm-setup.md §6.7）")
            cs = vm.channel_state()
            add("agent 通道 state", cs == "connected", f"state={cs}")
        else:
            add("guest-ping", True, "域已关机（回滚前正常）")
            add("agent 通道 state", True, "域已关机（跳过）")

    return checks
