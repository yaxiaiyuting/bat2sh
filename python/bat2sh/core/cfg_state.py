"""CFG 标签分派状态机发射器（v2.5.0 Stage 2；**门控 + 默认关闭**）。

定位
----
把「goto 任意跳转」翻译为 **标签分派状态机**：保留块内结构化（`if/fi`、`for/done`），
但在**标签处切分**为 `case` 臂，用 `$__bat2sh_pc` 驱动任意跳转：

.. code-block:: bash

    __bat2sh_pc=__bat2sh_start
    while :; do
      case ${__bat2sh_pc} in
      __bat2sh_start)
          <文件头到首个标签>
          __bat2sh_pc=__L_1; continue ;;
      __L_1)  # :Label1
          <Label1 到下一标签>
          __bat2sh_pc=__L_2; continue ;;
      ...
      __bat2sh_exit) exit 0 ;;
      esac
    done

- `goto Lx` → `__bat2sh_pc=__L_x; continue`（块内则 `continue N`，N = 包裹循环数 + 1）。
- `goto :eof` → 沿用既有 `exit 0` / `return`。

实现方式（**零改写** `_label_line`/块栈）
----------------------------------------
本模块**子类化** ``BatchConverter``，仅**覆写** ``_prescan`` / ``_label_line`` /
``_convert_goto`` / ``_finish``（外加 ``_indent`` 缩进）。原类（含 053 修复的块栈发射层）
**逐字节不改**；分派模式只在**门控命中**时由子类实例启用。因此：

- 未命中文件：走原 ``BatchConverter``，产物与 v2.4.0 **逐字节相同**（053 最强保护）。
- 命中文件：走 ``_DispatchConverter``，旧块栈机制仍用于块内结构，仅标签/goto 改由分派处理。

门控（保守，纪律 1）
-------------------
只有同时满足下列全部条件才发射，否则返回 ``None``（回退原路径）：

1. 存在至少一条 **goto → 标签** 边；
2. 无 ``missing`` / ``dynamic`` 目标（无静态安全映射，纪律 7）；
3. 无重复标签；
4. 无块内标签（``label_in_block``；须提升/扁平化，属编译器级 → 诚实 TODO）；
5. **无 `call :label`**（避免函数通道与分派臂交织）；
6. 产物结构自检通过（所有引用的臂均已定义、`bash -n` 通过）。

设计见 ``docs/v2.5.0-blockstack-design.md`` §5.2.2 / §5.3-B。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .batch import BatchConverter
from .cfg import build_cfg, logical_lines
from .cfg_blocks import analyze_flow
from .settings import ConvertSettings
from .syntax import bash_syntax_error
from .types import ConvertReport, Diagnostic

__all__ = ["Eligibility", "evaluate", "emit"]

_LABEL_RE = re.compile(r"^:([A-Za-z0-9_][\w.\-]*)\s*$")
_GOTO_RE = re.compile(r"(?i)^goto(?:\s*:\s*|\s+)([\w.\-]+)\s*$")
_INTERACTIVE_RE = re.compile(r"(?i)^\s*@?\s*(?:set\s*/p\b|pause\b|choice\b)")

_PC_VAR = "__bat2sh_pc"
_ARM_START = "__bat2sh_start"
_ARM_EXIT = "__bat2sh_exit"
_ARM_INDENT = "    "
_CASE_INDENT = "  "


@dataclass(frozen=True)
class Eligibility:
    ok: bool
    reasons: tuple[str, ...] = ()
    label_edges: int = 0


def _ordered_labels(lines: list[str]) -> list[str]:
    seen: list[str] = []
    seen_set: set[str] = set()
    for line in lines:
        match = _LABEL_RE.match(line.strip())
        if not match:
            continue
        key = match.group(1).lower()
        if key not in seen_set:
            seen_set.add(key)
            seen.append(key)
    return seen


def evaluate(text: str) -> Eligibility:
    """门控判定（只读，不发射）。"""
    logical = logical_lines(text)
    lines = [line for _, line in logical]
    flow = analyze_flow_from(lines)
    reasons: list[str] = []

    label_edges = flow["label_edges"]
    if label_edges == 0:
        reasons.append("no_label_edges")
    if flow["has_missing"]:
        reasons.append("missing_label")
    if flow["has_dynamic"]:
        reasons.append("dynamic_target")
    if flow["duplicate_labels"]:
        reasons.append("duplicate_labels")
    if flow["label_in_block"]:
        reasons.append("label_in_block")
    if flow["call_targets"]:
        reasons.append("call_targets")

    return Eligibility(ok=not reasons, reasons=tuple(reasons), label_edges=label_edges)


def analyze_flow_from(lines: list[str]) -> dict[str, object]:
    from .cfg import build_cfg

    cfg = build_cfg(lines, start_lines=list(range(1, len(lines) + 1)))
    flow = analyze_flow(cfg, lines)
    label_edges = sum(1 for edge in cfg.edges if edge.target_kind == "label")
    return {
        "has_missing": flow.has_missing,
        "has_dynamic": flow.has_dynamic,
        "duplicate_labels": flow.duplicate_labels,
        "label_in_block": flow.label_in_block,
        "call_targets": flow.call_targets,
        "label_edges": label_edges,
    }


class _DispatchConverter(BatchConverter):
    """标签分派状态机转换器（仅在门控命中时使用）。"""

    def __init__(self, settings: ConvertSettings, source_name: str = "input.bat") -> None:
        super().__init__(replace(settings, cfg_state_machine=False), source_name)
        self._dispatch_ready = False
        self._label_ids: dict[str, str] = {}

    # 缩进：分派模式在臂体内额外缩进一层（可读性；不影响语义）
    @property
    def _indent(self) -> str:
        depth = len(self._stack) + (1 if self._current_func else 0)
        base = _ARM_INDENT if self._dispatch_ready else ""
        return base + self.settings.indent * depth

    def _prescan(self, logical: list[tuple[int, str]]) -> None:
        for key in _ordered_labels([line for _, line in logical]):
            self._label_ids.setdefault(key, f"__L_{len(self._label_ids) + 1}")
        super()._prescan(logical)
        self._dispatch_ready = True
        self._out.extend(
            [
                f"{_PC_VAR}={_ARM_START}",
                "while :; do",
                f"{_CASE_INDENT}case ${{{_PC_VAR}}} in",
                f"{_CASE_INDENT}{_ARM_START})",
            ]
        )

    def _label_line(self, lineno: int, name: str) -> list[str]:
        key = name.lower()
        arm = self._label_ids.get(key)
        if arm is None:
            return super()._label_line(lineno, name)
        # 闭合上一臂（落空 → 本臂）并开启本臂
        return [
            f"{_ARM_INDENT}{_PC_VAR}={arm}; continue",
            f"{_ARM_INDENT};;",
            f"{_CASE_INDENT}{arm})  # :{name}",
        ]

    def _convert_goto(self, lineno: int, text: str) -> list[str]:
        match = _GOTO_RE.match(text)
        if match and match.group(1).lower() != "eof":
            arm = self._label_ids.get(match.group(1).lower())
            if arm is not None:
                loops = sum(1 for block in self._stack if block.close_word == "done")
                keyword = "continue" if loops == 0 else f"continue {loops + 1}"
                return [self._c(f"{_PC_VAR}={arm}; {keyword}")]
        return super()._convert_goto(lineno, text)

    def _finish(self) -> None:
        super()._finish()
        self._out.extend(
            [
                f"{_ARM_INDENT}{_PC_VAR}={_ARM_EXIT}; continue",
                f"{_ARM_INDENT};;",
                f"{_CASE_INDENT}{_ARM_EXIT}) exit 0 ;;",
                f"{_CASE_INDENT}esac",
                "done",
            ]
        )


def _structural_self_check(output: str) -> bool:
    """自检：所有被引用的臂 id 均已定义（`ARM)  # :` 形式）。防「跳到未定义臂 → 死循环」。"""
    defined = set(re.findall(r"^\s*(__L_\d+|__bat2sh_start|__bat2sh_exit)\)", output, re.M))
    referenced = set(re.findall(rf"{_PC_VAR}=(__L_\d+|__bat2sh_exit)", output))
    return referenced <= defined


def _warn_interactive_loops(text: str, report: ConvertReport) -> None:
    """对「含运行时输入语句的循环」发**非阻断**告警（无 stdin 环境会挂起）。"""
    logical = logical_lines(text)
    lines = [line for _, line in logical]
    cfg = build_cfg(lines, start_lines=[number for number, _ in logical])
    flow = analyze_flow(cfg, lines)
    block_by_id = {block.id: block for block in flow.blocks}
    for loop in flow.loops:
        header = block_by_id.get(loop.header_block)
        if header is None:
            continue
        for tail_id in loop.tail_blocks:
            tail = block_by_id.get(tail_id)
            if tail is None:
                continue
            region = lines[header.start_index: tail.end_index + 1]
            if any(_INTERACTIVE_RE.search(line) for line in region):
                report.warnings.append(
                    Diagnostic(
                        header.start_line,
                        f"循环 :{loop.label} 依赖运行时输入（交互式）；无 stdin 环境会挂起",
                        "",
                        "control_flow",
                    )
                )
                break


def emit(
    text: str,
    settings: ConvertSettings,
    source_name: str = "input.bat",
    report: ConvertReport | None = None,
) -> str | None:
    """尝试发射状态机产物；门控不命中或自检失败返回 ``None``（回退原路径）。"""
    decision = evaluate(text)
    if not decision.ok:
        return None

    if report is not None:
        _warn_interactive_loops(text, report)

    converter = _DispatchConverter(settings, source_name)
    try:
        output = converter.convert(text)
    except Exception:  # pragma: no cover - 保守回退，绝不半成品
        return None

    # 若转换器自身判定为语法降级（整体注释），说明状态机产物有问题 → 回退
    if any(diag.category == "syntax" for diag in converter.report.errors):
        return None
    if not _structural_self_check(output):
        return None
    if bash_syntax_error(output) is not None:  # pragma: no cover - 契约兜底
        return None
    return output
