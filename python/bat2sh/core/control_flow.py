"""C4 goto 控制流形态台账（只读基础设施，v1.10.0b1）。

定位
----
cmd 的 ``goto`` 是**任意跳转**（前跳/回跳/跳出/跳入控制块/动态目标），bash 无对应物；
要译对必须先做**控制流图（CFG）**分析。路线图把 C4 评为 1.x 单点最大（~250 TODO）、
风险最高，明确归 **v2.0**（``docs/v1.x-roadmap-research.md`` §1.C4、§2.2、§3.1、F1）。

本模块**不驱动任何转换**（``integrated=False``）：它把语料实测到的 goto 形态固化为
**带 ``evidence`` 的结构化台账**，供 v2.0 的 CFG/状态机使用，并防止「反复评估」
（路线图 §5 指出的问题）。设计契约见 ``docs/session-c4-design.md``。

第四张表
--------
``mappings/windows_tools.py``（命令） / ``mappings/windows_names.py``（名称） /
``mappings/output_contracts.py``（输出契约）之外，本模块是**控制流形态表**。

纪律
----
- **纪律 7（不发明映射 / 缺 evidence 拒绝）**：每条形态必须带真实语料 ``文件:行``；
  ``validate_control_flow_patterns()`` 在测试中守护。
- **纪律 6（置信度光谱）**：A=已实现且经语料/黄金对照验证；B=可直接用（但无余量）；
  C=需适配；D=不可自动转换（维持诚实 TODO）。
- **纪律 1（保守 TODO）**：不可证安全的形态一律 ``convertible=False``，由现有诚实 TODO 兜底。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

__all__ = [
    "CONFIDENCE_LEVELS",
    "ControlFlowPattern",
    "GOTO_PATTERNS",
    "PRIMARY_SHAPE_KEYS",
    "classify_goto",
    "pattern_for",
    "summarize_goto_lines",
    "validate_control_flow_patterns",
]

CONFIDENCE_LEVELS = ("A", "B", "C", "D")

_DIRECTIONS = ("backward", "forward", "self", "both", "none")
_LOCATIONS = ("top_level", "in_block", "both", "unknown")
_CONDITIONALITY = ("conditional", "unconditional", "both", "none")
_TARGET_KINDS = ("label", "eof", "dynamic", "missing")

_GOTO_RE = re.compile(r"(?i)(?<![A-Za-z0-9_])@?goto(?:\s*:\s*|\s+)([^\s&|()]+)")
_LABEL_RE = re.compile(r"^\s*:([^\s:&|<>()]+)\s*$")
_EVIDENCE_RE = re.compile(r"^.+:\d+$")


@dataclass(frozen=True)
class ControlFlowPattern:
    """一条 goto/控制流形态的台账记录。

    ``corpus_statements`` / ``corpus_files`` 为**扫描器实测值**
    （``summarize_goto_lines``，echo 与 ``rem`` 行不计；标签支持 CJK）。
    ``primary`` = 该键是 ``classify_goto`` 的互斥输出之一。
    """

    key: str
    description: str
    direction: str
    location: str
    conditionality: str
    target_kind: str
    corpus_statements: int
    corpus_files: int
    confidence: str
    integrated: bool
    convertible: bool
    plan: str
    evidence: str
    notes: str
    primary: bool = True


GOTO_PATTERNS: tuple[ControlFlowPattern, ...] = (
    ControlFlowPattern(
        key="eof_exit",
        description="goto :eof（顶层退出 / 函数内返回）",
        direction="none",
        location="both",
        conditionality="both",
        target_kind="eof",
        corpus_statements=93,
        corpus_files=20,
        confidence="A",
        integrated=True,
        convertible=True,
        plan="顶层 → exit 0；函数内 → return（已实现：core/batch.py:1625-1628）",
        evidence="xp下确定最后的盘符.bat:10",
        notes="本轮唯一已实现且经 151 语料回归的形态；v1.10.0b1 不改动。",
    ),
    ControlFlowPattern(
        key="forward_skip",
        description="前向 goto：跳过一段代码到后续标签",
        direction="forward",
        location="top_level",
        conditionality="both",
        target_kind="label",
        corpus_statements=551,
        corpus_files=26,
        confidence="D",
        integrated=False,
        convertible=False,
        plan="v2.4.0 已实现保守子集：无条件顶层 goto 且区间内无标签样行 → 区间不可达，逐行注释化；一般前跳仍 D 档诚实 TODO",
        evidence="获取某路径下的所有文件名.cmd:21",
        notes="可达性证明见 docs/v2.4.0-review.md：区间内无标签样行（含 CJK）则无跳转入口；条件/块内/含标签区间一律不转换（保留诚实 TODO）。",
    ),
    ControlFlowPattern(
        key="backward_loop",
        description="回跳 goto：指向已执行过的标签（重试/菜单循环）",
        direction="backward",
        location="top_level",
        conditionality="both",
        target_kind="label",
        corpus_statements=446,
        corpus_files=28,
        confidence="D",
        integrated=False,
        convertible=False,
        plan="v2.0 CFG：回跳 → while/until；需识别循环不变式与出口条件",
        evidence="带密码的批处理.bat:14",
        notes="出口常依赖 errorlevel/输入变量，静态不可全知（纪律 1）。",
    ),
    ControlFlowPattern(
        key="in_block_goto",
        description="控制块内的 goto（for/if 体内）",
        direction="both",
        location="in_block",
        conditionality="both",
        target_kind="label",
        corpus_statements=457,
        corpus_files=8,
        confidence="D",
        integrated=False,
        convertible=False,
        plan="v2.0：先块栈配平，再把块内跳转映射 break/continue/函数",
        evidence="xp下确定最后的盘符.bat:7",
        notes="与 053 同域；for/f 体含 goto 当前整行 TODO（core/batch.py:2300-2307）。",
    ),
    ControlFlowPattern(
        key="redundant_goto",
        description="冗余 goto：目标标签就是下一条非空语句",
        direction="forward",
        location="top_level",
        conditionality="both",
        target_kind="label",
        corpus_statements=27,
        corpus_files=5,
        confidence="B",
        integrated=False,
        convertible=True,
        plan="已实现（v2.4.0）：整行独立顶层 goto 且目标紧随其后 → 等价 no-op（core/batch.py _convert_goto）",
        evidence="合并文本/合并文本.bat:6",
        notes="v2.4.0 实现仅覆盖「整行独立 goto」；条件/复合形态（if … (goto X) else …、cmd & goto）仍为诚实 TODO。",
    ),
    ControlFlowPattern(
        key="missing_label",
        description="目标标签在文件内不存在",
        direction="none",
        location="both",
        conditionality="both",
        target_kind="missing",
        corpus_statements=8,
        corpus_files=2,
        confidence="D",
        integrated=False,
        convertible=False,
        plan="无自动方案：维持诚实 TODO（部分为动态目标/跨文件，静态不可判）",
        evidence="瑞星杀毒软件2008批处理版.bat:160",
        notes="扫描器仅识别字面标签；动态目标另计（dynamic_target）。",
    ),
    ControlFlowPattern(
        key="dynamic_target",
        description="动态目标 goto：目标名运行时求值（goto %VAR%）",
        direction="none",
        location="top_level",
        conditionality="both",
        target_kind="dynamic",
        corpus_statements=1,
        corpus_files=1,
        confidence="D",
        integrated=False,
        convertible=False,
        plan="无静态方案：维持诚实 TODO",
        evidence="文件夹伪装.bat:401",
        notes="examples/deepseek_bat_20260913_faa286.bat 另有 goto :%LABEL%（无 .sh 对照）。",
    ),
    ControlFlowPattern(
        key="label_in_block",
        description="标签 :name 位于控制块内（cmd 危险写法）",
        direction="none",
        location="in_block",
        conditionality="none",
        target_kind="label",
        corpus_statements=97,
        corpus_files=4,
        confidence="D",
        integrated=False,
        convertible=False,
        plan="v2.0：块内标签无静态安全改写；维持 error 层响亮拒绝",
        evidence="提取IE缓存的指定文件.bat:33",
        notes="经 report.errors（非 todo）；--fail-on-todo 计 error_count 会命中。",
        primary=False,
    ),
)

PRIMARY_SHAPE_KEYS: frozenset[str] = frozenset(
    pattern.key for pattern in GOTO_PATTERNS if pattern.primary
)


def classify_goto(
    target: str,
    *,
    label_known: bool = True,
    direction: str = "none",
    in_block: bool = False,
    redundant: bool = False,
) -> str:
    """把一条 goto 语句归入 ``PRIMARY_SHAPE_KEYS`` 中的**唯一**形态键。

    分类优先级（互斥）：动态目标 → ``:eof`` → 缺标签 → 块内 → 冗余 → 回跳 → 前跳。
    ``direction`` 取 ``"backward"`` / ``"forward"`` / ``"self"`` / ``"none"``；
    ``label_known=True`` 但方向为 ``self``/``none`` 时按**冗余**（目标等同当前/相邻语句）处理。
    """
    token = target.strip().lstrip(":").rstrip(":").lower()
    if "%" in token or "!" in token:
        return "dynamic_target"
    if token == "eof":
        return "eof_exit"
    if not label_known:
        return "missing_label"
    if in_block:
        return "in_block_goto"
    if redundant:
        return "redundant_goto"
    if direction == "backward":
        return "backward_loop"
    if direction == "forward":
        return "forward_skip"
    return "redundant_goto"


def _first_token(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("@"):
        stripped = stripped[1:].lstrip()
    return stripped.split(None, 1)[0].lower() if stripped else ""


def summarize_goto_lines(lines: Sequence[str]) -> Counter[str]:
    """对一段批处理源码逐行扫描并统计 goto 形态（**best-effort**，只读）。

    规则：跳过空行与 ``::`` 注释；``echo``/``rem`` 行内的 ``goto`` 视为数据不计；
    标签支持非 ASCII（CJK）；``in_block`` 用括号净值近似（非块栈，仅供形态统计）。
    """
    label_lines = {
        match.group(1).lower(): number
        for number, line in enumerate(lines, start=1)
        if (match := _LABEL_RE.match(line))
    }
    counter: Counter[str] = Counter()
    depth = 0
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("::"):
            continue
        if _first_token(line) not in ("echo", "rem"):
            for match in _GOTO_RE.finditer(line):
                target = match.group(1)
                key = target.strip().lstrip(":").rstrip(":").lower()
                label_line = label_lines.get(key)
                direction = "none"
                if label_line is not None:
                    direction = "backward" if label_line < number else "forward"
                redundant = False
                if label_line is not None:
                    for following in lines[number:]:
                        candidate = following.strip()
                        if not candidate or candidate.startswith("::"):
                            continue
                        label_match = _LABEL_RE.match(following)
                        redundant = bool(
                            label_match and label_match.group(1).lower() == key
                        )
                        break
                counter[
                    classify_goto(
                        target,
                        label_known=label_line is not None or key == "eof",
                        direction=direction,
                        in_block=depth > 0,
                        redundant=redundant,
                    )
                ] += 1
        depth = max(0, depth + stripped.count("(") - stripped.count(")"))
    return counter


def pattern_for(key: str) -> ControlFlowPattern | None:
    """按键查台账记录；不存在返回 ``None``。"""
    for pattern in GOTO_PATTERNS:
        if pattern.key == key:
            return pattern
    return None


def validate_control_flow_patterns() -> list[str]:
    """校验台账 schema 与纪律（``evidence`` 必填、置信度/枚举合法、覆盖完整）。"""
    problems: list[str] = []
    seen: set[str] = set()
    for pattern in GOTO_PATTERNS:
        where = f"control_flow[{pattern.key}]"
        if not pattern.key or pattern.key in seen:
            problems.append(f"{where}: 键为空或重复")
        seen.add(pattern.key)
        if not pattern.description:
            problems.append(f"{where}: description 为空")
        if pattern.confidence not in CONFIDENCE_LEVELS:
            problems.append(f"{where}: confidence 非法（{pattern.confidence!r}）")
        if pattern.direction not in _DIRECTIONS:
            problems.append(f"{where}: direction 非法（{pattern.direction!r}）")
        if pattern.location not in _LOCATIONS:
            problems.append(f"{where}: location 非法（{pattern.location!r}）")
        if pattern.conditionality not in _CONDITIONALITY:
            problems.append(f"{where}: conditionality 非法（{pattern.conditionality!r}）")
        if pattern.target_kind not in _TARGET_KINDS:
            problems.append(f"{where}: target_kind 非法（{pattern.target_kind!r}）")
        if not pattern.evidence or not _EVIDENCE_RE.match(pattern.evidence):
            problems.append(f"{where}: evidence 缺失或格式非『文件:行』")
        if not pattern.plan:
            problems.append(f"{where}: plan 为空")
        if not pattern.notes:
            problems.append(f"{where}: notes 为空")
        if pattern.corpus_statements < 0 or pattern.corpus_files < 0:
            problems.append(f"{where}: 语料计数为负")
        if (pattern.corpus_statements > 0) != (pattern.corpus_files > 0):
            problems.append(f"{where}: corpus_statements/files 不一致")
        if pattern.integrated and (
            pattern.confidence != "A" or not pattern.convertible
        ):
            problems.append(f"{where}: integrated=True 要求 confidence=A 且 convertible=True")
        if pattern.convertible and pattern.confidence not in ("A", "B"):
            problems.append(f"{where}: convertible=True 要求 confidence ∈ {{A,B}}")
        if pattern.confidence == "D" and pattern.convertible:
            problems.append(f"{where}: D 档不得 convertible=True")
        if pattern.primary and pattern.corpus_statements <= 0:
            problems.append(f"{where}: 主形态必须有语料计数")
    if PRIMARY_SHAPE_KEYS != frozenset(p.key for p in GOTO_PATTERNS if p.primary):
        problems.append("PRIMARY_SHAPE_KEYS 与 primary 记录不一致")
    if len(seen) != len(GOTO_PATTERNS):
        problems.append("台账存在重复键")
    return problems
