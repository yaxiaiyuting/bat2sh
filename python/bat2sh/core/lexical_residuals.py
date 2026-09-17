"""词法层残余台账（v1.10.0rc1 / Session C-lex）。

背景
----
053「块栈失同步」已于 v1.9.0（commit ``61a4b44``）修复，A1 ``%VAR%`` 冻结语义已于
v1.9.2 修复。此后语料中仍有 4 个 degraded 文件触发转换器的**循环变量逸出守卫**
（``core/batch.py`` 的 ``_loop_var_leak`` → 消息
``循环变量 %%x 逸出 for 循环（块结构失同步）``）。

本模块把 4 条残余的**机制 / 根因 / 最小复现 / 修复草案 / 风险**固化为与
「命令表 / 名称表 / 输出契约表 / 控制流表」并列的**第五张只读表**，
供后续版本（v2.0 解析层）与回归使用。

纪律
----
- **只读**：本模块**不 import** ``core.batch``，**不被转换器调用**（``integrated=False``）。
- **证据必填**（纪律 7）：每条 residual 必须有 ``evidence``；``validate_lexical_residuals()``
  在测试中守护。
- **置信度光谱**（纪律 6）：``confidence ∈ {A,B,C,D}``；D 档不得标 ``fixed``。

实测证伪（本会话）
------------------
任务书把 4 条统称「真块失同步」，本会话用 wine 语义锚定证伪：
**只有 2 条是 for 头切分歧义（044/135，同构），另 2 条是守卫误报（059/138）**。
详见 ``docs/session-lex-coldstart.md`` §3.2 与 ``docs/session-lex-design.md``。
"""

from __future__ import annotations

from dataclasses import dataclass

# 转换器的逸出守卫消息（唯一权威字符串，见 core/batch.py:2695-2703）
LEAK_GUARD_MESSAGE = "循环变量 %%x 逸出 for 循环（块结构失同步）"

# 机制编号（与 docs/session-lex-design.md §3 对齐）
MECHANISM_HEADER_SPLIT = "LF-1"   # for 头正则贪婪切分（044/135）
MECHANISM_GUARD_FALSE_POSITIVE = "LF-2"  # 守卫引号/nested-cmd 盲区（059）
MECHANISM_SUBSTRING_SPLIT = "LF-3"  # _protect_arith_modulo 子串盲区（138）

ALLOWED_MECHANISMS = (MECHANISM_HEADER_SPLIT, MECHANISM_GUARD_FALSE_POSITIVE, MECHANISM_SUBSTRING_SPLIT)
ALLOWED_CONFIDENCE = ("A", "B", "C", "D")
ALLOWED_STATUS = ("backlog", "fixed", "wontfix", "terminal")
ALLOWED_RISK = ("低", "低-中", "中", "中-高", "高")


@dataclass(frozen=True)
class LexicalResidual:
    """单条词法层残余（按语料文件登记）。"""

    id: str                    # 语料仪器 ID（3 位）
    name: str                  # 文件相对路径
    mechanism: str             # LF-1 / LF-2 / LF-3
    kind: str                  # header_split / guard_false_positive / substring_split
    symptom: str               # 观测到的错误症状
    root_cause: str            # file:line
    trigger: str               # 最小复现（单行）
    fix_sketch: str            # 修复草案（本版不实现）
    risk: str                  # ALLOWED_RISK
    status: str                # ALLOWED_STATUS
    confidence: str            # A/B/C/D
    evidence: tuple[str, ...]  # 证据（file:line / wine 实测 / 仪器计数）
    wine_evidence: str         # wine cmd 锚定结论（可为空串）
    touches_block_stack: bool  # 是否触及 053 已修块栈核心
    touches_a1: bool           # 是否触及 A1（%VAR% 冻结）热路径
    metrics_impact: str        # 本 scope 内的指标影响
    integrated: bool = False   # 恒为 False：本表不驱动转换


