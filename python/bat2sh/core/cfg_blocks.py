"""CFG 基本块与流分析（v2.5.0 Stage 1；完整 CFG 状态机的前置图结构）。

定位
----
``core/cfg.py``（v2.1.0）给出**标签位置表**与 **goto 边**；本模块在其上构建
**基本块（BasicBlock）**、**后继/前驱边**、**回边循环**与**多入口**分析。
它是 ``core/cfg_state.py``（v2.5.0 标签分派状态机发射器）的**只读前置**。

只读纪律
--------
- 本模块**不 import** ``core.batch``，**不被默认转换路径调用**（``core.batch`` 仅在
  ``settings.cfg_state_machine`` 为真时才 import 发射器，默认 False）。
- **纪律 7（不发明映射）**：目标不存在即 ``missing``，动态目标即 ``dynamic``，绝不猜测。
- **纪律 9（仪器可复现）**：块划分与边集可由 ``cfg.edges`` / 逻辑行重算，测试守护。

口径与已知近似
--------------
- **行**：接收**逻辑行文本**（与 ``cfg.logical_lines`` / ``batch._logical_lines`` 同口径）。
- **块**：以「首行 / 标签行 / goto 后继行」为 leader 划分连续区间。
- **深度**：沿用 ``cfg`` 的**括号净值**近似（扫描器口径），非转换器的 ``_Block`` 块栈。
- **循环**：仅识别**回边**（``target_index < source_index``）形成的自然循环，不做完整支配分析。

设计见 ``docs/v2.5.0-blockstack-design.md`` §5.2.1。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .cfg import Cfg, build_cfg

__all__ = [
    "BasicBlock",
    "FlowAnalysis",
    "Loop",
    "analyze_flow",
    "analyze_text",
    "build_blocks",
    "detect_loops",
]

# 逻辑行中「整行独立 goto」的判定复用 cfg 的口径（避免第二套正则漂移）。
from .cfg import _GOTO_RE, _STANDALONE_GOTO_RE  # noqa: E402  (只读私有工具)


@dataclass(frozen=True)
class BasicBlock:
    """一段连续逻辑行（leader 起始）。"""

    id: int
    start_index: int          # 首行在逻辑行序列中的下标
    end_index: int            # 末行下标（含）
    start_line: int           # 首行源文件行号
    label: str | None         # 以标签起始时的原始名（否则 None）
    successors: tuple[int, ...]      # 后继块 id
    predecessors: tuple[int, ...]    # 前驱块 id（由边集重算）


@dataclass(frozen=True)
class Loop:
    """一个循环头（header）聚合的自然循环（近似：按回边目标标签归并）。"""

    header_block: int                  # 回边目标所在块 id
    label: str                         # 回边目标标签 key
    backward_edges: int                # 指向该 header 的回边总数
    tail_blocks: tuple[int, ...]       # 所有回边源块 id（升序）


@dataclass(frozen=True)
class FlowAnalysis:
    """完整只读流分析结果。"""

    blocks: tuple[BasicBlock, ...]
    loops: tuple[Loop, ...]
    multi_entry_labels: tuple[str, ...]
    duplicate_labels: tuple[str, ...]
    call_targets: tuple[str, ...]
    goto_targets: tuple[str, ...]
    label_in_block: bool
    has_missing: bool
    has_dynamic: bool


def _first_token(line: str) -> str:
    stripped = line.strip().lstrip("@").lstrip()
    return stripped.split(None, 1)[0].lower() if stripped else ""


def _line_has_goto(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("::") or _first_token(line) in ("echo", "rem"):
        return False
    return bool(_GOTO_RE.search(line))


def build_blocks(cfg: Cfg, lines: Sequence[str]) -> tuple[BasicBlock, ...]:
    """按 leader 划分基本块并计算前驱/后继。

    leader = 首行 ∪ 标签行 ∪ 每个 goto 行之后的首行。
    """
    if len(lines) == 0:
        return ()
    if any(position.index >= len(lines) for position in cfg.labels) or any(
        edge.source_index >= len(lines) for edge in cfg.edges
    ):
        raise ValueError("cfg 与 lines 不一致")

    label_by_index = {position.index: position.name for position in cfg.labels}

    leaders: set[int] = {0}
    for position in cfg.labels:
        leaders.add(position.index)
    for edge in cfg.edges:
        following = edge.source_index + 1
        if following < len(lines):
            leaders.add(following)

    ordered = sorted(leaders)
    blocks: list[BasicBlock] = []
    for order, start in enumerate(ordered):
        end = (ordered[order + 1] - 1) if order + 1 < len(ordered) else len(lines) - 1
        blocks.append(
            BasicBlock(
                id=order,
                start_index=start,
                end_index=end,
                start_line=start + 1,
                label=label_by_index.get(start),
                successors=(),
                predecessors=(),
            )
        )

    # 边：块尾 -> 后继
    block_of_index: dict[int, int] = {}
    for block in blocks:
        for index in range(block.start_index, block.end_index + 1):
            block_of_index[index] = block.id

    successors: dict[int, set[int]] = {block.id: set() for block in blocks}
    for block in blocks:
        last_index = block.end_index
        last_line = lines[last_index]
        taken: set[int] = set()
        if _line_has_goto(last_line):
            stripped = last_line.strip()
            for match in _GOTO_RE.finditer(stripped):
                key = match.group(1).strip().lstrip(":").rstrip(":").lower()
                target = next(
                    (position for position in cfg.labels if position.key == key), None
                )
                if target is not None and target.index in block_of_index:
                    taken.add(block_of_index[target.index])
        if not _STANDALONE_GOTO_RE.match(last_line):
            following = last_index + 1
            if following in block_of_index:
                taken.add(block_of_index[following])
        successors[block.id] = taken

    predecessors: dict[int, set[int]] = {block.id: set() for block in blocks}
    for source, targets in successors.items():
        for target in targets:
            predecessors[target].add(source)

    return tuple(
        BasicBlock(
            id=block.id,
            start_index=block.start_index,
            end_index=block.end_index,
            start_line=block.start_line,
            label=block.label,
            successors=tuple(sorted(successors[block.id])),
            predecessors=tuple(sorted(predecessors[block.id])),
        )
        for block in blocks
    )


def detect_loops(cfg: Cfg, blocks: Sequence[BasicBlock]) -> tuple[Loop, ...]:
    """由**回边**（target_index < source_index）识别自然循环，按目标块归并。"""
    block_of_index: dict[int, int] = {}
    for block in blocks:
        for index in range(block.start_index, block.end_index + 1):
            block_of_index[index] = block.id

    header_of_key = {position.key: position.index for position in cfg.labels}
    grouped: dict[str, list[object]] = {}
    for edge in cfg.edges:
        if edge.target_kind != "label" or edge.target_index is None:
            continue
        if edge.target_index >= edge.source_index:
            continue
        header_index = header_of_key.get(edge.target_key)
        if header_index is None or header_index not in block_of_index:
            continue
        grouped.setdefault(edge.target_key, []).append(edge)

    loops: list[Loop] = []
    for key, edges in grouped.items():
        header_index = header_of_key[key]
        header_block = block_of_index[header_index]
        tail_blocks = sorted(
            {
                block_of_index[edge.source_index]
                for edge in edges
                if edge.source_index in block_of_index
            }
        )
        loops.append(
            Loop(
                header_block=header_block,
                label=key,
                backward_edges=len(edges),
                tail_blocks=tuple(tail_blocks),
            )
        )
    loops.sort(key=lambda loop: (loop.header_block, loop.label))
    return tuple(loops)


def analyze_flow(cfg: Cfg, lines: Sequence[str] | None = None) -> FlowAnalysis:
    """汇总流分析（块/循环/多入口/重复标签/call·goto 目标/入口障碍）。"""
    if lines is None:
        lines = ["" for _ in range(max((e.source_index for e in cfg.edges), default=-1) + 1)]

    blocks = build_blocks(cfg, lines)
    loops = detect_loops(cfg, blocks)

    incoming: dict[str, int] = {}
    for edge in cfg.edges:
        if edge.target_kind == "label":
            incoming[edge.target_key] = incoming.get(edge.target_key, 0) + 1
    multi_entry = tuple(sorted(key for key, count in incoming.items() if count > 1))

    duplicate = tuple(
        sorted(
            {
                position.key
                for position in cfg.labels
                if sum(1 for other in cfg.labels if other.key == position.key) > 1
            }
        )
    )

    call_targets: set[str] = set()
    goto_targets: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered.startswith("call") and ":" in stripped:
            token = stripped.split(":", 1)[1].split()[0] if ":" in stripped else ""
            if token:
                call_targets.add(token.strip().lower())
        for match in _GOTO_RE.finditer(stripped):
            key = match.group(1).strip().lstrip(":").rstrip(":").lower()
            if key != "eof":
                goto_targets.add(key)
        if lowered.startswith("if") and "goto" in lowered:
            for match in _GOTO_RE.finditer(stripped):
                key = match.group(1).strip().lstrip(":").rstrip(":").lower()
                if key != "eof":
                    goto_targets.add(key)

    return FlowAnalysis(
        blocks=blocks,
        loops=loops,
        multi_entry_labels=multi_entry,
        duplicate_labels=duplicate,
        call_targets=tuple(sorted(call_targets)),
        goto_targets=tuple(sorted(goto_targets)),
        label_in_block=any(position.in_block for position in cfg.labels),
        has_missing=any(edge.target_kind == "missing" for edge in cfg.edges),
        has_dynamic=any(edge.target_kind == "dynamic" for edge in cfg.edges),
    )


def analyze_text(text: str) -> tuple[Cfg, FlowAnalysis, list[str]]:
    """便捷入口：从源码文本构建 CFG + 流分析（逻辑行文本一并返回）。"""
    from .cfg import logical_lines

    logical = logical_lines(text)
    lines = [line for _, line in logical]
    cfg = build_cfg(lines, start_lines=[number for number, _ in logical])
    return cfg, analyze_flow(cfg, lines), lines
