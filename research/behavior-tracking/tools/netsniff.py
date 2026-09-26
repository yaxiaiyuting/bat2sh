#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bat2sh 行为采集 —— 网络头部嗅探器（`recording` 模式的记录后端）

职责：在宿主侧**只读**观察某网桥上属于目标 VM 的帧，输出**连接级元数据**
（dst / proto / result / 字节数）。**不读 payload、不落 pcap。**

设计依据：`research/behavior-tracking/network-policy.md`
  §4.2 result 判定规则 / §4.3 不记录内容（隐私）/ §5.4 D1b（tcpdump 不可用）

为什么自己写而不用 tcpdump / tshark：
  1. 实测宿主**未安装** tcpdump / dumpcap / tshark（见 network-policy.md §2）。
     为采集去装包会扩大供应链面，与降低风险的初衷相悖。
  2. 更重要的：**隐私是构造性质而非纪律**。本文件用 `recvfrom(MAX_FRAME_BYTES)`
     只把每帧的前 192 字节读进内存，并且解析器**没有**任何读取 payload 的代码路径。
     pcap 做不到这一点 —— 它必然把 payload 写进文件。

⚠️ 需要 CAP_NET_RAW ⇒ 必须以 root 运行。**这是唯一被提权的进程**，
   且它是只读的、无参数的（除了 iface / MAC / 输出路径 / 时限）。
   调用方是 `tools/net.py`，用 `sudo -n` 起一个独立子进程，采集器主体不提权。
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import select
import signal
import socket
import struct
import sys
import time

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

#: 每帧**最多读进内存**的字节数。Ethernet(14) + IPv4 最大头(60) + TCP 最大头(60) = 134，
#: 取 192 留出 VLAN 标签与余量。**这是隐私保证的物理边界**：payload 根本不进本进程。
MAX_FRAME_BYTES = 192

ETH_P_ALL = 0x0003
ETH_HDR_LEN = 14

ETH_IPV4 = 0x0800
ETH_IPV6 = 0x86DD
ETH_VLAN = 0x8100
ETH_QINQ = 0x88A8

IPPROTO_ICMP = 1
IPPROTO_TCP = 6
IPPROTO_UDP = 17
IPPROTO_ICMPV6 = 58

TCP_FIN, TCP_SYN, TCP_RST, TCP_PSH, TCP_ACK = 0x01, 0x02, 0x04, 0x08, 0x10

#: ICMPv4 type 3 (Destination Unreachable) 的 code → result
ICMP4_UNREACH = {3: "refused", 0: "unreachable", 1: "unreachable",
                 2: "unreachable", 9: "unreachable", 10: "unreachable",
                 13: "unreachable"}
#: ICMPv6 type 1 (Destination Unreachable) 的 code → result
ICMP6_UNREACH = {4: "refused", 0: "unreachable", 1: "unreachable",
                 3: "unreachable"}


def _now_ms() -> float:
    return time.monotonic() * 1000.0


def mac_str(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b)


def ipv4_str(b: bytes) -> str:
    return ".".join(str(x) for x in b)


def ipv6_str(b: bytes) -> str:
    return socket.inet_ntop(socket.AF_INET6, b)


# --------------------------------------------------------------------------
# 流表
# --------------------------------------------------------------------------