LEXICAL_RESIDUALS: tuple[LexicalResidual, ...] = (
    LexicalResidual(
        id="044",
        name="备份文件/备份服务.bat",
        mechanism=MECHANISM_HEADER_SPLIT,
        kind="header_split",
        symptom="整行 `echo sc config %%j start= %%s >>\"%FILENAME%\"` 被降级为 TODO「逸出」",
        root_cause="core/batch.py:2092",
        trigger='for %%j in (a) do (for %%s in (b) do echo %%j %%s)',
        fix_sketch=(
            "对 in (…) 起点做平衡括号扫描，取第一个深度归零的 ')' 作为 set_text 结束；"
            "仅当粗匹配结果内出现 ') do'（已误切）时回退，收窄改动面"
        ),
        risk="中-高",
        status="backlog",
        confidence="A",
        evidence=(
            "core/batch.py:2092 头部正则 `\\((.*)\\)` 贪婪",
            "最小复现 /tmp/lex/repro.py:r044 复现逸出 TODO（warn=4）",
            "churn 上界：10 行 / 4 文件（只读语料扫描）",
            "docs/v1.8.3-attribution.md [044] 归因（D 深水区）",
        ),
        wine_evidence="源 `%%j/%%s` 确为外层/内层 for 变量；cmd 应输出每对 (j,s) 组合",
        touches_block_stack=True,
        touches_a1=False,
        metrics_impact="无文件翻转（044 仍有 path/pipeline/for-f 等 6 条 TODO）",
    ),
    LexicalResidual(
        id="135",
        name="系统优化.bat",
        mechanism=MECHANISM_HEADER_SPLIT,
        kind="header_split",
        symptom="`echo sc config %%j start= %%k >>\"%filename%\"` 被降级为 TODO「逸出」",
        root_cause="core/batch.py:2092",
        trigger='for /f "tokens=2" %%j in (f) do (echo %%j & for /f "tokens=4" %%s in (g) do echo %%j %%s)',
        fix_sketch="同 LF-1（044）：for 头平衡括号扫描",
        risk="中-高",
        status="backlog",
        confidence="A",
        evidence=(
            "源 batch.py:4228（本会话定位）与 044 同构（多一层嵌套 for /f）",
            "最小复现 /tmp/lex/matrix.py:m3_forf_nested 复现逸出 TODO（warn=4）",
            "churn 上界：与 LF-1 合并计 4 文件",
        ),
        wine_evidence="同 LF-1（循环变量语义一致）",
        touches_block_stack=True,
        touches_a1=False,
        metrics_impact="无文件翻转（135 有 443 条 TODO，横跨 goto/sc/regsvr32 等）",
    ),
    LexicalResidual(
        id="059",
        name="打开快捷方式指向的目录.bat",
        mechanism=MECHANISM_GUARD_FALSE_POSITIVE,
        kind="guard_false_positive",
        symptom='整行 `start "提示" cmd /c "…for /l %%i…"` 被降级为 TODO「逸出」',
        root_cause="core/batch.py:928-935 + :2695-2703（leak 守卫）",
        trigger='echo "for /l %%i in (5,-1,1) do cls"',
        fix_sketch=(
            "在 _expand_vars 标注引号 / nested-command 字符串态；"
            "对字符串内 %%X 按字面处理且不置 _loop_var_leak；引号外维持守卫"
        ),
        risk="高",
        status="backlog",
        confidence="A",
        evidence=(
            "wine 实测 `echo %%m` → `%m`、`echo \"for /l %%i …\"` → 字面 `%i`",
            "最小复现 /tmp/lex/repro.py:r059；更简 echo 引号也复现",
            "leak 守卫为载荷性兜底（044/135 依赖它），误收窄 → 静默错",
        ),
        wine_evidence="`%%X` 在 for 外（含引号内）为字面 `%X`，非循环变量",
        touches_block_stack=False,
        touches_a1=True,
        metrics_impact="无文件翻转（059 余 1 条 for/f TODO）",
    ),
    LexicalResidual(
        id="138",
        name="获取U盘盘符和可用容量.bat",
        mechanism=MECHANISM_SUBSTRING_SPLIT,
        kind="substring_split",
        symptom="`set /a m3=%m3%%m:~0,1%%%%~1` 被降级为 TODO「逸出」（伪 `%%m`）",
        root_cause="core/batch.py:131-152（_protect_arith_modulo）",
        trigger="set /a m3=%m3%%m:~0,1%%%%~1",
        fix_sketch=(
            "在 _protect_arith_modulo 并列识别子串式 `%VAR:~[^%]*%`（与 _expand_vars 子串正则同源），"
            "整段透传后再找 `%%`"
        ),
        risk="低-中",
        status="backlog",
        confidence="B",
        evidence=(
            "core/batch.py:128 `_ARITH_VAR_RE = %([^\\W\\d]\\w*)%` 不匹配 `%VAR:~n,m%`",
            "最小复现 /tmp/lex/repro.py:r138b（顶层、无 for，仍复现）",
            "churn 上界：2 行 / 2 文件（083、138）",
        ),
        wine_evidence="源行本身退化：wine `set /a m3=…` 报错、m3 值不变 → 「修成什么」语义不明",
        touches_block_stack=False,
        touches_a1=False,
        metrics_impact="无文件翻转（138 余 6 条 goto/for-f TODO）",
    ),
)


