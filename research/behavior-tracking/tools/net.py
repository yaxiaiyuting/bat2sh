#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bat2sh 行为采集 —— 网络策略层

职责：把 `network-policy.md` §6 选定的三档网络姿态**施加**到域上，并在样本执行窗口内
      采集连接级网络行为，产出指纹的 `network` 字段。

三档模式（`collect.py --network=`）：
  * `isolated`（默认）—— vNIC 链路 **down**（持久 XML）。报文根本发不出去。
  * `recording`       —— 链路 up，但接在 `bat2sh-rec`（`forward mode='none'`）上。
                        **结构性无 NAT、无转发、无 DNS 上联**，且 libvirt 自带 reject
                        规则 ⇒ 连接快速失败（`refused`），不会挂到 TCP 超时。
  * `nat`             —— 接 `default`（NAT），**显式放弃隔离**，外部性真实存在。

设计依据：`research/behavior-tracking/network-policy.md`
  §3 三档语义 / §4.1 记录结构 / §4.2 result 判定 / §4.3 不记录内容 / §6 选定方案

⚠️ 三条不可动摇的约束：
  1. **默认必须是 `isolated`** —— 不给参数就是最安全的姿态。
  2. **模式必须在冷启动前施加**。链路状态/承载网络属于域定义，域在跑时改会引入竞态。
  3. **不记录 payload**。提权进程只有 `netsniff.py`，它每帧最多读 192 字节，
     解析器里没有读 payload 的代码路径（`payload_read: false` 是构造性质）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

from vm import DEFAULT_CONN, DEFAULT_DOMAIN, Vm, VmError, decode, sh

MODES = ("isolated", "recording", "nat")

DEFAULT_NET = "default"
REC_NET = "bat2sh-rec"
#: recording 网络的宿主侧网关（= `<ip address>`）。见 configure_guest_egress()。
REC_GW = "192.168.200.1"
REC_NET_XML = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "bat2sh-rec.network.xml")
NETSNIFF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "netsniff.py")

#: 嗅探器就绪超时（秒）。就绪=已 bind 成功 ⇒ 从此刻起不会漏帧。
READY_TIMEOUT_S = 15.0
#: 停止后等待嗅探器落盘的超时（秒）
STOP_TIMEOUT_S = 10.0


class NetPolicyError(RuntimeError):
    """网络策略无法施加 / 无法验证 —— **必须硬失败**。

    理由与 `EnvCheckError` 同源：网络姿态没生效时采集会产出
    **看起来完全正常的错误数据**（"样本没联网" 与 "我们没拦住" 不可区分）。
    """


def _safe(name: str, argv, **kw):
    try:
        return sh(list(argv), **kw)
    except VmError as e:
        raise NetPolicyError(f"{name} 失败：{e}") from e


# --------------------------------------------------------------------------
# 策略
# --------------------------------------------------------------------------