class FlowTable:
    """按 5 元组聚合，最终给出 `result` 判定。"""

    def __init__(self, guest_mac: str, t0: float):
        self.guest_mac = guest_mac.lower()
        self.t0 = t0
        self.flows: dict[tuple, dict] = {}
        self.frames_seen = 0
        self.frames_guest = 0
        self.frames_other = 0
        self.unparsed = 0
        self.non_ip = 0
        # 恰好读满 MAX_FRAME_BYTES 的帧数。**不是"损坏"**：192 > 最大头长(134)，
        # 解析永远不受影响；这个计数只用来如实说明"有多少帧的 payload 我们没读"。
        self.max_len = 0

    def _flow(self, key: tuple, meta: dict) -> dict:
        f = self.flows.get(key)
        if f is None:
            f = {
                "proto": meta["proto"],
                "dst": meta["dst"],
                "direction": meta["direction"],
                "first_seen_ms": int(_now_ms() - self.t0),
                "bytes_sent": 0,
                "bytes_recv": 0,
            }
            self.flows[key] = f
        return f

    # ---- 帧入口 ----

    def feed(self, frame: bytes) -> None:
        self.frames_seen += 1
        if len(frame) >= MAX_FRAME_BYTES:
            self.max_len += 1

        if len(frame) < ETH_HDR_LEN:
            self.unparsed += 1
            return
        dst_mac = mac_str(frame[0:6])
        src_mac = mac_str(frame[6:12])
        ethertype = struct.unpack("!H", frame[12:14])[0]
        off = ETH_HDR_LEN

        # VLAN / QinQ：跳过标签，但**只跳一层**；再深（QinQ 嵌套）不猜，计 other
        if ethertype in (ETH_VLAN, ETH_QINQ):
            if len(frame) < off + 4:
                self.unparsed += 1
                return
            ethertype = struct.unpack("!H", frame[off + 2:off + 4])[0]
            off += 4

        s = src_mac == self.guest_mac
        d = dst_mac == self.guest_mac
        if not (s or d):
            self.frames_other += 1
            return
        self.frames_guest += 1
        direction = "out" if s else "in"

        if ethertype == ETH_IPV4:
            self._ipv4(frame, off, direction)
        elif ethertype == ETH_IPV6:
            self._ipv6(frame, off, direction)
        else:
            # ARP / 其他 L2：属于"网络行为"但不属于"连接"，计 other 不猜
            self.non_ip += 1

    # ---- IPv4 ----

    def _ipv4(self, f: bytes, off: int, direction: str) -> None:
        if len(f) < off + 20:
            self.unparsed += 1
            return
        ihl = (f[off] & 0x0F) * 4
        if ihl < 20 or len(f) < off + ihl:
            self.unparsed += 1
            return
        proto = f[off + 9]
        total_len = struct.unpack("!H", f[off + 2:off + 4])[0]
        src = ipv4_str(f[off + 12:off + 16])
        dst = ipv4_str(f[off + 16:off + 20])
        # 分片（offset != 0）：**不重组、不猜测**，计 other
        frag = struct.unpack("!H", f[off + 6:off + 8])[0] & 0x1FFF
        if frag:
            self.unparsed += 1
            return
        self._l4(f, off + ihl, proto, src, dst, direction, total_len - ihl)

    # ---- IPv6（不处理扩展头链；带扩展头的归 other，不猜）----

    def _ipv6(self, f: bytes, off: int, direction: str) -> None:
        if len(f) < off + 40:
            self.unparsed += 1
            return
        nxt = f[off + 6]
        payload_len = struct.unpack("!H", f[off + 4:off + 6])[0]
        src = ipv6_str(f[off + 8:off + 24])
        dst = ipv6_str(f[off + 24:off + 40])
        if nxt in (0, 43, 44, 60):  # hop-by-hop / routing / fragment / dest-opts
            self.unparsed += 1
            return
        self._l4(f, off + 40, nxt, src, dst, direction, payload_len)

    # ---- L4 ----

    def _l4(self, f: bytes, off: int, proto: int, src: str, dst: str,
            direction: str, ip_payload_len: int) -> None:
        guest_ip = src if direction == "out" else dst
        peer_ip = dst if direction == "out" else src

        if proto == IPPROTO_TCP:
            if len(f) < off + 20:
                self.unparsed += 1
                return
            sport, dport = struct.unpack("!HH", f[off:off + 4])
            flags = f[off + 13]
            gport, pport = (sport, dport) if direction == "out" else (dport, sport)
            key = ("tcp", guest_ip, gport, peer_ip, pport)
            fl = self._flow(key, {"proto": "tcp",
                                  "dst": f"{peer_ip}:{pport}",
                                  "direction": direction})
            self._add_bytes(fl, direction, ip_payload_len)
            if direction == "out":
                if flags & TCP_SYN and not flags & TCP_ACK:
                    fl["syn"] = True
                if flags & TCP_RST:
                    fl["rst"] = True
            else:
                if flags & TCP_SYN and flags & TCP_ACK:
                    fl["synack"] = True
                if flags & TCP_RST:
                    fl["rst"] = True
            return

        if proto == IPPROTO_UDP:
            if len(f) < off + 8:
                self.unparsed += 1
                return
            sport, dport = struct.unpack("!HH", f[off:off + 4])
            gport, pport = (sport, dport) if direction == "out" else (dport, sport)
            key = ("udp", guest_ip, gport, peer_ip, pport)
            fl = self._flow(key, {"proto": "udp",
                                  "dst": f"{peer_ip}:{pport}",
                                  "direction": direction})
            self._add_bytes(fl, direction, ip_payload_len)
            return

        if proto in (IPPROTO_ICMP, IPPROTO_ICMPV6):
            if len(f) < off + 8:
                self.unparsed += 1
                return
            itype, icode = f[off], f[off + 1]
            # echo request / reply 自带 id+seq，用它做流键的一部分（区分并发 ping）
            if (proto == IPPROTO_ICMP and itype in (0, 8)) or \
               (proto == IPPROTO_ICMPV6 and itype in (128, 129)):
                ident = struct.unpack("!H", f[off + 4:off + 6])[0]
                key = ("icmp", guest_ip, ident, peer_ip, 0)
                fl = self._flow(key, {"proto": "icmp", "dst": peer_ip,
                                      "direction": direction})
                self._add_bytes(fl, direction, ip_payload_len)
                if (proto == IPPROTO_ICMP and itype == 0) or \
                   (proto == IPPROTO_ICMPV6 and itype == 129):
                    fl["echo_reply"] = True
                else:
                    fl["echo_request"] = True
                return
            # 错误报文：**解析内嵌的"被引用报文的头部"**，把结果归因回原始流。
            # ⚠️ 这是**头部**不是应用 payload —— 正是防火墙判断"哪个连接被拒"的标准做法。
            # 不做这一步的后果（本工具第二版实测）：被 refuse 的 TCP 连接会显示成
            # `no-reply`（"静默丢弃"），而真实语义是 `refused`（"有东西在应答"）。
            # 两者对样本后续行为的影响完全不同，不能混。
            quoted = self._quoted_flow(f, off + 8)
            if quoted is not None:
                qkey, qmeta = quoted
                qf = self._flow(qkey, qmeta)
                qf["icmp_unreach"] = (itype, icode)
                return
            # 内嵌头读不到（截断/非 IP/不认识的协议）⇒ **不猜**，记为独立流
            key = ("icmp", guest_ip, 0, peer_ip, 0, itype, icode)
            fl = self._flow(key, {"proto": "icmp", "dst": peer_ip,
                                  "direction": direction})
            fl["icmp_type"] = itype
            fl["icmp_code"] = icode
            self._add_bytes(fl, direction, ip_payload_len)
            return

        # 其他 IP 协议（GRE/ESP/...）：记为 other，不猜
        key = ("other", guest_ip, 0, peer_ip, proto)
        fl = self._flow(key, {"proto": "other", "dst": peer_ip,
                              "direction": direction})
        self._add_bytes(fl, direction, ip_payload_len)

    @staticmethod
    def _add_bytes(fl: dict, direction: str, n: int) -> None:
        if n <= 0:
            return
        if direction == "out":
            fl["bytes_sent"] += n
        else:
            fl["bytes_recv"] += n

    # ---- ICMP 错误报文里"被引用报文的头部" ----

    def _quoted_flow(self, f: bytes, qoff: int):
        """解析 ICMP 错误报文内嵌的原始 IP 头 + L4 前 4 字节，还原**原始流**。

        返回 `(key, meta)` 或 `None`（读不到就不猜）。

        隐私说明：读的是**被引用报文的 IP/L4 头部**（源/目的/协议/端口），
        不是应用 payload。这正是 RFC 792 里 ICMP 错误报文携带信息的用途，
        也是防火墙做"哪个连接被拒"归因的标准做法。读取范围仍在
        `MAX_FRAME_BYTES = 192` 之内。
        """
        if len(f) < qoff + 20:
            return None
        ver = f[qoff] >> 4
        if ver == 4:
            ihl = (f[qoff] & 0x0F) * 4
            if ihl < 20 or len(f) < qoff + ihl + 4:
                return None
            proto = f[qoff + 9]
            frag = struct.unpack("!H", f[qoff + 6:qoff + 8])[0] & 0x1FFF
            if frag:
                return None
            src = ipv4_str(f[qoff + 12:qoff + 16])
            dst = ipv4_str(f[qoff + 16:qoff + 20])
        elif ver == 6:
            if len(f) < qoff + 40 + 4:
                return None
            proto = f[qoff + 6]
            if proto in (0, 43, 44, 60):
                return None
            src = ipv6_str(f[qoff + 8:qoff + 24])
            dst = ipv6_str(f[qoff + 24:qoff + 40])
            ihl = 40
        else:
            return None

        l4 = qoff + ihl
        if proto == IPPROTO_TCP:
            sport, dport = struct.unpack("!HH", f[l4:l4 + 4])
            # 原始报文是 guest 发出的 ⇒ 源就是 guest
            return (("tcp", src, sport, dst, dport),
                    {"proto": "tcp", "dst": f"{dst}:{dport}", "direction": "out"})
        if proto == IPPROTO_UDP:
            sport, dport = struct.unpack("!HH", f[l4:l4 + 4])
            return (("udp", src, sport, dst, dport),
                    {"proto": "udp", "dst": f"{dst}:{dport}", "direction": "out"})
        if proto in (IPPROTO_ICMP, IPPROTO_ICMPV6):
            ident = struct.unpack("!H", f[l4 + 4:l4 + 6])[0]
            return (("icmp", src, ident, dst, 0),
                    {"proto": "icmp", "dst": dst, "direction": "out"})
        return None

    # ---- 判定 ----

    @staticmethod
    def classify(fl: dict) -> str:
        """`network-policy.md` §4.2 的判定表。"""
        proto = fl["proto"]
        if fl.get("rst"):
            return "refused"
        # ICMP 错误（优先于 synack/no-reply）：它**就是**"对端/中间设备拒绝了"
        if fl.get("icmp_unreach"):
            it, ic = fl["icmp_unreach"]
            tbl = ICMP4_UNREACH if it == 3 else (
                ICMP6_UNREACH if it == 1 else {})
            return tbl.get(ic, "other-icmp")
        if proto == "icmp":
            if fl.get("echo_reply"):
                return "established"
            it, ic = fl.get("icmp_type"), fl.get("icmp_code")
            if it is not None:
                tbl = ICMP4_UNREACH if it == 3 else (
                    ICMP6_UNREACH if it == 1 else {})
                if ic in tbl:
                    return tbl[ic]
                return "other-icmp"
            return "sent"
        if fl.get("synack"):
            return "established"
        if proto == "udp":
            # UDP 无握手：有回包即认为双向可达，否则只能说"发出了"
            return "established" if fl["bytes_recv"] > 0 else "sent"
        if proto == "tcp":
            return "no-reply"
        return "sent"

    def report(self) -> dict:
        conns = []
        for fl in self.flows.values():
            r = fl.get("result") or self.classify(fl)
            item = {"dst": fl["dst"], "proto": fl["proto"], "result": r,
                    "direction": fl["direction"],
                    "first_seen_ms": fl["first_seen_ms"],
                    "bytes_sent": fl["bytes_sent"], "bytes_recv": fl["bytes_recv"]}
            conns.append(item)
        conns.sort(key=lambda c: (c["first_seen_ms"], c["dst"]))
        return {
            "flows": conns,
            # ⚠️ 按**方向字节**求和，而不是按 flow.direction 过滤：一条流里
            # 两个方向都有字节（首帧方向只表示"谁先开口"）。
            # 本工具第一版按 direction=="in" 求和，导致 bytes_recv 恒为 0。
            "bytes_sent": sum(c["bytes_sent"] for c in conns),
            "bytes_recv": sum(c["bytes_recv"] for c in conns),
            "frames_seen": self.frames_seen,
            "frames_guest": self.frames_guest,
            "frames_other": self.frames_other,
            "frames_unparsed": self.unparsed,
            "frames_non_ip": self.non_ip,
            "frames_at_max_len": self.max_len,
        }