def validate_lexical_residuals(
    residuals: tuple[LexicalResidual, ...] = LEXICAL_RESIDUALS,
) -> list[str]:
    """校验台账完整性（纪律 7：缺 evidence 拒绝）。返回问题列表，空列表 = 通过。"""
    problems: list[str] = []
    seen: set[str] = set()
    for r in residuals:
        where = r.id or "<no-id>"
        if not r.id or not r.id.isdigit() or len(r.id) != 3:
            problems.append(f"{where}: id 必须是 3 位数字")
        if r.id in seen:
            problems.append(f"{where}: id 重复")
        seen.add(r.id)
        if not r.name.strip():
            problems.append(f"{where}: name 不能为空")
        if r.mechanism not in ALLOWED_MECHANISMS:
            problems.append(f"{where}: mechanism 非法 {r.mechanism!r}")
        if r.confidence not in ALLOWED_CONFIDENCE:
            problems.append(f"{where}: confidence 非法 {r.confidence!r}")
        if r.status not in ALLOWED_STATUS:
            problems.append(f"{where}: status 非法 {r.status!r}")
        if r.risk not in ALLOWED_RISK:
            problems.append(f"{where}: risk 非法 {r.risk!r}")
        if not r.evidence or any(not e.strip() for e in r.evidence):
            problems.append(f"{where}: evidence 必填且不得为空（纪律 7）")
        if ":" not in r.root_cause:
            problems.append(f"{where}: root_cause 必须为 file:line，实为 {r.root_cause!r}")
        if not r.trigger.strip():
            problems.append(f"{where}: trigger（最小复现）必填")
        if not r.fix_sketch.strip():
            problems.append(f"{where}: fix_sketch 必填")
        if not r.symptom.strip():
            problems.append(f"{where}: symptom 必填")
        if r.confidence == "D" and r.status == "fixed":
            problems.append(f"{where}: D 档不得标 fixed")
        if r.integrated:
            problems.append(f"{where}: 本表为只读台账，integrated 必须为 False")
    missing = {"044", "059", "135", "138"} - seen
    if missing:
        problems.append(f"台账缺残余: {sorted(missing)}")
    return problems


def classify_percent_token(*, in_active_for: bool, in_nested_command_string: bool) -> str:
    """按 cmd 语义分类 ``%%X``：``"loop_var"`` 或 ``"literal"``。

    规则（wine 实测）：``%%X`` 仅在**活动 for 体内**且**不在嵌套命令字符串内**时
    才是循环变量；否则是字面 ``%X``。
    """
    if in_active_for and not in_nested_command_string:
        return "loop_var"
    return "literal"


def expected_percent_expansion(
    name: str, *, in_active_for: bool, in_nested_command_string: bool
) -> str:
    """给出 ``%%NAME`` 的语义等价展开（与转换器无关的参考实现）。"""
    if classify_percent_token(
        in_active_for=in_active_for, in_nested_command_string=in_nested_command_string
    ) == "loop_var":
        return "${%s}" % name.lower()
    return "%" + name


def residual_for_id(cid: str) -> LexicalResidual | None:
    for r in LEXICAL_RESIDUALS:
        if r.id == cid:
            return r
    return None


def summarize_residuals() -> dict[str, object]:
    """机器可读摘要（供 tools/lex 与测试使用）。"""
    mechanisms: dict[str, list[str]] = {}
    for r in LEXICAL_RESIDUALS:
        mechanisms.setdefault(r.mechanism, []).append(r.id)
    return {
        "count": len(LEXICAL_RESIDUALS),
        "ids": [r.id for r in LEXICAL_RESIDUALS],
        "mechanisms": mechanisms,
        "statuses": {r.status for r in LEXICAL_RESIDUALS},
        "touches_block_stack": [r.id for r in LEXICAL_RESIDUALS if r.touches_block_stack],
        "touches_a1": [r.id for r in LEXICAL_RESIDUALS if r.touches_a1],
        "guard_message": LEAK_GUARD_MESSAGE,
    }
