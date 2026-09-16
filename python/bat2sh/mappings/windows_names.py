"""bat2sh Windows **名称**映射子系统（B1，v1.10.0a1）。

与既有两张表并列的第三张表：

* ``mappings/windows_tools.py`` —— Windows **命令** → Linux 命令；
* ``core/registry_map.py`` —— **注册表键路径** → Linux 只读探针；
* **本模块** —— 同一个东西在另一边的**名字**：环境变量 / 路径根 / 服务名。

设计要点（对齐 ``windows_tools.py`` 的纪律）：

1. **单一数据源**：新增/修正的 Windows→Linux **名称**映射以本表为准。
2. **``evidence`` 必填**（纪律 7：不发明映射），格式 ``corpus/<name>:<line>``，
   必须指向真实语料行；``validate_name_mappings()`` 在测试中守护。
3. **降级策略**：凡不能给出有依据 Linux 名的（``form="none"`` 或 ``integrated=False``）
   一律由转换器降级为**诚实 TODO/警告**，不得硬凑（纪律 1）。
4. **登记 ≠ 集成**：``integrated=False`` 表示「本版只登记，不驱动转换」（backlog），
   其 ``notes`` 必须写明 ``backlog``，避免「表里有但没生效」的错觉。

首批（本版）范围 = **C3 路径/环境**（不含 ``sc→systemctl``；C7 已后移 v2.0）：

* ``env_var`` —— ``ProgramFiles``（无对应物 → 诚实 TODO）、``AllUsersProfile``（→ ``/usr/share``）；
* ``path_root`` —— 盘符（``drive``）与 UNC 共享（``unc``）**仅登记**（churn 实测见
  ``docs/session-b1b2-review.md`` §2.2：盘符 35 文件 / 其中 6 个功能完好）。

服务名（``service``）kind 已在 schema 中预留，但**本版不落条目**——1.x 无 ``sc→systemctl``
宿主（C7/v2.0），且没有任何「服务名 → systemd unit」的有依据映射（纪律 7）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .windows_tools import CONFIDENCES, FORMS, TARGET_EXISTS

#: 名称类别：环境变量 / 路径根 / 服务名
NAME_KINDS = ("env_var", "path_root", "service")
#: 路径根子类（用于 evidence/notes 自检）
PATH_ROOT_SUBTYPES = ("drive", "unc")

_EVIDENCE_RE = re.compile(r"^corpus/.+:\d+$")
_ENV_TOKEN_RE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")


@dataclass(frozen=True)
class NameMapping:
    """一条「Windows 名 → Linux 名」的映射记录。

    ``integrated=False`` 表示本版只登记、不驱动转换（backlog）。
    """

    win: str
    kind: str
    linux: str
    form: str
    confidence: str
    target_exists: str
    evidence: str
    integrated: bool = True
    notes: str = ""


def validate_name_mappings(entries: tuple[NameMapping, ...] | None = None) -> list[str]:
    """返回全部违规描述；空列表表示通过。

    规则：
    * ``evidence`` 必填且格式为 ``corpus/<name>:<line>``（纪律 7）；
    * ``kind`` / ``form`` / ``confidence`` / ``target_exists`` 取值合法；
    * ``confidence == "D"`` ⇒ ``form == "none"`` 且 ``linux`` 为空（不得硬凑组合）；
    * ``form == "none"`` ⇒ ``notes`` 含「无对应物」；
    * ``target_exists == "no"`` ⇒ ``notes`` 含「目标物不存在」；
    * ``integrated is False`` ⇒ ``notes`` 含「backlog」（登记与集成必须可区分）；
    * ``kind == "service"`` 且 ``form != "none"`` ⇒ ``notes`` 含「systemd」（服务名必须落到 unit）；
    * ``kind == "path_root"`` ⇒ ``win`` 必须是 ``drive``/``unc`` 子类伪名（约定可机检）；
    * ``(kind, win.lower())`` 不得重复。
    """
    items = WINDOWS_NAMES if entries is None else entries
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(items):
        tag = f"[{index}] {item.kind}:{item.win or '<empty>'}"
        if not _EVIDENCE_RE.match(item.evidence):
            errors.append(f"{tag}: evidence 缺失或格式错误（应为 corpus/<name>:<line>）")
        if item.kind not in NAME_KINDS:
            errors.append(f"{tag}: kind 非法 {item.kind!r}")
        if item.form not in FORMS:
            errors.append(f"{tag}: form 非法 {item.form!r}")
        if item.confidence not in CONFIDENCES:
            errors.append(f"{tag}: confidence 非法 {item.confidence!r}")
        if item.target_exists not in TARGET_EXISTS:
            errors.append(f"{tag}: target_exists 非法 {item.target_exists!r}")
        if item.confidence == "D" and (item.form != "none" or item.linux):
            errors.append(f"{tag}: confidence D 必须 form=none 且 linux 为空（不得硬凑组合）")
        if item.form == "none" and "无对应物" not in item.notes:
            errors.append(f"{tag}: form=none 必须在 notes 说明「无对应物」")
        if item.target_exists == "no" and "目标物不存在" not in item.notes:
            errors.append(f"{tag}: target_exists=no 必须在 notes 标注「目标物不存在」")
        if not item.integrated and "backlog" not in item.notes:
            errors.append(f"{tag}: integrated=False 必须在 notes 标注 backlog（登记未生效）")
        if item.kind == "service" and item.form != "none" and "systemd" not in item.notes:
            errors.append(f"{tag}: service 映射必须在 notes 指明 systemd unit")
        if item.kind == "path_root" and item.win.lower() not in PATH_ROOT_SUBTYPES:
            errors.append(
                f"{tag}: path_root 的 win 必须是子类伪名 {'/'.join(PATH_ROOT_SUBTYPES)}"
            )
        key = (item.kind, item.win.lower())
        if key in seen:
            errors.append(f"{tag}: (kind, win) 重复")
        seen.add(key)
    return errors


#: 首批映射条目（B1，v1.10.0a1）。
#:
#: 范围 = C3 路径/环境（不含 sc→systemctl；C7 已后移 v2.0）。
#: * ``env_var``：新增**未在** ``rules.BATCH_ENV_MAP`` 中的 Windows 专有变量，
#:   避免与既有映射双源冲突（``test_env_map_consistency`` 守护）。
#: * ``path_root``：``drive``/``unc`` 使用子类**伪名**；本版 ``integrated=False``
#:   （仅登记，不驱动转换）——churn 实测见 docs/session-b1b2-review.md §2.2。
WINDOWS_NAMES: tuple[NameMapping, ...] = (
    NameMapping(
        win="ProgramFiles",
        kind="env_var",
        linux="",
        form="none",
        confidence="C",
        target_exists="no",
        evidence="corpus/史上最牛X批处理工具包09年7月11日更新版.bat:9933",
        integrated=True,
        notes="Windows 程序安装根目录（%ProgramFiles%）在 Linux 无对应物——"
        "发行版布局并存（/usr、/opt、/usr/local 语义不同），硬映射会产出"
        "「看似对、实际错」的路径；目标物不存在。",
    ),
    NameMapping(
        win="AllUsersProfile",
        kind="env_var",
        linux="/usr/share",
        form="partial",
        confidence="C",
        target_exists="unknown",
        evidence="corpus/快速清理垃圾文件安装修改版/快速清理垃圾文件.bat:15",
        integrated=True,
        notes="%AllUsersProfile% 即 C:\\ProgramData，与既有规则表 "
        'BATCH_ENV_MAP["PROGRAMDATA"]="/usr/share" 保持一致（非发明）；'
        "共享数据目录的子布局不同，需人工核对。",
    ),
    NameMapping(
        win="drive",
        kind="path_root",
        linux="",
        form="none",
        confidence="C",
        target_exists="no",
        evidence="corpus/注册表/导出注册表的键值2.bat:1",
        integrated=False,
        notes="Windows 盘符根（C:\\、D:\\…）在 Linux 无对应物（挂载点由 fstab/systemd 决定）；"
        "本版仅登记（backlog）：诚实 TODO 化会触及 35 个语料文件、其中 6 个当前功能完好，"
        "超出 B1 首批边界（docs/session-b1b2-review.md §2.2）；目标物不存在。",
    ),
    NameMapping(
        win="unc",
        kind="path_root",
        linux="",
        form="none",
        confidence="C",
        target_exists="no",
        evidence="corpus/注册表/设注册表某个键的键值为变量2.bat:3",
        integrated=False,
        notes="UNC 共享路径（\\\\host\\share）在 Linux 无对应物（需先 mount/SMB）；"
        "本版仅登记（backlog）：语料证据为同族 \\\\ 前缀路径（WMI namespace），"
        "当前产物会拼坏（\\\\/host/share）；目标物不存在。",
    ),
)


def name_mapping_for(
    name: str,
    kind: str | None = None,
    entries: tuple[NameMapping, ...] | None = None,
) -> NameMapping | None:
    """按名字（大小写不敏感，自动剥离 ``%`` 与 ``.exe``）查找映射记录。"""
    items = WINDOWS_NAMES if entries is None else entries
    low = name.strip().strip('"').strip("%").lower()
    if low.endswith(".exe"):
        low = low[:-4]
    for item in items:
        if item.win.lower() == low and (kind is None or item.kind == kind):
            return item
    return None


def env_mapping_for(
    name: str, entries: tuple[NameMapping, ...] | None = None
) -> NameMapping | None:
    """查找 ``kind="env_var"`` 的记录（``name`` 可带 ``%``）。"""
    return name_mapping_for(name, kind="env_var", entries=entries)


def path_root_mapping_for(
    token: str, entries: tuple[NameMapping, ...] | None = None
) -> NameMapping | None:
    """判断一个路径 token 是否为已登记的 Windows 路径根（盘符 / UNC）。

    仅做**识别**，不产出替换文本；调用方决定降级方式（本版不集成盘符/UNC 转换）。
    """
    items = WINDOWS_NAMES if entries is None else entries
    stripped = token.strip().strip("\"'")
    matched: list[str] = []
    if re.match(r"(?i)^[a-z]:[\\/]", stripped):
        matched.append("drive")
    if stripped.startswith("\\\\"):
        matched.append("unc")
    if not matched:
        return None
    for subtype in matched:
        for item in items:
            if item.kind == "path_root" and item.win.lower() == subtype:
                return item
    return None


def unmappable_env_names_in(
    text: str, entries: tuple[NameMapping, ...] | None = None
) -> list[str]:
    """返回 ``text`` 中命中「无对应物」环境变量的名字（去重、保序）。

    供转换器做**行级诚实 TODO**：命中即说明该行无法静态正确翻译。

    与 ``_expand_vars`` 保持同序：先把 ``%%`` 掩掉再扫描，
    以免把 ``%%ProgramFiles%%``（转义后的字面量）误判为变量引用。
    """
    items = WINDOWS_NAMES if entries is None else entries
    found: list[str] = []
    seen: set[str] = set()
    masked = text.replace("%%", "\x00")
    for match in _ENV_TOKEN_RE.finditer(masked):
        name = match.group(1)
        if name.upper() in seen:
            continue
        entry = env_mapping_for(name, entries=items)
        if entry is not None and entry.form == "none":
            seen.add(name.upper())
            found.append(name)
    return found
