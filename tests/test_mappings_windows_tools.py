"""v1.8.1 结构化映射表校验（纪律 7：缺 evidence 一律拒绝）。"""

from __future__ import annotations

import re

from bat2sh.mappings import WINDOWS_TOOLS, mapping_for, validate_mappings
from bat2sh.mappings.windows_tools import ToolMapping


def test_table_passes_validation():
    assert validate_mappings() == []


def test_every_entry_has_real_corpus_evidence():
    for item in WINDOWS_TOOLS:
        assert re.match(r"^corpus/.+:\d+$", item.evidence), item.win


def test_all_entries_have_confidence_in_spectrum():
    assert {item.confidence for item in WINDOWS_TOOLS} <= {"A", "B", "C", "D"}


def test_missing_evidence_is_rejected():
    bad = (
        ToolMapping(
            win="x", linux="y", form="1:1", confidence="A", output_contract=False,
            dangerous=False, target_exists="yes", evidence="",
        ),
    )
    assert any("evidence" in e for e in validate_mappings(bad))


def test_confidence_d_must_not_invent_combo():
    bad = (
        ToolMapping(
            win="x", linux="magic", form="1:1", confidence="D", output_contract=False,
            dangerous=False, target_exists="yes", evidence="corpus/a.bat:1",
        ),
    )
    assert any("confidence D" in e for e in validate_mappings(bad))


def test_output_contract_requires_format_note():
    bad = (
        ToolMapping(
            win="x", linux="y", form="1:1", confidence="A", output_contract=True,
            dangerous=False, target_exists="yes", evidence="corpus/a.bat:1", notes="",
        ),
    )
    assert any("输出格式" in e for e in validate_mappings(bad))


def test_target_exists_no_requires_note():
    bad = (
        ToolMapping(
            win="x", linux="", form="none", confidence="D", output_contract=False,
            dangerous=False, target_exists="no", evidence="corpus/a.bat:1", notes="",
        ),
    )
    assert any("目标物不存在" in e for e in validate_mappings(bad))


def test_duplicate_win_rejected():
    entry = dict(
        linux="y", form="1:1", confidence="A", output_contract=False,
        dangerous=False, target_exists="yes", evidence="corpus/a.bat:1",
    )
    bad = (ToolMapping(win="dup", **entry), ToolMapping(win="DUP", **entry))
    assert any("重复" in e for e in validate_mappings(bad))


def test_mapping_for_lookup():
    assert mapping_for("regsvr32").confidence == "D"
    assert mapping_for("REGSVR32.EXE").form == "none"
    assert mapping_for("nonexistent-tool") is None


def test_v182_new_d_entries_present():
    for name in (
        "graftabl", "debug", "defrag", "regini", "mountvol",
        "cmdow", "csty", "keyprs", "finfo", "cido",
    ):
        item = mapping_for(name)
        assert item is not None, name
        assert item.confidence == "D" and item.form == "none" and item.linux == "", name


def test_v182_partial_entries_have_linux_target():
    assert mapping_for("nconvert").form == "partial"
    assert mapping_for("rasdial").linux == "nmcli"
    assert mapping_for("subst").linux == "mount --bind"


def test_new_d_tool_converts_to_honest_todo(convert_bat, bash_check):
    out, report = convert_bat("@echo off\ngraftabl 936 >nul\n")
    bash_check(out)
    assert "# TODO: 手动检查: graftabl 936 >nul" in out
    assert report.todo_count == 1

