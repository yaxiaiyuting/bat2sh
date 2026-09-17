"""CFG 只读数据模型（v2.1.0 P4；goto 语义转换的前置基础设施）。

定位
----
cmd 的 ``goto`` 是任意跳转，bash 无对应物；要译对必须先有**控制流图（CFG）**。
本模块在 ``core/control_flow.py``（C4 形态台账）之上，进一步给出**标签位置表**与
**goto→标签边**：方向（前跳/回跳）、目标存在性、是否块内、是否条件、是否冗余、
入边计数、被跳过的区间。它服务 v2.2 的 goto 高级形态（回跳→循环 / 块内 goto），
**本身不驱动任何转换**（``integrated=False``）。

只读纪律
--------
- 本模块**不 import** ``core.batch``，**不被转换器调用**；因此对转换产物**零影响**。
- **纪律 7（不发明映射）**：目标不存在即 ``missing``，动态目标即 ``dynamic``，绝不猜测。
- **纪律 6（置信度光谱）**：形态键复用 C4 台账（A–D），不新增形态。
- **纪律 9（仪器可复现）**：``summarize_cfg`` 与 ``control_flow.summarize_goto_lines``
  在相同输入上**逐计数一致**（由测试守护）。

口径与已知近似
--------------
- **行**：默认 ``build_cfg`` 接收**逻辑行**（``build_cfg_from_text`` 负责 ``^`` 续行累积，
  与 ``batch._logical_lines`` 同口径，测试守护）。
- **块深度**：用**括号净值**近似（与 C4 扫描器一致），**不是**转换器的 ``_Block`` 块栈；
  ``LabelPosition.in_block`` 因此为「扫描器口径」。
- **重复标签**：cmd 语义此处不作断言；为与 C4 台账一致，解析目标取**最后一次**出现的标签，
  重复项由 ``summarize_cfg`` 的 ``duplicate_labels`` 如实暴露（v2.2 决策点）。

设计契约见 ``docs/session-c4-design.md`` §2 Phase 1 与 ``docs/v2.1.0-review.md``。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Sequence

from .control_flow import PRIMARY_SHAPE_KEYS, classify_goto

__all__ = [
    "DIRECTIONS",
    "TARGET_KINDS",
    "Cfg",
    "GotoEdge",
    "LabelPosition",
    "build_cfg",
    "build_cfg_from_text",
    "logical_lines",
    "summarize_cfg",
    "validate_cfg",
]

DIRECTIONS = ("backward", "forward", "self", "none")
TARGET_KINDS = ("label", "eof", "dynamic", "missing")

# 与 ``core/control_flow.py`` 的扫描规则同源（goto 目标 / 标签）。
# CJK 标签受支持；``echo``/``rem`` 行内的 goto 视为数据（见 build_cfg）。
_GOTO_RE = re.compile(r"(?i)(?<![A-Za-z0-9_])@?goto(?:\s*:\s*|\s+)([^\s&|()]+)")
_LABEL_RE = re.compile(r"^\s*:([^\s:&|<>()]+)\s*$")
_STANDALONE_GOTO_RE = re.compile(r"(?i)^\s*@?\s*goto\b")
_EOF_GOTO_RE = re.compile(r"(\^+)$")


@dataclass(frozen=True)
class LabelPosition:
    """一个 ``:label`` 的位置表项。"""

    name: str            # 原始名（大小写保留）
    key: str             # 归一化键（lower）
    line: int            # 行号（逻辑行起始行）
    index: int           # 在逻辑行序列中的下标
    in_block: bool       # 扫描器口径：括号净值 > 0
    incoming: int = 0    # 指向该标签的 goto 边数


@dataclass(frozen=True)
class GotoEdge:
    """一条 ``goto`` 语句到其目标的边。"""

    source_line: int
    source_index: int
    target: str                  # 原样目标 token
    target_key: str              # 归一化键
    target_kind: str             # label / eof / dynamic / missing
    target_line: int | None
    target_index: int | None
    direction: str               # backward / forward / self / none
    in_block: bool
    conditional: bool            # 该 goto 不在行首（if/&/| 复合行内）
    redundant: bool              # 目标即下一条非空非注释行
    shape: str                   # C4 形态键（classify_goto 输出）


@dataclass(frozen=True)
class Cfg:
    """只读控制流图：标签表 + goto 边。"""

    labels: tuple[LabelPosition, ...]
    edges: tuple[GotoEdge, ...]

    @property
    def label_map(self) -> dict[str, tuple[LabelPosition, ...]]:
        """``key -> 该名字的全部位置``（重复标签按出现顺序）。"""
        mapping: dict[str, list[LabelPosition]] = {}
        for position in self.labels:
            mapping.setdefault(position.key, []).append(position)
        return {key: tuple(value) for key, value in mapping.items()}


def logical_lines(text: str) -> list[tuple[int, str]]:
    """把源码按 ``^`` 续行累积为逻辑行；与 ``batch._logical_lines`` 同口径。

    返回 ``(起始行号, 逻辑行文本)`` 列表。
    """
    result: list[tuple[int, str]] = []
    buf = ""
    start = 0
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip("\r")
        if buf:
            line = buf + line
            buf = ""
        else:
            start = number
        stripped = line.rstrip()
        match = _EOF_GOTO_RE.search(stripped)
        if match and len(match.group(1)) % 2 == 1:
            buf = stripped[:-1]
            continue
        result.append((start, line))
    if buf:
        result.append((start, buf))
    return result


def _normalise(target: str) -> str:
    return target.strip().lstrip(":").rstrip(":").lower()


def _first_token(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("@"):
        stripped = stripped[1:].lstrip()
    return stripped.split(None, 1)[0].lower() if stripped else ""


def _is_redundant_tail(lines: Sequence[str], index: int, key: str) -> bool:
    """目标标签是否为 ``lines[index]`` 之后的第一条非空非 ``::`` 行。

    与 ``control_flow.summarize_goto_lines`` 的冗余判定**同口径**。
    """
    for following in lines[index + 1:]:
        candidate = following.strip()
        if not candidate or candidate.startswith("::"):
            continue
        match = _LABEL_RE.match(following)
        return bool(match and match.group(1).lower() == key)
    return False


def build_cfg(lines: Sequence[str], *, start_lines: Sequence[int] | None = None) -> Cfg:
    """从逻辑行构建只读 CFG。

    ``lines`` 为逻辑行文本；``start_lines`` 可选，给出每行对应的源文件行号
    （缺省 ``1..n``）。空行与 ``::`` 注释不产生边；``echo``/``rem`` 行内的 ``goto``
    视为数据（与 C4 扫描器一致）。
    """
    line_numbers = list(start_lines) if start_lines is not None else list(range(1, len(lines) + 1))
    if len(line_numbers) != len(lines):
        raise ValueError("start_lines 与 lines 长度不一致")

    # 括号净值近似：与 C4 扫描器同口径（空行 / ``::`` 不参与深度更新）。
    depths: list[int] = []
    depth = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("::"):
            depths.append(depth)
            continue
        depths.append(depth)
        depth = max(0, depth + stripped.count("(") - stripped.count(")"))

    # 标签表：为与 C4 台账一致，同名的解析目标取最后一次出现。
    resolved: dict[str, int] = {}   # key -> index（最后一次）
    positions: list[LabelPosition] = []
    for index, line in enumerate(lines):
        match = _LABEL_RE.match(line)
        if match and not line.strip().startswith("::"):
            key = match.group(1).lower()
            resolved[key] = index
            positions.append(
                LabelPosition(
                    name=match.group(1),
                    key=key,
                    line=line_numbers[index],
                    index=index,
                    in_block=depths[index] > 0,
                )
            )

    # goto 边。
    edges: list[GotoEdge] = []
    incoming: Counter[str] = Counter()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("::") or _first_token(line) in ("echo", "rem"):
            continue
        for match in _GOTO_RE.finditer(line):
            target = match.group(1)
            key = _normalise(target)
            if "%" in key or "!" in key:
                target_kind = "dynamic"
            elif key == "eof":
                target_kind = "eof"
            elif key not in resolved:
                target_kind = "missing"
            else:
                target_kind = "label"

            target_index = resolved.get(key) if target_kind == "label" else None
            target_line = line_numbers[target_index] if target_index is not None else None
            if target_kind == "label" and target_index is not None:
                direction = "backward" if target_index < index else "forward"
            else:
                direction = "none"

            redundant = (
                target_kind == "label"
                and target_index is not None
                and target_index > index
                and _is_redundant_tail(lines, index, key)
            )
            shape = classify_goto(
                target,
                label_known=target_kind == "label" or target_kind == "eof",
                direction=direction,
                in_block=depths[index] > 0,
                redundant=redundant,
            )
            if target_kind == "label":
                incoming[key] += 1
            edges.append(
                GotoEdge(
                    source_line=line_numbers[index],
                    source_index=index,
                    target=target,
                    target_key=key,
                    target_kind=target_kind,
                    target_line=target_line,
                    target_index=target_index,
                    direction=direction,
                    in_block=depths[index] > 0,
                    conditional=not _STANDALONE_GOTO_RE.match(line),
                    redundant=redundant,
                    shape=shape,
                )
            )

    labels = tuple(replace(position, incoming=incoming.get(position.key, 0)) for position in positions)
    return Cfg(labels=labels, edges=tuple(edges))


def build_cfg_from_text(text: str) -> Cfg:
    """``build_cfg(logical_lines(text))`` 的便捷入口。"""
    logical = logical_lines(text)
    return build_cfg([line for _, line in logical], start_lines=[number for number, _ in logical])


def summarize_cfg(cfg: Cfg) -> dict[str, object]:
    """汇总只读统计（形态 / 方向 / 目标类型 / 多入口 / 重复标签 / 冗余）。"""
    by_shape: Counter[str] = Counter(edge.shape for edge in cfg.edges)
    by_direction: Counter[str] = Counter(edge.direction for edge in cfg.edges)
    by_target: Counter[str] = Counter(edge.target_kind for edge in cfg.edges)
    incoming_by_key: Counter[str] = Counter(
        edge.target_key for edge in cfg.edges if edge.target_kind == "label"
    )
    duplicate_labels = sorted(
        key for key, count in Counter(position.key for position in cfg.labels).items() if count > 1
    )
    multi_entry = sorted(key for key, count in incoming_by_key.items() if count > 1)
    return {
        "labels": len(cfg.labels),
        "labels_in_block": sum(1 for position in cfg.labels if position.in_block),
        "edges": len(cfg.edges),
        "by_shape": dict(by_shape),
        "by_direction": dict(by_direction),
        "by_target_kind": dict(by_target),
        "redundant": sum(1 for edge in cfg.edges if edge.redundant),
        "conditional": sum(1 for edge in cfg.edges if edge.conditional),
        "multi_entry_labels": multi_entry,
        "duplicate_labels": duplicate_labels,
    }


def validate_cfg(cfg: Cfg) -> list[str]:
    """校验 CFG 数据模型的内部一致性（``[]`` = 通过）。

    纪律：每条 goto 必须落入 C4 台账的**互斥主形态**；方向/目标类型/冗余标记必须自洽；
    入边计数必须可由边集重算。**不**把源文件本身的怪癖（如重复标签）当作模型错误。
    """
    problems: list[str] = []
    incoming: Counter[str] = Counter()

    for edge in cfg.edges:
        where = f"cfg.edge[{edge.source_line}:{edge.source_index}:{edge.target}]"
        if edge.source_line < 1:
            problems.append(f"{where}: source_line 必须 >= 1")
        if edge.source_index < 0:
            problems.append(f"{where}: source_index 必须 >= 0")
        if edge.shape not in PRIMARY_SHAPE_KEYS:
            problems.append(f"{where}: shape 不在 C4 主形态集合（{edge.shape!r}）")
        if edge.target_kind not in TARGET_KINDS:
            problems.append(f"{where}: target_kind 非法（{edge.target_kind!r}）")
        if edge.direction not in DIRECTIONS:
            problems.append(f"{where}: direction 非法（{edge.direction!r}）")

        labelled = edge.target_kind == "label"
        if labelled != (edge.target_index is not None):
            problems.append(f"{where}: target_kind 与 target_index 不一致")
        if edge.target_kind in ("eof", "dynamic", "missing") and edge.direction != "none":
            problems.append(f"{where}: 非标签目标的 direction 必须为 none")

        if edge.shape == "eof_exit" and edge.target_kind != "eof":
            problems.append(f"{where}: eof_exit 对应 target_kind 必须为 eof")
        if edge.shape == "dynamic_target" and edge.target_kind != "dynamic":
            problems.append(f"{where}: dynamic_target 对应 target_kind 必须为 dynamic")
        if edge.shape == "missing_label" and edge.target_kind != "missing":
            problems.append(f"{where}: missing_label 对应 target_kind 必须为 missing")
        if edge.shape == "in_block_goto" and not edge.in_block:
            problems.append(f"{where}: in_block_goto 要求 in_block=True")
        if edge.shape == "forward_skip":
            if edge.direction != "forward" or edge.in_block or edge.redundant:
                problems.append(f"{where}: forward_skip 要求 forward 且非块内且非冗余")
        if edge.shape == "backward_loop":
            if edge.direction != "backward" or edge.in_block:
                problems.append(f"{where}: backward_loop 要求 backward 且非块内")
        if edge.shape == "redundant_goto" and not edge.redundant:
            problems.append(f"{where}: redundant_goto 要求 redundant=True")

        if labelled and edge.target_index is not None:
            if edge.target_index < edge.source_index and edge.direction != "backward":
                problems.append(f"{where}: target 在前但 direction != backward")
            if edge.target_index > edge.source_index and edge.direction != "forward":
                problems.append(f"{where}: target 在后但 direction != forward")
            incoming[edge.target_key] += 1

    for position in cfg.labels:
        expected = incoming.get(position.key, 0)
        if position.incoming != expected:
            problems.append(
                f"cfg.label[{position.key}]: incoming={position.incoming} 与边集重算 {expected} 不一致"
            )
    return problems
