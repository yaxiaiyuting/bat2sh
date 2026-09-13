"""复杂管道的参考改写建议：只生成注释文本，绝不生成可执行行。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .utils import tokenize_args

HIGH = "高"
MEDIUM = "中"
LOW = "低"
_LEVEL_RANK = {HIGH: 0, MEDIUM: 1, LOW: 2}


@dataclass(frozen=True)
class _Plan:
    level: str
    replacement: str
    difference: str | None = None
    fallback_name: str | None = None


_FINDSTR_FLAGS = {"i": "i", "v": "v", "n": "n", "s": "r"}


def _rewrite_findstr(args: str) -> str:
    out: list[str] = []
    for token in tokenize_args(args):
        low = token.lower()
        if low == "/r":
            continue
        if low.startswith("/c:"):
            out.extend(["-F", token[3:]])
            continue
        if len(low) == 2 and low.startswith("/") and low[1] in _FINDSTR_FLAGS:
            out.append("-" + _FINDSTR_FLAGS[low[1]])
            continue
        out.append(token)
    return " ".join(out)


def _rewrite_dir(args: str) -> str:
    out: list[str] = []
    for token in tokenize_args(args):
        low = token.lower()
        if low == "/b":
            out.append("-1")
        elif low == "/s":
            out.append("-R")
        elif re.fullmatch(r"/[a-z]+", low):
            continue
        else:
            out.append(token)
    return " ".join(out)


def _plan_segment(segment: str) -> _Plan | None:
    text = re.sub(r"(?i)2>nul", "2>/dev/null", segment.strip())
    if not text:
        return None

    m = re.match(r"(?i)^certutil\s+-hashfile\s+(\S+)\s+MD5\b(.*)$", text)
    if m:
        return _Plan(HIGH, f"md5sum {m.group(1)}{m.group(2)}", "输出无 CertUtil 头与指纹格式")
    m = re.match(r"(?i)^certutil\s+-hashfile\s+(\S+)\s+SHA256\b(.*)$", text)
    if m:
        return _Plan(HIGH, f"sha256sum {m.group(1)}{m.group(2)}", "输出无 CertUtil 头与指纹格式")
    m = re.match(r"(?i)^findstr\b(.*)$", text)
    if m:
        return _Plan(
            HIGH,
            ("grep " + _rewrite_findstr(m.group(1))).strip(),
            "findstr 与 grep 的正则语法存在差异（/r 在 grep 中为默认行为）",
        )
    m = re.match(r"(?i)^sort\s+/r\b(.*)$", text)
    if m:
        return _Plan(HIGH, f"sort -r{m.group(1)}")
    m = re.match(r"(?i)^type\s+(.+)$", text)
    if m:
        return _Plan(HIGH, f"cat {m.group(1)}")

    m = re.match(r"(?i)^sc\s+query\s+(\S+)(.*)$", text)
    if m:
        return _Plan(
            MEDIUM,
            f"systemctl is-active {m.group(1)}{m.group(2)}",
            "sc 输出 STATE : 4 RUNNING 等文本，systemctl 输出 active/inactive",
        )
    m = re.match(r"(?i)^netstat\b(.*)$", text)
    if m:
        return _Plan(MEDIUM, f"ss{m.group(1)}", "列名与列顺序不同")
    m = re.match(r"(?i)^tasklist\b(.*)$", text)
    if m:
        return _Plan(
            MEDIUM,
            f"ps aux{m.group(1)}",
            "列格式完全不同；/fi 等过滤条件需改写为 grep/ps 选项",
        )
    m = re.match(r"(?i)^ipconfig\b(.*)$", text)
    if m:
        return _Plan(MEDIUM, f"ip addr{m.group(1)}", "输出结构不同（Linux 无 Windows 的分节摘要）")
    m = re.match(r"(?i)^systeminfo\b(.*)$", text)
    if m:
        return _Plan(MEDIUM, "uname -a", "信息量与结构差异大；系统版本请另加 cat /etc/os-release")
    m = re.match(r"(?i)^driverquery\b(.*)$", text)
    if m:
        return _Plan(MEDIUM, "lsmod", "驱动服务与内核模块语义不同")
    m = re.match(r"(?i)^query\s+user\b(.*)$", text)
    if m:
        return _Plan(MEDIUM, f"who{m.group(1)}", "列格式不同（who 显示登录会话）")
    m = re.match(r"(?i)^net\s+user\b(.*)$", text)
    if m:
        return _Plan(MEDIUM, f"getent passwd{m.group(1)}", "输出无表头，字段与格式完全不同")
    m = re.match(r"(?i)^net\s+start\b(.*)$", text)
    if m:
        return _Plan(
            MEDIUM,
            "systemctl list-units --type=service --state=running",
            "输出格式不同（无 Windows 的清单标题与列）",
        )
    m = re.match(r"(?i)^dir\b(.*)$", text)
    if m:
        return _Plan(
            MEDIUM,
            ("ls " + _rewrite_dir(m.group(1))).strip(),
            "Windows dir 列格式与 ls 不同（/b→ls -1、/s→ls -R 已近似，请核对）",
        )

    m = re.match(r"(?i)^wmic\s+os\b", text)
    if m:
        return _Plan(LOW, "用 /etc/os-release 或 lsb_release -a 获取系统信息", fallback_name="wmic")
    m = re.match(r"(?i)^wmic\s+cpu\b", text)
    if m:
        return _Plan(LOW, "用 lscpu 或 /proc/cpuinfo 获取 CPU 信息", fallback_name="wmic")
    m = re.match(r"(?i)^wmic\s+logicaldisk\b", text)
    if m:
        return _Plan(LOW, "用 df -h 或 lsblk 获取磁盘信息", fallback_name="wmic")
    m = re.match(r"(?i)^wmic\s+process\b", text)
    if m:
        return _Plan(LOW, "用 ps aux（配合 grep）获取进程信息", fallback_name="wmic")
    m = re.match(r"(?i)^wmic\b", text)
    if m:
        return _Plan(LOW, "用 /proc、lsblk、lscpu 等获取等价信息", fallback_name="wmic")
    m = re.match(r"(?i)^reg\s+query\b", text)
    if m:
        return _Plan(
            LOW,
            "读取对应的 Linux 配置文件（Linux 无注册表；键值请按具体场景改写）",
            fallback_name="reg query",
        )
    m = re.match(r"(?i)^icacls\b", text)
    if m:
        return _Plan(
            LOW,
            "简单权限用 chmod，复杂 ACL 用 setfacl（ACL 与 UGO 抽象层不同）",
            fallback_name="icacls",
        )
    m = re.match(r"(?i)^attrib\b", text)
    if m:
        return _Plan(LOW, "用 chmod / lsattr 调整文件属性", fallback_name="attrib")
    return None


def split_pipeline_segments(text: str) -> list[str]:
    """按顶层 ``|`` 拆段；``^|`` 转义与引号内的 ``|`` 不拆（``||`` 保留）。"""
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            buf.append(char)
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "\"'":
            quote = char
            buf.append(char)
            index += 1
            continue
        if char == "^" and index + 1 < len(text):
            buf.append(text[index : index + 2])
            index += 2
            continue
        if char == "|":
            if index + 1 < len(text) and text[index + 1] == "|":
                buf.append("||")
                index += 2
                continue
            parts.append("".join(buf))
            buf = []
            index += 1
            continue
        buf.append(char)
        index += 1
    parts.append("".join(buf))
    return [part for part in parts if part.strip()]


def suggest_pipeline(original: str) -> list[str] | None:
    """返回建议注释行（不含 ``#`` 前缀，由调用方添加）；None 表示无建议。"""
    segments = split_pipeline_segments(original)
    if len(segments) < 2:
        return None
    plans: list[_Plan] = []
    for segment in segments:
        plan = _plan_segment(segment)
        if plan is None:
            return None
        plans.append(plan)

    level = max(plans, key=lambda plan: _LEVEL_RANK[plan.level]).level
    fragments = " | ".join(plan.replacement for plan in plans)
    lines = ["  原命令: " + original.strip()]
    if level == LOW:
        lines.append(f"  参考(低): {fragments}")
        names = "、".join(
            dict.fromkeys(plan.fallback_name for plan in plans if plan.fallback_name)
        )
        lines.append(f"  说明: {names} 无 Linux 对应物，需手工选替代方案")
        return lines
    lines.append(f"  参考({level}): {fragments}")
    differences = "；".join(
        dict.fromkeys(plan.difference for plan in plans if plan.difference)
    )
    if differences:
        lines.append("  差异: " + differences)
    return lines
