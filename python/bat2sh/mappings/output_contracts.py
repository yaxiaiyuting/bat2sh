"""bat2sh 输出契约子系统（B2，v1.10.0a1）。

**问题**：命令被正确翻译了，但两边的**输出形态**不同——``ipconfig`` → ``ip addr`` 命令没错，
可 ``ip addr`` 没有 Windows 的 ``IP Address`` 标签、列位也不同；``for /f`` 解析输出的脚本
会静默解析错。``windows_tools.ToolMapping.output_contract`` 从 v1.8.1 起就存在，
但只被 ``notes`` 里的「输出格式」四个字约束着，**不驱动任何行为**。

**本模块**把该标记升级为可执行契约：每条契约结构化记录
「Windows 命令 → Linux 命令 → 输出差异 → 关键词对照 → 能否解析级适配」。

**1.x 红线（路线图 §1.B）**：1.x **不做解析级输出适配**（v1.8.3 的流程感知改法 26/151
churn 且 examples 漂移，已被否）。本版只做三件事：

1. **登记**契约（``evidence`` 必填，纪律 7）+ ``validate_contracts()`` 校验；
2. **交叉强制**：``windows_tools`` 中 ``output_contract=True`` 的命令**必须**有契约记录
   （把「装饰性标记」变成「必须有实据」）；
3. **诚实化**：裸 ``dxdiag`` / ``perfmon``（无 ``.exe``、当前静默透传 → ``command not found``）
   改为结构化诚实 TODO。带 ``.exe`` 的形态已由既有 exe 分支诚实 TODO，故不重复接管。

``integrated`` 语义 = 「本版转换器是否**消费**该契约」；``False`` 表示仅登记（backlog），
其 ``notes`` 必须写明 ``backlog``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .windows_tools import WINDOWS_TOOLS

#: 输出形态：等效 / 不同 / 无对应物
CONTRACT_SHAPES = ("equivalent", "differs", "none")

_EVIDENCE_RE = re.compile(r"^corpus/.+:\d+$")


@dataclass(frozen=True)
class OutputContract:
    """一条命令的输出契约。

    ``keywords`` 是 ``(Windows 输出关键词, Linux 输出关键词)`` 对照；
    Linux 侧为空串表示「Linux 输出无该关键词」。
    """

    command: str
    linux_command: str
    shape: str
    evidence: str
    keywords: tuple[tuple[str, str], ...] = ()
    integrated: bool = True
    notes: str = ""


def validate_contracts(
    entries: tuple[OutputContract, ...] | None = None,
    tools: tuple[object, ...] | None = None,
) -> list[str]:
    """返回全部违规描述；空列表表示通过。

    规则：
    * ``evidence`` 必填且格式为 ``corpus/<name>:<line>``（纪律 7）；
    * ``shape`` ∈ ``CONTRACT_SHAPES``；``command`` 非空；``command`` 不得重复；
    * ``shape == "differs"`` ⇒ ``notes`` 含「输出」；
    * ``shape == "none"`` ⇒ ``linux_command`` 为空且 ``notes`` 含「无对应物」；
    * ``shape == "equivalent"`` ⇒ ``linux_command`` 非空；
    * ``keywords`` 每项必须是二元组且 Windows 侧非空；
    * ``integrated is False`` ⇒ ``notes`` 含 ``backlog``；
    * **交叉强制**：``tools`` 中 ``output_contract=True`` 的命令必须有契约记录。
    """
    items = OUTPUT_CONTRACTS if entries is None else entries
    tool_items = WINDOWS_TOOLS if tools is None else tools
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        tag = f"[{index}] {item.command or '<empty>'}"
        if not item.command:
            errors.append(f"{tag}: command 为空")
        if not _EVIDENCE_RE.match(item.evidence):
            errors.append(f"{tag}: evidence 缺失或格式错误（应为 corpus/<name>:<line>）")
        if item.shape not in CONTRACT_SHAPES:
            errors.append(f"{tag}: shape 非法 {item.shape!r}")
        if item.shape == "differs" and "输出" not in item.notes:
            errors.append(f"{tag}: shape=differs 必须在 notes 说明输出差异")
        if item.shape == "none" and (item.linux_command or "无对应物" not in item.notes):
            errors.append(f"{tag}: shape=none 必须 linux_command 为空且 notes 注明「无对应物」")
        if item.shape == "equivalent" and not item.linux_command:
            errors.append(f"{tag}: shape=equivalent 必须给出 linux_command")
        for pair in item.keywords:
            if len(pair) != 2 or not pair[0]:
                errors.append(f"{tag}: keywords 每项须为 (Windows 关键词, Linux 关键词) 且前者非空")
        if not item.integrated and "backlog" not in item.notes:
            errors.append(f"{tag}: integrated=False 必须在 notes 标注 backlog（登记未生效）")
        key = item.command.lower()
        if key in seen:
            errors.append(f"{tag}: command 重复")
        seen.add(key)
    for tool in tool_items:
        if getattr(tool, "output_contract", False):
            if tool.win.lower() not in seen:
                errors.append(f"{tool.win}: output_contract=true 但缺少 OutputContract 记录")
    return errors


#: 首批契约（B2，v1.10.0a1）：ipconfig 命令层已映射、输出需契约；
#: dxdiag/perfmon 无对应物；ping/help 为 windows_tools 中 output_contract=true 的既有条目。
OUTPUT_CONTRACTS: tuple[OutputContract, ...] = (
    OutputContract(
        command="ipconfig",
        linux_command="ip addr",
        shape="differs",
        evidence="corpus/显示自己的IP.bat:2",
        keywords=(
            ("IPv4 地址", "inet "),
            ("IPv6 地址", "inet6 "),
            ("物理地址", "ether "),
            ("IP Address", ""),
            ("Physical Address", ""),
        ),
        integrated=True,
        notes="命令层由 cmd_ipconfig 映射为 ip addr；输出无 “IP Address/Physical Address” "
        "标签、列位不同（tokens=15 等），解析型脚本必须适配。1.x 只做告警/诚实 TODO，"
        "不做解析级适配（路线图 §1.B）；中文关键词对照与 _FINDSTR_CJK_MAP 一致，由测试锁定。",
    ),
    OutputContract(
        command="dxdiag",
        linux_command="",
        shape="none",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:6285",
        integrated=True,
        notes="Windows DirectX 诊断工具在 Linux 无对应物（lshw/inxi 仅近似，输出契约完全不同）；"
        "裸命令（无 .exe）原为静默透传 → command not found，本版改结构化诚实 TODO。目标物不存在。",
    ),
    OutputContract(
        command="perfmon",
        linux_command="",
        shape="none",
        evidence="corpus/系统优化.bat:4287",
        integrated=True,
        notes="Windows 性能监视器在 Linux 无对应物（sar/vmstat/perf 语义与输出均不同）；"
        "裸命令（无 .exe）原为静默透传 → command not found，本版改结构化诚实 TODO。目标物不存在。",
    ),
    OutputContract(
        command="ping",
        linux_command="ping -c",
        shape="differs",
        evidence="corpus/让屏幕显示硬件错误的信息（恶搞类）.bat:11",
        keywords=(("TTL=", "ttl="), ("Reply from", "bytes from")),
        integrated=False,
        notes="开关需转换（/n→-c）；输出格式与 Windows 不同，解析 ping 输出的脚本必须适配；"
        "本版仅登记（backlog），解析级适配留 2.x。",
    ),
    OutputContract(
        command="help",
        linux_command="man",
        shape="differs",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:13565",
        integrated=False,
        notes="Windows 内建帮助 → man：输出格式完全不同（内建命令帮助 vs man 页面），"
        "无参数时行为差异大；本版仅登记（backlog）。",
    ),
)


def contract_for(
    name: str, entries: tuple[OutputContract, ...] | None = None
) -> OutputContract | None:
    """按命令名（大小写不敏感）查找契约。

    **不剥离 ``.exe``**：带后缀的可执行文件形态由既有 exe 分支诚实 TODO，
    本子系统只接管**裸命令**（``dxdiag`` / ``perfmon``），避免重复接管与消息漂移。
    """
    items = OUTPUT_CONTRACTS if entries is None else entries
    low = name.strip().strip('"').strip("%").lower()
    for item in items:
        if item.command.lower() == low:
            return item
    return None
