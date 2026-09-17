"""C4 控制流形态台账（core/control_flow.py）回归测试。

覆盖：台账 schema/纪律校验、分类器互斥性、扫描器行为（echo/rem 跳过、CJK 标签、
前跳/回跳/块内/冗余/缺标签/动态目标）。**不依赖外部语料**（CI 可跑）。
"""

from __future__ import annotations

from bat2sh.core.control_flow import (
    CONFIDENCE_LEVELS,
    GOTO_PATTERNS,
    PRIMARY_SHAPE_KEYS,
    classify_goto,
    pattern_for,
    summarize_goto_lines,
    validate_control_flow_patterns,
)

EXPECTED_PRIMARY = {
    "eof_exit",
    "forward_skip",
    "backward_loop",
    "in_block_goto",
    "redundant_goto",
    "missing_label",
    "dynamic_target",
}


def test_ledger_passes_validation() -> None:
    assert validate_control_flow_patterns() == []


def test_primary_keys_are_expected_set() -> None:
    assert PRIMARY_SHAPE_KEYS == frozenset(EXPECTED_PRIMARY)
    assert {p.key for p in GOTO_PATTERNS if p.primary} == EXPECTED_PRIMARY


def test_every_primary_key_is_reachable_by_classifier() -> None:
    produced = {
        classify_goto("eof"),
        classify_goto("%dynamic%"),
        classify_goto("elsewhere", label_known=False),
        classify_goto("loop", direction="backward"),
        classify_goto("ahead", direction="forward"),
        classify_goto("inside", in_block=True),
        classify_goto("next", redundant=True),
    }
    assert produced == EXPECTED_PRIMARY


def test_classify_priority_is_exclusive() -> None:
    # 动态目标优先于一切
    assert classify_goto("%x%", in_block=True, direction="backward") == "dynamic_target"
    # :eof 优先于块内
    assert classify_goto("eof", in_block=True) == "eof_exit"
    # 缺标签优先于块内
    assert classify_goto("gone", label_known=False, in_block=True) == "missing_label"
    # 块内优先于冗余/方向
    assert classify_goto("x", in_block=True, direction="backward", redundant=True) == "in_block_goto"


def test_classify_fallback_for_known_label_without_direction() -> None:
    assert classify_goto("here", direction="self") == "redundant_goto"
    assert classify_goto("here") == "redundant_goto"


def test_classify_target_normalisation() -> None:
    assert classify_goto(":EOF") == "eof_exit"
    assert classify_goto(" Loop ", direction="backward") == "backward_loop"


def test_pattern_for_lookup() -> None:
    assert pattern_for("eof_exit") is not None
    assert pattern_for("nope") is None
    assert pattern_for("eof_exit").integrated is True


def test_ledger_evidence_and_confidence_rules() -> None:
    for pattern in GOTO_PATTERNS:
        assert pattern.confidence in CONFIDENCE_LEVELS
        assert ":" in pattern.evidence and pattern.evidence.rsplit(":", 1)[1].isdigit()
        if pattern.confidence == "D":
            assert pattern.convertible is False
        if pattern.integrated:
            assert pattern.confidence == "A"


def test_summarize_forward_and_backward() -> None:
    lines = [
        "@echo off",
        ":loop",
        "if exist a.txt goto done",
        "echo working",
        "goto loop",
        ":done",
        "goto :eof",
    ]
    summary = summarize_goto_lines(lines)
    assert summary["forward_skip"] == 1
    assert summary["backward_loop"] == 1
    assert summary["eof_exit"] == 1


def test_summarize_redundant_goto() -> None:
    lines = ["goto next", ":next", "echo hi"]
    assert summarize_goto_lines(lines)["redundant_goto"] == 1


def test_summarize_in_block_goto() -> None:
    lines = [
        "for %%i in (a b) do (",
        "    if not defined x goto skip",
        ")",
        ":skip",
    ]
    assert summarize_goto_lines(lines)["in_block_goto"] == 1


def test_summarize_dynamic_target() -> None:
    assert summarize_goto_lines(["goto %name%", ":a"])["dynamic_target"] == 1


def test_summarize_missing_label() -> None:
    assert summarize_goto_lines(["goto nowhere"])["missing_label"] == 1


def test_summarize_ignores_echo_and_rem_lines() -> None:
    lines = [
        'echo if "%%p%%"=="1" goto continue >> out.bat',
        "rem goto somewhere",
        ":: goto commented",
    ]
    assert summarize_goto_lines(lines) == {}


def test_summarize_handles_cjk_labels() -> None:
    lines = ["goto 清理", ":清理", "echo done"]
    assert summarize_goto_lines(lines)["redundant_goto"] == 1


def test_summarize_counts_are_disjoint() -> None:
    lines = [
        "goto :eof",
        "goto %x%",
        "goto missing",
        ":start",
        "goto start",
        "goto ahead",
        ":ahead",
    ]
    summary = summarize_goto_lines(lines)
    assert set(summary) <= EXPECTED_PRIMARY
    assert sum(summary.values()) == 5
