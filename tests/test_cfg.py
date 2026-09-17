"""CFG 只读数据模型（core/cfg.py）回归测试。

断言**语义**（方向 / 目标类型 / 冗余 / 块内 / 入边 / 多入口），而非编码转换器现况
（纪律 14）。**不依赖外部语料**（CI 可跑）。
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

from bat2sh.core.cfg import (
    DIRECTIONS,
    TARGET_KINDS,
    build_cfg,
    build_cfg_from_text,
    logical_lines,
    summarize_cfg,
    validate_cfg,
)
from bat2sh.core.control_flow import PRIMARY_SHAPE_KEYS, summarize_goto_lines

MODULE = Path(__file__).resolve().parents[1] / "python" / "bat2sh" / "core" / "cfg.py"


def _edges(cfg):
    return {edge.target: edge for edge in cfg.edges}


def test_module_never_imports_the_converter() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any("batch" in name for name in imported), imported


def test_canonical_program_validates() -> None:
    cfg = build_cfg_from_text(
        "@echo off\ngoto skip\n:skip\necho done\ngoto :eof\n"
    )
    assert validate_cfg(cfg) == []


def test_labels_record_positions_and_lines() -> None:
    cfg = build_cfg_from_text("@echo off\n:alpha\necho a\n:beta\necho b\n")
    assert [(p.name, p.line) for p in cfg.labels] == [("alpha", 2), ("beta", 4)]
    assert all(p.incoming == 0 for p in cfg.labels)


def test_forward_and_backward_directions() -> None:
    cfg = build_cfg_from_text("@echo off\ngoto later\necho x\n:later\ngoto :eof\n")
    edge = _edges(cfg)["later"]
    assert edge.direction == "forward"
    assert edge.shape == "forward_skip"
    assert edge.target_kind == "label"

    cfg = build_cfg_from_text("@echo off\n:top\necho x\ngoto top\n")
    edge = _edges(cfg)["top"]
    assert edge.direction == "backward"
    assert edge.shape == "backward_loop"


def test_eof_target_is_special() -> None:
    cfg = build_cfg_from_text("@echo off\ngoto :eof\n")
    edge = cfg.edges[0]
    assert edge.target_kind == "eof"
    assert edge.direction == "none"
    assert edge.shape == "eof_exit"
    assert edge.target_index is None


def test_dynamic_target_is_not_resolved() -> None:
    cfg = build_cfg_from_text("@echo off\ngoto %TARGET%\n:hit\necho x\n")
    edge = _edges(cfg)["%TARGET%"]
    assert edge.target_kind == "dynamic"
    assert edge.shape == "dynamic_target"
    assert edge.target_line is None


def test_missing_label_is_reported_not_invented() -> None:
    cfg = build_cfg_from_text("@echo off\ngoto nowhere\n")
    edge = cfg.edges[0]
    assert edge.target_kind == "missing"
    assert edge.shape == "missing_label"
    assert validate_cfg(cfg) == []


def test_redundant_goto_when_next_statement_is_the_label() -> None:
    cfg = build_cfg_from_text("@echo off\ngoto next\n:next\necho x\n")
    edge = _edges(cfg)["next"]
    assert edge.redundant is True
    assert edge.shape == "redundant_goto"


def test_not_redundant_when_code_between() -> None:
    cfg = build_cfg_from_text("@echo off\ngoto next\necho intermediate\n:next\necho x\n")
    edge = _edges(cfg)["next"]
    assert edge.redundant is False
    assert edge.shape == "forward_skip"


def test_comment_and_blank_lines_do_not_break_redundancy() -> None:
    cfg = build_cfg_from_text("@echo off\ngoto next\n\n:: comment\n:next\necho x\n")
    assert _edges(cfg)["next"].redundant is True


def test_in_block_goto_uses_paren_net() -> None:
    cfg = build_cfg_from_text("@echo off\nif 1==1 (\ngoto out\n)\n:out\necho x\n")
    edge = _edges(cfg)["out"]
    assert edge.in_block is True
    assert edge.shape == "in_block_goto"


def test_conditional_flag_marks_non_standalone_gotos() -> None:
    cfg = build_cfg_from_text('@echo off\nif "%1"=="" goto empty\necho x\n:empty\necho y\n')
    edge = _edges(cfg)["empty"]
    assert edge.conditional is True
    assert edge.shape == "forward_skip"

    cfg = build_cfg_from_text("@echo off\ngoto :eof\n")
    assert cfg.edges[0].conditional is False


def test_incoming_counts_and_multi_entry() -> None:
    cfg = build_cfg_from_text(
        "@echo off\ngoto hit\ngoto hit\n:first\necho x\n:hit\necho y\n"
    )
    assert [(p.name, p.incoming) for p in cfg.labels] == [("first", 0), ("hit", 2)]
    assert summarize_cfg(cfg)["multi_entry_labels"] == ["hit"]


def test_duplicate_labels_exposed_but_not_a_model_error() -> None:
    cfg = build_cfg_from_text("@echo off\n:dup\necho a\n:dup\necho b\n")
    summary = summarize_cfg(cfg)
    assert summary["duplicate_labels"] == ["dup"]
    assert len(cfg.label_map["dup"]) == 2
    assert validate_cfg(cfg) == []


def test_cjk_labels_are_supported() -> None:
    cfg = build_cfg_from_text("@echo off\ngoto 锁定\n:锁定\necho x\n")
    edge = cfg.edges[0]
    assert edge.target_kind == "label"
    assert edge.direction == "forward"


def test_echo_and_rem_gotos_are_data_not_edges() -> None:
    cfg = build_cfg_from_text(
        "@echo off\necho goto nowhere\nrem goto nowhere\n:nowhere\necho x\n"
    )
    assert cfg.edges == ()
    assert validate_cfg(cfg) == []


def test_start_lines_align_with_logical_lines() -> None:
    cfg = build_cfg(["@echo off", "goto later", ":later"], start_lines=[10, 20, 30])
    assert cfg.edges[0].source_line == 20
    assert cfg.labels[0].line == 30


def test_build_cfg_rejects_mismatched_start_lines() -> None:
    try:
        build_cfg(["a", "b"], start_lines=[1])
    except ValueError:
        return
    raise AssertionError("应当抛出 ValueError")


def test_logical_lines_match_batch_converter() -> None:
    from bat2sh.core.batch import BatchConverter
    from bat2sh.core.settings import ConvertSettings

    text = "@echo off\necho one ^\ntwo\nfor %%i in (a) do (\necho %%i\n)\n"
    assert logical_lines(text) == BatchConverter(
        ConvertSettings(bash_check=False)
    )._logical_lines(text)


def test_shape_distribution_matches_control_flow_scanner() -> None:
    lines = [
        "@echo off",
        "if \"%1\"==\"\" goto empty",
        "echo body",
        ":empty",
        "goto later",
        "echo skipped",
        ":later",
        "for %%i in (a) do (",
        "goto stop",
        ")",
        ":stop",
        "goto back",
        ":back",
        "goto next",
        ":next",
        "goto :eof",
        "goto %T%",
        "goto nowhere",
    ]
    cfg = build_cfg(lines)
    mine = {
        key: count
        for key, count in summarize_cfg(cfg)["by_shape"].items()
        if key in PRIMARY_SHAPE_KEYS
    }
    reference = {
        key: count
        for key, count in summarize_goto_lines(lines).items()
        if key in PRIMARY_SHAPE_KEYS
    }
    assert mine == reference
    assert validate_cfg(cfg) == []


def test_validator_flags_direction_inconsistency() -> None:
    cfg = build_cfg_from_text("@echo off\ngoto later\necho x\n:later\necho y\n")
    broken = replace(cfg.edges[0], direction="backward")
    problems = validate_cfg(replace(cfg, edges=(broken,)))
    assert any("direction" in problem for problem in problems)


def test_validator_flags_unknown_shape() -> None:
    cfg = build_cfg_from_text("@echo off\ngoto later\necho x\n:later\necho y\n")
    broken = replace(cfg.edges[0], shape="not_a_shape")
    problems = validate_cfg(replace(cfg, edges=(broken,)))
    assert any("shape" in problem for problem in problems)


def test_validator_flags_incoming_drift() -> None:
    cfg = build_cfg_from_text("@echo off\ngoto later\necho x\n:later\necho y\n")
    broken = replace(cfg.labels[0], incoming=99)
    problems = validate_cfg(replace(cfg, labels=(broken,)))
    assert any("incoming" in problem for problem in problems)


def test_enums_are_the_documented_sets() -> None:
    assert DIRECTIONS == ("backward", "forward", "self", "none")
    assert TARGET_KINDS == ("label", "eof", "dynamic", "missing")