# --------------------------------------------------------------------------
# 主循环
# --------------------------------------------------------------------------


def sniff(iface: str, guest_mac: str, out_path: str, duration_s: float,
          stop_file: str | None, ready_file: str | None = None) -> dict:
    t0 = _now_ms()
    table = FlowTable(guest_mac, t0)

    try:
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(ETH_P_ALL))
    except PermissionError as e:
        raise SystemExit(f"需要 CAP_NET_RAW（以 root 运行）：{e}")
    try:
        s.bind((iface, 0))
    except OSError as e:
        raise SystemExit(f"无法绑定网桥 {iface}：{e}（网桥不存在或未启动？）")
    s.setblocking(False)
    # 加大接收缓冲，避免突发把帧丢在内核里（丢帧会让指纹"少记"而不是报错）
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
    except OSError:
        pass

    # ---- 就绪握手 ----
    # ⚠️ 实测坑：调用方若只 `sleep N` 就开跑，会**静默漏掉**样本最早的那批帧
    #（本工具第一版就这么漏掉了一整个 ping）。必须由嗅探器**主动宣告**已绑定成功，
    # 调用方等到这个文件出现再执行样本。
    if ready_file:
        tmp = ready_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        os.replace(tmp, ready_file)

    stopped = {"v": False}

    def _sig(_sig, _frm):
        stopped["v"] = True

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    end_at = (t0 + duration_s * 1000.0) if duration_s > 0 else None
    errors = 0
    while not stopped["v"]:
        now = _now_ms()
        if end_at is not None and now >= end_at:
            break
        if stop_file and os.path.exists(stop_file):
            break
        try:
            r, _, _ = select.select([s], [], [], 0.25)
        except InterruptedError:
            continue
        if not r:
            continue
        try:
            frame, _addr = s.recvfrom(MAX_FRAME_BYTES)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
                continue
            errors += 1
            if errors > 50:
                break
            continue
        # 只读进 MAX_FRAME_BYTES：**这就是隐私保证的物理边界**，
        # payload 从不进入本进程，解析器里也没有读它的代码路径。
        table.feed(frame)

    s.close()
    rep = table.report()
    rep["iface"] = iface
    rep["guest_mac"] = guest_mac.lower()
    rep["duration_ms"] = int(_now_ms() - t0)
    rep["max_frame_bytes"] = MAX_FRAME_BYTES
    rep["payload_read"] = False  # 构造性质，非承诺
    rep["recv_errors"] = errors

    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    os.chmod(tmp, 0o644)  # 采集器主体以普通用户运行，必须读得到
    os.replace(tmp, out_path)
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="netsniff.py",
        description="只读网络头部嗅探（连接级元数据；不读 payload、不落 pcap）")
    ap.add_argument("--iface", required=True, help="要监听的网桥（如 virbr0 / virbr-rec）")
    ap.add_argument("--guest-mac", required=True, help="目标 VM 的 MAC（用于过滤无关流量）")
    ap.add_argument("--out", required=True, help="结果 JSON 路径")
    ap.add_argument("--duration", type=float, default=0,
                    help="最长监听秒数（0 = 无限，靠 --stop-file 或信号结束）")
    ap.add_argument("--stop-file", default=None,
                    help="该文件出现即优雅退出（调用方用它精确控制窗口）")
    ap.add_argument("--ready-file", default=None,
                    help="绑定成功后创建该文件 —— 调用方**必须**等它出现再执行样本，"
                         "否则会静默漏掉最早的帧")
    args = ap.parse_args(argv)
    rep = sniff(args.iface, args.guest_mac, args.out, args.duration, args.stop_file,
                args.ready_file)
    print(json.dumps({k: rep[k] for k in
                      ("iface", "frames_seen", "frames_guest", "frames_other",
                       "frames_unparsed", "frames_non_ip", "duration_ms")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
