"""词法层残余额账测试（v1.10.0rc1 / Session C-lex）。

断言的是**台账语义**（纪律 14：不编码转换器的当前行为）：
- 台账完整性（evidence 必填、置信度光谱、只读）；
- `classify_percent_token` 的 **cmd 语义**（wine 锚定），而非转换器现况。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from bat2sh.core.lexical_residuals import (
    LEXICAL_RESIDUALS,
    MECHANISM_GUARD_FALSE_POSITIVE,
    MECHANISM_HEADER_SPLIT,
    MECHANISM_SUBSTRING_SPLIT,
    classify_percent_token,
    expected_percent_expansion,
    residual_for_id,
    summarize_residuals,
    validate_lexical_residuals,
)

MODULE = Path(__file__).resolve().parents[1] / "python" / "bat2sh" / "core" / "lexical_residuals.py"


def test_validator_clean():
    assert validate_lexical_residuals() == []


def test_four_residuals_cover_expected_corpus_ids():
    assert len(LEXICAL_RESIDUALS) == 4
    assert {r.id for r in LEXICAL_RESIDUALS} == {"044", "059", "135", "138"}


def test_mechanisms_are_the_three_documented_kinds():
    by_mech = {r.mechanism for r in LEXICAL_RESIDUALS}
    assert by_mech == {
        MECHANISM_HEADER_SPLIT,
        MECHANISM_GUARD_FALSE_POSITIVE,
        MECHANISM_SUBSTRING_SPLIT,
    }
    assert [r.id for r in LEXICAL_RESIDUALS if r.mechanism == MECHANISM_HEADER_SPLIT] == ["044", "135"]


def test_every_residual_has_evidence_and_file_line_root_cause():
    for r in LEXICAL_RESIDUALS:
        assert r.evidence, r.id
        assert re.match(r"^[\w./]+:\d+", r.root_cause), (r.id, r.root_cause)


def test_ledger_is_read_only_and_never_integrated():
    assert all(r.integrated is False for r in LEXICAL_RESIDUALS)
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any("batch" in name for name in imported), imported


def test_validator_rejects_missing_evidence():
    from dataclasses import replace

    bad = replace(LEXICAL_RESIDUALS[0], evidence=())
    problems = validate_lexical_residuals((bad,))
    assert any("evidence" in p for p in problems)


def test_validator_rejects_confidence_d_fixed():
    from dataclasses import replace

    bad = replace(LEXICAL_RESIDUALS[0], confidence="D", status="fixed")
    problems = validate_lexical_residuals((bad,))
    assert any("D 档" in p for p in problems)


def test_classify_percent_token_follows_cmd_semantics():
    # 活动 for 体内 → 循环变量
    assert classify_percent_token(in_active_for=True, in_nested_command_string=False) == "loop_var"
    # for 外（含引号内字面）→ 字面（wine: echo %%m -> %m）
    assert classify_percent_token(in_active_for=False, in_nested_command_string=False) == "literal"
    # 嵌套命令字符串内（059：cmd /c "…%%i…"）→ 字面
    assert classify_percent_token(in_active_for=True, in_nested_command_string=True) == "literal"


def test_expected_percent_expansion_shape():
    assert expected_percent_expansion("J", in_active_for=True, in_nested_command_string=False) == "${j}"
    assert expected_percent_expansion("M", in_active_for=False, in_nested_command_string=False) == "%M"
    assert expected_percent_expansion("I", in_active_for=True, in_nested_command_string=True) == "%I"


def test_summary_consistency():
    summary = summarize_residuals()
    assert summary["count"] == len(LEXICAL_RESIDUALS)
    assert set(summary["ids"]) == {"044", "059", "135", "138"}
    assert summary["statuses"] == {"backlog"}
    assert summary["touches_block_stack"] == ["044", "135"]
    assert summary["touches_a1"] == ["059"]


def test_residual_lookup():
    assert residual_for_id("059").name == "打开快捷方式指向的目录.bat"
    assert residual_for_id("135").mechanism == MECHANISM_HEADER_SPLIT
    assert residual_for_id("999") is None