class NetPolicy:
    """一个域的网络姿态 + 采集窗口。"""

    def __init__(self, vm: Vm, mode: str = "isolated"):
        if mode not in MODES:
            raise NetPolicyError(f"未知网络模式 '{mode}'（可选：{', '.join(MODES)}）")
        self.vm = vm
        self.mode = mode
        self.setup: dict = {}
        self.capture: dict | None = None
        self._tmpdir: str | None = None
        self._proc: subprocess.Popen | None = None
        self._t_capture0: float | None = None

    # ---- 域信息（只读）----

    def _domxml(self) -> ET.Element:
        p = sh(["virsh", "--connect", self.vm.conn, "dumpxml", self.vm.domain],
               check=False, timeout=30)
        if p.returncode != 0:
            raise NetPolicyError(f"无法读取域 XML：{(p.stderr or '').strip()}")
        return ET.fromstring(p.stdout or "")

    def nic(self) -> dict:
        """当前 vNIC 的 MAC / 承载网络 / 链路状态。**一个域只支持一个 NIC**。"""
        ifaces = self._domxml().findall("./devices/interface")
        if len(ifaces) != 1:
            raise NetPolicyError(
                f"域 '{self.vm.domain}' 有 {len(ifaces)} 个 <interface>；"
                f"本工具按设计只支持 1 个（network-policy.md §2 的实测基线就是 1 个）")
        i = ifaces[0]
        src = i.find("source")
        link = i.find("link")
        mac = i.find("mac")
        return {
            "mac": (mac.get("address") if mac is not None else None),
            "network": (src.get("network") if src is not None else None),
            "link_state": (link.get("state") if link is not None else "up"),
        }

    def bridge_of(self, network: str) -> str:
        p = sh(["virsh", "--connect", self.vm.conn, "net-dumpxml", network],
               check=False, timeout=30)
        if p.returncode != 0:
            raise NetPolicyError(
                f"网络 '{network}' 不存在：{(p.stderr or '').strip()}\n"
                f"  recording 模式需要先 `virsh net-define {REC_NET_XML}`")
        br = ET.fromstring(p.stdout or "").find("bridge")
        if br is None or not br.get("name"):
            raise NetPolicyError(f"网络 '{network}' 的 XML 里没有 <bridge name=.../>")
        return br.get("name")

    # ---- recording 承载网络的幂等准备 ----

    @staticmethod
    def _net_is_active(conn: str, name: str) -> bool:
        """网络是否活动 —— **不依赖 locale**。

        实测踩到两次：
          1. 中文输出的分隔符是**全角冒号** `：`(U+FF1A)，`split(":")` 直接失效；
          2. 字段名是 **`活跃`**，不是 `活动`（我按直觉猜错了）。
        所以判据改成"**网桥接口是否存在**" —— libvirt 启停网络时会创建/删除网桥，
        这是与语言无关的事实。字段名匹配只作为辅助。
        """
        # 主判据：网桥接口存在
        try:
            p = sh(["virsh", "--connect", conn, "net-dumpxml", name],
                   check=False, timeout=30)
            br = ET.fromstring(p.stdout or "").find("bridge")
            if br is not None and br.get("name"):
                lp = sh(["ip", "link", "show", br.get("name")],
                        check=False, timeout=15)
                if lp.returncode == 0 and (lp.stdout or "").strip():
                    return True
        except (ET.ParseError, NetPolicyError, VmError):
            pass
        # 辅助判据：字段名归一化（全角/半角冒号都认，中英文都认）
        p = sh(["virsh", "--connect", conn, "net-info", name],
               check=False, timeout=30)
        for ln in (p.stdout or "").splitlines():
            k, sep, v = ln.replace("：", ":").partition(":")
            if not sep:
                continue
            if k.strip().lower() in ("active", "活跃", "活动") and \
               v.strip().lower() in ("yes", "是"):
                return True
        return False

    def ensure_rec_network(self) -> dict:
        """确保 `bat2sh-rec` 已定义且活动。**幂等**。"""
        out = {"name": REC_NET, "defined": False, "started": False}
        p = sh(["virsh", "--connect", self.vm.conn, "net-info", REC_NET],
               check=False, timeout=30)
        if p.returncode != 0:
            if not os.path.exists(REC_NET_XML):
                raise NetPolicyError(f"缺少网络定义文件：{REC_NET_XML}")
            _safe("net-define", ["virsh", "--connect", self.vm.conn,
                                 "net-define", REC_NET_XML], timeout=60)
            out["defined"] = True
        if self._net_is_active(self.vm.conn, REC_NET):
            out["active"] = True
            return out
        # 直接 start，并把"已经活动"当成功 —— 比解析文案更稳
        try:
            sh(["virsh", "--connect", self.vm.conn, "net-start", REC_NET],
               timeout=60)
            out["started"] = True
        except VmError as e:
            msg = str(e)
            if not any(k in msg for k in ("already active", "已经活动", "活跃",
                                          "already running")):
                raise NetPolicyError(f"net-start {REC_NET} 失败：{e}") from e
        out["active"] = True
        return out

    def ensure_dhcp_input_rule(self) -> dict:
        """确保宿主 ufw 放行 `virbr-rec` 的 **DHCP 入站**（且**只放行 DHCP**）。

        ⚠️ **不能用 `ufw allow in on virbr-rec`** —— 那会放行该网桥上的**全部**入站，
        等于把宿主所有监听 0.0.0.0 的服务暴露给样本。DHCP 只需要 udp/67。
        """
        iface = self.bridge_of(REC_NET)
        p = sh(["ufw", "status"], sudo=True, check=False, timeout=30)
        txt = p.stdout or ""
        if "Status: active" not in txt:
            return {"rule": "skipped", "reason": "ufw 未启用"}
        # 已有规则形如：`67/udp on virbr-rec   ALLOW IN   Anywhere`
        for ln in txt.splitlines():
            if iface in ln and "67" in ln and "ALLOW" in ln:
                return {"rule": "present", "line": ln.strip()}
        _safe("ufw allow", ["ufw", "allow", "in", "on", iface, "to", "any",
                            "port", "67", "proto", "udp",
                            "comment", "bat2sh recording net: DHCP only"],
              sudo=True, timeout=60)
        return {"rule": "added", "port": 67, "proto": "udp", "iface": iface,
                "scope": "DHCP only (NOT `allow in on <bridge>`)"}

    # ---- 模式施加（域必须已关机）----

    def apply(self) -> dict:
        """把模式的网络姿态写进**持久域 XML**。必须在冷启动前调用。"""
        if self.vm.is_running():
            raise NetPolicyError(
                "模式必须在域**关机**时施加（链路状态/承载网络属于域定义）。\n"
                "  顺序： revert（停机） → apply_network → start")

        before = self.nic()
        target_net = REC_NET if self.mode == "recording" else DEFAULT_NET
        link = "down" if self.mode == "isolated" else "up"

        extra = {}
        if self.mode == "recording":
            extra["rec_network"] = self.ensure_rec_network()
            extra["dhcp_rule"] = self.ensure_dhcp_input_rule()

        # 每个模式都**完全决定** NIC 配置 ⇒ 幂等、无漂移（不依赖上一次跑成什么样）
        _safe("virt-xml network", ["virt-xml", self.vm.domain,
                                   "--connect", self.vm.conn, "--edit",
                                   "--network", f"network={target_net}"], timeout=60)
        _safe("virt-xml link", ["virt-xml", self.vm.domain,
                                "--connect", self.vm.conn, "--edit",
                                "--network", f"link_state={link}"], timeout=60)

        after = self.nic()
        if after["network"] != target_net or after["link_state"] != link:
            raise NetPolicyError(
                f"网络姿态施加后复核失败：期望 network={target_net} link={link}，"
                f"实际 network={after['network']} link={after['link_state']}")
        if after["mac"] != before["mac"]:
            raise NetPolicyError(
                f"MAC 变了（{before['mac']} → {after['mac']}）—— 嗅探器的过滤会失效")

        self.setup = {
            "mode": self.mode,
            "requested": {"network": target_net, "link_state": link},
            "before": before,
            "after": after,
            "bridge": self.bridge_of(target_net),
            **extra,
        }
        return self.setup

    # ---- recording：给 guest 补默认路由（**必需**，见方法注释）----

    def configure_guest_egress(self) -> dict:
        r"""recording 专用：给 guest 装一条**默认路由**并把 DNS 指向宿主。

        ⚠️ **为什么必需**（实测坑，本工具第一版因此得到空结果）：
        `forward mode='none'` 下 libvirt 在生成的 dnsmasq conf 里写 `dhcp-option=3`
        —— dnsmasq 里"选项 3 不带值"表示**不通告默认网关**。于是 guest 拿到了
        DHCP 地址（实测 192.168.200.36）却**没有默认路由**，后果是：

            ping 8.8.8.8    → 立即 "传输失败。常见故障。"（**一个报文都没发出**）
            TCP 1.1.1.1:80  → 立即 error
            DNS             → 无解析器可用

        宿主侧嗅探器因此只看到多播噪声 —— 与"样本没联网"**不可区分**，
        正是 network-policy.md §1 R5（观测损失）描述的假阴性。

        **补默认路由是否削弱了安全性？不。** 宿主对 192.168.200.0/24
        **不存在任何 masquerade 规则**（实测：`nft list ruleset | grep 192.168.200` = 0 条），
        所以 guest 的报文即使一路穿过所有过滤，也只能以 RFC1918 源地址离开，
        上游必然丢弃。三层各自独立：

            1. libvirt  `iif "virbr-rec" reject`   （forward mode='none' 自动生成）
            2. ufw      `deny (routed)` + 只对 virbr0 开 `ALLOW FWD`
            3. 没有 NAT 规则 ⇒ 源地址是私网，出不了上游

        DNS 指向 192.168.200.1 同理：该地址上 **没有任何 :53 监听**
        （dnsmasq 对 bat2sh-rec 跑的是 `port=0`），所以查询拿到 ICMP port
        unreachable ⇒ `result=refused`，**既可见又不外泄**。
        """
        gw = self.setup.get("bridge_ip") or REC_GW
        # ⚠️ **完全不用 PowerShell / CIM**（本方法第三版）。
        # 实测（本 VM）：
        #     Get-NetAdapter                        14048 ms  ← 主犯
        #     Set-DnsClientServerAddress(validate)  12502 ms  ← DNS 故意不可达 ⇒ 验证超时
        #     Get-NetRoute                           4713 ms
        #     Get-NetIPAddress（过滤后，warm）        3376 ms
        #     首次 PowerShell 调用（冷启动）           4403 ms
        #   ⇒ 组合起来在**冷** CIM 上实测 15.2 s，占掉单样本预算的 1/4。
        #     原生 route.exe / netsh.exe 全部 ~100-450 ms，且**零冷启动**。
        mac = (self.setup.get("after") or {}).get("mac") or ""
        mac_spaced = mac.replace(":", " ").lower()
        if not mac_spaced:
            raise NetPolicyError("缺少 MAC，无法在 guest 内定位接口")

        # 1) 从 `route print -4` 的**接口表**里按 MAC 反查接口号。
        #    这一行形如 `  2...52 54 00 c4 73 fd ......Intel(R) 82574L ...`
        #    按 MAC（纯 ASCII）匹配 ⇒ **不受本地化文案影响**，也不需要 CIM。
        rp = self.vm.qga.exec_wait("route.exe", ["print", "-4"], timeout=60)
        route_txt = decode(rp["stdout_b64"])
        m = re.search(r"^\s*(\d+)\.\.\." + re.escape(mac_spaced),
                      route_txt, re.M | re.I)
        if not m:
            raise NetPolicyError(
                f"在 guest 的 `route print -4` 接口表里找不到 MAC {mac} —— "
                f"网卡可能没起来（DHCP 失败？）。\n{route_txt[:800]}")
        idx = m.group(1)

        # 2) 幂等清理 + 加默认路由（route.exe 失败会返回非 0，但**不抛异常**，故显式检查）
        self.vm.qga.exec_wait("route.exe",
                              ["delete", "0.0.0.0", "mask", "0.0.0.0"], timeout=60)
        ra = self.vm.qga.exec_wait(
            "route.exe",
            ["add", "0.0.0.0", "mask", "0.0.0.0", gw, "if", idx, "metric", "1"],
            timeout=60)
        # 3) DNS 指向宿主（该地址上没有 :53 监听 ⇒ 查询被 refuse，可见且不外泄）。
        #    `validate=no` 是必需的：否则 netsh 会去"验证"这个**故意不可达**的
        #    DNS 服务器，白等 12.5 秒再报一个我们本来就知道的错误。
        ns = self.vm.qga.exec_wait(
            "netsh.exe",
            ["interface", "ipv4", "set", "dnsservers", "name=" + idx,
             "static", gw, "primary", "validate=no"], timeout=60)

        info = {
            "requested_gateway": gw, "guest_ifindex": idx,
            "route_add_exit": ra["exit_code"],
            "route_add_stderr": (decode(ra["stderr_b64"]).strip() or None),
            "dns_set_exit": ns["exit_code"],
        }

        # ---- 复核（不信命令的 rc，直接读回状态）----
        # 只匹配 ASCII 的 IP 字面量 ⇒ 不受本地化文案影响
        vp = self.vm.qga.exec_wait("route.exe", ["print", "-4", "0.0.0.0"], timeout=60)
        vtxt = decode(vp["stdout_b64"])
        vd = self.vm.qga.exec_wait(
            "netsh.exe", ["interface", "ipv4", "show", "dnsservers"], timeout=60)
        dns_txt = decode(vd["stdout_b64"])
        info["route_ok"] = gw in vtxt
        info["dns_ok"] = gw in dns_txt
        if not info["route_ok"]:
            raise NetPolicyError(
                f"guest 内默认路由复核失败（`route print -4 0.0.0.0` 中未见 {gw}）。\n"
                f"  route add rc={ra['exit_code']}\n{vtxt[:600]}")
        if not info["dns_ok"]:
            info["notes"] = ["DNS 服务器复核未通过 —— DNS 尝试可能不可见（默认路由不受影响）"]

        self.setup["guest_egress"] = info
        return info

    # ---- 采集窗口 ----

    def start_capture(self) -> dict:
        """启动嗅探器并**等它就绪**。

        ⚠️ 就绪握手是必须的（实测坑）：`sleep N` 之后再执行样本会**静默漏掉**
        最早的帧 —— 本工具第一版因此整个漏掉了一次 ping，而失败表现为
        "connections 为空"，看起来就像"样本没联网"。
        """
        if not self.setup:
            raise NetPolicyError("先调用 apply() 再 start_capture()")
        iface = self.setup["bridge"]
        mac = self.setup["after"]["mac"]
        if not mac:
            raise NetPolicyError("域 XML 里没有 MAC，无法过滤流量")

        self._tmpdir = tempfile.mkdtemp(prefix="bat2sh-net-")
        os.chmod(self._tmpdir, 0o777)  # 抓包进程以 root 写，采集器以普通用户读
        self._ready = os.path.join(self._tmpdir, "ready")
        self._stop = os.path.join(self._tmpdir, "stop")
        self._out = os.path.join(self._tmpdir, "flows.json")
        self._log = os.path.join(self._tmpdir, "sniff.log")

        py = shutil.which("python3") or "/usr/bin/python3"
        argv = ["sudo", "-n", py, NETSNIFF,
                "--iface", iface, "--guest-mac", mac, "--out", self._out,
                "--ready-file", self._ready, "--stop-file", self._stop]
        logf = open(self._log, "wb")
        self._proc = subprocess.Popen(argv, stdout=logf, stderr=subprocess.STDOUT)
        logf.close()

        t0 = time.monotonic()
        while time.monotonic() - t0 < READY_TIMEOUT_S:
            if os.path.exists(self._ready):
                self._t_capture0 = time.monotonic()
                return {"iface": iface, "ready_ms": int((time.monotonic() - t0) * 1000),
                        "guest_mac": mac}
            if self._proc.poll() is not None:
                raise NetPolicyError(
                    f"嗅探器启动即退出（rc={self._proc.returncode}）：\n"
                    f"{self._read_log()}")
            time.sleep(0.05)
        self._kill()
        raise NetPolicyError(
            f"嗅探器 {READY_TIMEOUT_S}s 内未就绪（iface={iface}）。\n{self._read_log()}")

    def _read_log(self) -> str:
        try:
            with open(self._log, "r", encoding="utf-8", errors="replace") as f:
                return f.read().strip()[-2000:]
        except OSError:
            return "(无日志)"

    def _kill(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def stop_capture(self) -> dict:
        """优雅停止嗅探器并取回结果。"""
        if not self._proc:
            raise NetPolicyError("stop_capture() 前没有 start_capture()")
        with open(self._stop, "w", encoding="utf-8") as f:
            f.write("stop")
        try:
            self._proc.wait(timeout=STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            self._kill()
            raise NetPolicyError("嗅探器未在超时内停止（结果不可信）")
        if not os.path.exists(self._out):
            raise NetPolicyError(
                f"嗅探器未产出结果文件（rc={self._proc.returncode}）：\n{self._read_log()}")
        with open(self._out, "r", encoding="utf-8") as f:
            self.capture = json.load(f)
        self._cleanup()
        return self.capture

    def _cleanup(self) -> None:
        if self._tmpdir and os.path.isdir(self._tmpdir):
            # 目录里有 root 建的文件 ⇒ 需要 sudo 才能删干净
            sh(["rm", "-rf", self._tmpdir], sudo=True, check=False, timeout=60)
        self._tmpdir = None

    # ---- 指纹 ----

    def fingerprint(self) -> dict:
        """产出 `network` 字段（`network-policy.md` §4.1）。"""
        if self.capture is None:
            raise NetPolicyError("采集未完成，无网络指纹可产出")
        cap = self.capture
        conns = [{"dst": c["dst"], "proto": c["proto"], "result": c["result"],
                  "first_seen_ms": c["first_seen_ms"],
                  "bytes_sent": c["bytes_sent"], "bytes_recv": c["bytes_recv"]}
                 for c in cap["flows"]]
        isolated = self.mode == "isolated"
        seen = cap["frames_guest"]

        if isolated:
            # 链路 down ⇒ guest 的帧**根本到不了宿主**，所以"是否尝试过"**观测不到**。
            # 这里必须如实返回 None，而不是 False —— 那是一个我们支持不了的断言。
            attempted, basis = None, ("link-down：guest 的帧不进入宿主网桥，"
                                      "因此无法观测连接尝试（只能证明没有出网）")
        else:
            attempted = bool(conns)
            basis = "宿主侧观察到连接尝试（头部级）"

        notes = []
        if isolated and seen == 0:
            notes.append("egress_frames=0 —— 隔离的硬证据")
        if self.mode == "nat":
            notes.append("⚠️ nat 模式：**外部性真实存在**，出网不可撤回"
                         "（network-policy.md §3 / §6.3 R3）")
        if cap["frames_unparsed"]:
            notes.append(f"{cap['frames_unparsed']} 帧无法解析（分片/扩展头/隧道），"
                         f"已计入计数但**未猜测**其含义")
        if cap["frames_at_max_len"]:
            notes.append(f"{cap['frames_at_max_len']} 帧达到读取上限 "
                         f"{cap['max_frame_bytes']}B —— payload 按设计未读，头部解析不受影响")

        method = {"isolated": "nic-link-down",
                  "recording": "dedicated-no-forward-network",
                  "nat": "explicit-nat-optin"}[self.mode]
        return {
            "mode": self.mode,
            "isolated": isolated,
            "isolation_method": method,
            "network_name": self.setup["requested"]["network"],
            "link_state": self.setup["requested"]["link_state"],
            "iface": self.setup["bridge"],
            "attempted": attempted,
            "attempted_basis": basis,
            "connections": conns,
            "bytes_sent": cap["bytes_sent"],
            "bytes_recv": cap["bytes_recv"],
            # 隔离的硬证据：宿主网桥上来自 guest MAC 的帧数
            "egress_frames": seen,
            "capture": {
                "method": "af_packet-header-only",
                "iface": cap["iface"],
                "guest_mac": cap["guest_mac"],
                "window_ms": cap["duration_ms"],
                "frames_seen": cap["frames_seen"],
                "frames_guest": cap["frames_guest"],
                "frames_other": cap["frames_other"],
                "frames_unparsed": cap["frames_unparsed"],
                "frames_non_ip": cap["frames_non_ip"],
                "frames_at_max_len": cap["frames_at_max_len"],
                "max_frame_bytes": cap["max_frame_bytes"],
                "payload_read": cap["payload_read"],
            },
            "notes": notes,
        }
