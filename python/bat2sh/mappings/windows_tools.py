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
    ToolMapping(
        win="graftabl",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/修改GB搜索引擎.bat:6",
        notes="代码页字形加载（DOS 时代），Linux 无对应机制，目标物不存在。",
    ),
    ToolMapping(
        win="debug",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/右键菜单/复制路径.bat:395",
        notes="DOS 调试器，Linux 无对应物，目标物不存在。",
    ),
    ToolMapping(
        win="defrag",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=True,
        target_exists="no",
        evidence="corpus/碎片整理.bat:1",
        notes="Windows 碎片整理，目标物不存在（Linux 文件系统无需）。",
    ),
    ToolMapping(
        win="regini",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=True,
        target_exists="no",
        evidence="corpus/注册表/注册表权限设置.bat:44",
        notes="注册表脚本权限编辑器，Linux 无对应物，目标物不存在。",
    ),
    ToolMapping(
        win="mountvol",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=True,
        target_exists="no",
        evidence="corpus/一键转移桌面-收藏夹-文档多用户版.bat:19",
        notes="Windows 卷挂载管理，Linux 无对应物，目标物不存在。",
    ),
    ToolMapping(
        win="cmdow",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/第三方工具/CMDOW/HOTFIX.CMD:1",
        notes="第三方 Windows 窗口操控工具，目标物不存在。",
    ),
    ToolMapping(
        win="csty",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/第三方工具/CSty/普及讲解CSty.bat:10",
        notes="语料自带 Windows 控制台工具，目标物不存在。",
    ),
    ToolMapping(
        win="keyprs",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/第三方工具/KeyPrs/普及讲解KeyPrs.bat:9",
        notes="语料自带 Windows 按键模拟工具，目标物不存在。",
    ),
    ToolMapping(
        win="finfo",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/第三方工具/finfo/普及讲解Finfo.bat:12",
        notes="第三方 Windows 文件信息工具，目标物不存在。",
    ),
    ToolMapping(
        win="cido",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/第三方工具/第三方工具CIdo/普及讲解CIdo.bat:16",
        notes="语料自带 Windows 工具（beep 等），目标物不存在。",
    ),
    ToolMapping(
        win="nconvert",
        linux="nconvert",
        form="partial",
        confidence="B",
        output_contract=False,
        dangerous=False,
        target_exists="unknown",
        evidence="corpus/第三方工具/图片处理/批量将jpg变为bmp.bat:3",
        notes="XnView 提供 Linux 版 nconvert，需自行安装；开关语义请核对，未安装则不可用。",
    ),
    ToolMapping(
        win="rasdial",
        linux="nmcli",
        form="partial",
        confidence="C",
        output_contract=False,
        dangerous=False,
        target_exists="unknown",
        evidence="corpus/宽带连接.bat:1",
        notes="PPP 拨号可近似为 nmcli/pon，需凭据与权限，语义不完全等价，需人工确认。",
    ),
    ToolMapping(
        win="subst",
        linux="mount --bind",
        form="partial",
        confidence="C",
        output_contract=False,
        dangerous=False,
        target_exists="unknown",
        evidence="corpus/将文件夹变为磁盘.bat:6",
        notes="虚拟盘符可近似为 mount --bind，需特权且语义不同，需人工确认。",
    ),
    ToolMapping(
        win="tree",
        linux="tree",
        form="partial",
        confidence="B",
        output_contract=False,
        dangerous=False,
        target_exists="unknown",
        evidence="corpus/用日期管理你的文件/自动删除空文件夹并生成文件列表.bat:3",
        notes="Arch 需另装 tree 包（pacman -S tree）；Windows /F 与 Linux -f 语义不同，"
        "目标物视环境而定，请人工核对。",
    ),
    ToolMapping(
        win="ipseccmd",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=True,
        target_exists="no",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:10377",
        notes="Windows IPsec 策略命令行工具，Linux 用 ip xfrm/nft 语义不同，目标物不存在。",
    ),
    ToolMapping(
        win="tskill",
        linux="pkill",
        form="partial",
        confidence="C",
        output_contract=False,
        dangerous=True,
        target_exists="unknown",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:11373",
        notes="结束进程可近似 kill/pkill，PID/名称匹配与权限语义不同，需 API 建议 + 人工确认。",
    ),
    ToolMapping(
        win="netsh",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=True,
        target_exists="no",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:10288",
        notes="Windows 网络配置套件（advfirewall/interface ip），Linux 无单一对应物，目标物不存在。",
    ),
    ToolMapping(
        win="at",
        linux="systemd-run",
        form="partial",
        confidence="C",
        output_contract=False,
        dangerous=True,
        target_exists="unknown",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:766",
        notes="计划任务可近似 systemd-run --on-calendar（或 at+atd），调度语法差异大，"
        "需 API 建议 + 人工确认。",
    ),
    ToolMapping(
        win="arp",
        linux="ip neigh",
        form="partial",
        confidence="C",
        output_contract=False,
        dangerous=True,
        target_exists="unknown",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:5718",
        notes="静态 ARP 项可近似 ip neigh add；显示（-a）/删除语义与特权要求不同，"
        "需 API 建议 + 人工确认。",
    ),
    ToolMapping(
        win="explorer",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/第三方工具/wselect-双击选择文件（夹）/原版.bat:9",
        notes="Windows 桌面外壳（打开目录属 GUI 行为），Linux 无命令行等价物，目标物不存在。",
    ),
    ToolMapping(
        win="beenotice",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/第三方工具/BeeNotice - 显示文字到屏幕上/BeeNotice.bat:1",
        notes="语料自带 Windows 气泡提示工具（.exe 后缀由 mapping_for 剥离），目标物不存在。",
    ),
    ToolMapping(
        win="chkntfs",
        linux="",
        form="none",
        confidence="D",
        output_contract=False,
        dangerous=False,
        target_exists="no",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:2064",
        notes="NTFS 自检与自动检查时间设置，Linux 无对应物（fsck.ntfs 语义不同），目标物不存在。",
    ),
    ToolMapping(
        win="help",
        linux="man",
        form="partial",
        confidence="C",
        output_contract=True,
        dangerous=False,
        target_exists="yes",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:13565",
        notes="Windows 内建帮助 → man：输出格式完全不同（内建命令帮助 vs man 页面），"
        "无参数时行为差异大，需 API 建议 + 人工确认。",
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
