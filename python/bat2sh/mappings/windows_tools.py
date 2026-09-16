"""bat2sh Windows 命令结构化映射表（v1.8.1）。

单一数据源（single source of truth）：新增/修正的 Windows→Linux 映射以本表为准。
`evidence` 必填且指向真实语料（纪律 7：不发明映射）；`validate_mappings()` 在测试中守护。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FORMS = ("1:1", "1:N", "N:1", "partial", "none")
CONFIDENCES = ("A", "B", "C", "D")
TARGET_EXISTS = ("yes", "no", "unknown")
_EVIDENCE_RE = re.compile(r"^corpus/.+:\d+$")


@dataclass(frozen=True)
class ToolMapping:
    win: str
    linux: str
    form: str
    confidence: str
    output_contract: bool
    dangerous: bool
    target_exists: str
    evidence: str
    notes: str = ""


def validate_mappings(entries: tuple[ToolMapping, ...] | None = None) -> list[str]:
    """返回全部违规描述；空列表表示通过。规则见 docs/v1.8.1-design.md §3.3。"""
    items = WINDOWS_TOOLS if entries is None else entries
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        tag = f"[{index}] {item.win or '<empty>'}"
        if not _EVIDENCE_RE.match(item.evidence):
            errors.append(f"{tag}: evidence 缺失或格式错误（应为 corpus/<name>:<line>）")
        if item.form not in FORMS:
            errors.append(f"{tag}: form 非法 {item.form!r}")
        if item.confidence not in CONFIDENCES:
            errors.append(f"{tag}: confidence 非法 {item.confidence!r}")
        if item.target_exists not in TARGET_EXISTS:
            errors.append(f"{tag}: target_exists 非法 {item.target_exists!r}")
        if item.confidence == "D" and (item.form != "none" or item.linux):
            errors.append(f"{tag}: confidence D 必须 form=none 且 linux 为空（不得硬凑组合）")
        if item.output_contract and "输出格式" not in item.notes:
            errors.append(f"{tag}: output_contract=true 必须在 notes 说明输出格式适配")
        if item.target_exists == "no" and "目标物不存在" not in item.notes:
            errors.append(f"{tag}: target_exists=no 必须在 notes 标注目标物不存在")
        key = item.win.lower()
        if key in seen:
            errors.append(f"{tag}: win 重复")
        seen.add(key)
    return errors


WINDOWS_TOOLS: tuple[ToolMapping, ...] = (
    ToolMapping(
        win="title",
        linux="printf '\\033]0;%s\\007'",
        form="partial",
        confidence="B",
        output_contract=False,
        dangerous=False,
        target_exists="unknown",
        evidence="corpus/与某人的QQ临时对话.bat:3",
        notes="可近似为 ANSI 设置终端标题（printf \\033]0;…\\007）；无 TTY 时无效果，需人工确认。",
    ),
    ToolMapping(
        win="msg",
        linux="wall",
        form="partial",
        confidence="B",
        output_contract=False,
        dangerous=False,
        target_exists="unknown",
        evidence="corpus/瑞星杀毒软件2008批处理版.bat:49",
        notes="`msg *` 群发消息可近似为 wall；/time 等开关无对应，且需相应权限。",
    ),
    ToolMapping(
        win="iexplore",
        linux="xdg-open",
        form="partial",
        confidence="B",
        output_contract=False,
        dangerous=False,
        target_exists="yes",
        evidence="corpus/与某人的QQ临时对话.bat:6",
        notes="仅打开 URL 的场景可近似为默认浏览器；`-new` 等开关无对应，需人工核对。",
    ),
    ToolMapping(
        win="winrar",
        linux="unrar",
        form="partial",
        confidence="B",
        output_contract=False,
        dangerous=False,
        target_exists="unknown",
        evidence="corpus/rar对指定数量的文件进行批量压缩.bat:6",
        notes="仅解压可近似；压缩（a/-cpdelete 等）语义不同，须人工改写。",
    ),
    ToolMapping(
        win="ftp",
        linux="lftp -f",
        form="partial",
        confidence="C",
        output_contract=False,
        dangerous=False,
        target_exists="unknown",
        evidence="corpus/备份文件并上传至FTP服务器.bat:29",
        notes="Windows ftp -s:脚本 与 lftp -f 脚本语法不同，需 API 建议 + 人工确认。",
    ),
    ToolMapping(
        win="ping",
        linux="ping -c",
        form="partial",
        confidence="B",
        output_contract=True,
        dangerous=False,
        target_exists="yes",
        evidence="corpus/让屏幕显示硬件错误的信息（恶搞类）.bat:11",
        notes="开关需转换（/n→-c）；输出格式与 Windows 不同，解析 ping 输出的脚本必须适配。",
    ),
    ToolMapping(
        win="regsvr32",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=True,
        target_exists="no",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:2164",
        notes="COM 组件注册机制在 Linux 无对应物，目标物不存在，保持诚实 TODO。",
    ),
    ToolMapping(
        win="rundll32",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=True,
        target_exists="no",
        evidence="corpus/卸载inf文件.CMD:2",
        notes="调用 DLL 导出函数（如 setupapi）属 Windows 专有机制，目标物不存在。",
    ),
    ToolMapping(
        win="devcon",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=True,
        target_exists="no",
        evidence="corpus/第三方工具/devcon/i386/删除U盘.bat:1",
        notes="设备管理工具，依赖 Windows 驱动模型，目标物不存在。",
    ),
    ToolMapping(
        win="mshta",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=True,
        target_exists="no",
        evidence="corpus/临时运行(bat).bat:3",
        notes="HTA/VBScript 宿主，Linux 无对应物，目标物不存在。",
    ),
    ToolMapping(
        win="msiexec",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=True,
        target_exists="no",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:9128",
        notes="MSI 安装引擎，Linux 包管理语义不同，目标物不存在。",
    ),
    ToolMapping(
        win="gpupdate",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/刷新策略.bat:1",
        notes="组策略刷新，Linux 无对应机制，目标物不存在。",
    ),
    ToolMapping(
        win="regedit",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=True,
        target_exists="no",
        evidence="corpus/lockcmd.bat:32",
        notes="注册表编辑器；写类操作在 Linux 无对应物，目标物不存在，保持诚实 TODO。",
    ),
    ToolMapping(
        win="control",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:456",
        notes="打开控制面板小程序（ncpa.cpl 等），Linux 无对应物，目标物不存在。",
    ),
)


def mapping_for(name: str) -> ToolMapping | None:
    low = name.strip().strip('"').lower()
    if low.endswith(".exe"):
        low = low[:-4]
    for item in WINDOWS_TOOLS:
        if item.win == low:
            return item
    return None
