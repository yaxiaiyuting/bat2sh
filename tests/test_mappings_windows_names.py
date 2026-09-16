"""B1 名称映射子系统框架单测（v1.10.0a1）。

纪律 7：``evidence`` 必填且指向真实语料；降级策略可测（form=none → 诚实 TODO）。
框架阶段 ``WINDOWS_NAMES`` 为空表，故大部分用**合成条目**驱动校验器与查找器。
"""

from __future__ import annotations

import re

from bat2sh.mappings import (
    NAME_KINDS,
    WINDOWS_NAMES,
    NameMapping,
    env_mapping_for,
    name_mapping_for,
    path_root_mapping_for,
    unmappable_env_names_in,
    validate_name_mappings,
)


def make(**kwargs) -> NameMapping:
    base = dict(
        win="X",
        kind="env_var",
        linux="",
        form="none",
        confidence="C",
        target_exists="no",
        evidence="corpus/demo.bat:1",
        integrated=True,
        notes="Windows 专有名称在 Linux 无对应物；目标物不存在。",
    )
    base.update(kwargs)
    return NameMapping(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# schema / 校验器
# --------------------------------------------------------------------------


def test_empty_entries_passes_validation():
    assert validate_name_mappings(()) == []


def test_validate_accepts_wellformed_entry():
    assert validate_name_mappings((make(),)) == []


def test_name_kinds_are_documented():
    assert NAME_KINDS == ("env_var", "path_root", "service")


def test_missing_evidence_is_rejected():
    assert "evidence" in " ".join(validate_name_mappings((make(evidence=""),)))


def test_evidence_must_point_to_corpus_line():
    bad = validate_name_mappings((make(evidence="docs/foo.md"),))
    assert bad and "格式错误" in bad[0]


def test_invalid_kind_is_rejected():
    assert any("kind 非法" in e for e in validate_name_mappings((make(kind="thing"),)))


def test_invalid_form_is_rejected():
    assert any("form 非法" in e for e in validate_name_mappings((make(form="weird"),)))


def test_invalid_confidence_is_rejected():
    assert any("confidence 非法" in e for e in validate_name_mappings((make(confidence="Z"),)))


def test_invalid_target_exists_is_rejected():
    assert any(
        "target_exists 非法" in e for e in validate_name_mappings((make(target_exists="maybe"),))
    )


def test_confidence_d_requires_none_and_empty_linux():
    bad = validate_name_mappings((make(confidence="D", form="1:1", linux="ls"),))
    assert any("不得硬凑" in e for e in bad)


def test_form_none_requires_note():
    bad = validate_name_mappings((make(notes="随便写点什么"),))
    assert any("无对应物" in e for e in bad)


def test_target_exists_no_requires_note():
    bad = validate_name_mappings(
        (make(target_exists="no", notes="无对应物，但没写目标物"),)
    )
    assert any("目标物不存在" in e for e in bad)


def test_registered_not_integrated_requires_backlog_note():
    bad = validate_name_mappings(
        (make(integrated=False, notes="无对应物；目标物不存在。"),)
    )
    assert any("backlog" in e for e in bad)


def test_registered_not_integrated_with_backlog_note_passes():
    entry = make(integrated=False, notes="无对应物；目标物不存在；本版仅登记（backlog）。")
    assert validate_name_mappings((entry,)) == []


def test_service_mapping_must_name_systemd():
    bad = validate_name_mappings(
        (
            make(
                kind="service",
                win="Spooler",
                form="partial",
                linux="cups.service",
                confidence="C",
                target_exists="unknown",
                notes="近似映射。",
            ),
        )
    )
    assert any("systemd" in e for e in bad)


def test_duplicate_kind_win_is_rejected():
    bad = validate_name_mappings((make(), make()))
    assert any("重复" in e for e in bad)


def test_same_win_different_kind_is_allowed():
    entries = (make(), make(kind="path_root", win="drive"))
    assert validate_name_mappings(entries) == []


def test_path_root_requires_subtype_pseudo_name():
    bad = validate_name_mappings((make(kind="path_root", win="C:\\"),))
    assert any("子类伪名" in e for e in bad)


# --------------------------------------------------------------------------
# 查找器
# --------------------------------------------------------------------------

SYNTHETIC = (
    make(win="ProgramFiles"),
    make(win="AllUsersProfile", form="partial", linux="/usr/share", confidence="C",
         target_exists="unknown", notes="近似映射，需人工核对。"),
    make(win="drive", kind="path_root", integrated=False,
         notes="Windows 盘符在 Linux 无对应物；目标物不存在；本版仅登记（backlog）。"),
    make(win="unc", kind="path_root", integrated=False,
         notes="UNC 共享在 Linux 无对应物；目标物不存在；本版仅登记（backlog）。"),
)


def test_name_mapping_is_case_insensitive_and_strips_percent():
    for token in ("ProgramFiles", "programfiles", "%ProgramFiles%", "%PROGRAMFILES%"):
        entry = name_mapping_for(token, entries=SYNTHETIC)
        assert entry is not None and entry.win == "ProgramFiles"


def test_name_mapping_strips_quotes_and_exe_suffix():
    assert name_mapping_for('"ProgramFiles.exe"', entries=SYNTHETIC) is not None


def test_name_mapping_kind_filter():
    assert name_mapping_for("drive", kind="env_var", entries=SYNTHETIC) is None
    assert name_mapping_for("drive", kind="path_root", entries=SYNTHETIC) is not None


def test_unknown_name_returns_none():
    assert name_mapping_for("NoSuchName", entries=SYNTHETIC) is None


def test_env_mapping_for():
    entry = env_mapping_for("%AllUsersProfile%", entries=SYNTHETIC)
    assert entry is not None and entry.linux == "/usr/share"


def test_path_root_mapping_detects_drive_and_unc():
    assert path_root_mapping_for("C:\\Windows", entries=SYNTHETIC).win == "drive"
    assert path_root_mapping_for('"D:/data/x.txt"', entries=SYNTHETIC).win == "drive"
    assert path_root_mapping_for("\\\\server\\share", entries=SYNTHETIC).win == "unc"


def test_path_root_mapping_ignores_plain_paths():
    assert path_root_mapping_for("/usr/bin", entries=SYNTHETIC) is None
    assert path_root_mapping_for("a/b", entries=SYNTHETIC) is None


def test_unmappable_env_names_in_detects_none_entries():
    assert unmappable_env_names_in("echo %ProgramFiles%", entries=SYNTHETIC) == ["ProgramFiles"]


def test_unmappable_env_names_in_ignores_escaped_percent_pair():
    assert unmappable_env_names_in("echo %%ProgramFiles%%", entries=SYNTHETIC) == []


def test_unmappable_env_names_in_ignores_mapped_names():
    assert unmappable_env_names_in("echo %AllUsersProfile%", entries=SYNTHETIC) == []


def test_unmappable_env_names_in_dedupes_preserving_order():
    text = "%ProgramFiles% %ProgramFiles% %ProgramFiles%"
    assert unmappable_env_names_in(text, entries=SYNTHETIC) == ["ProgramFiles"]


def test_unmappable_env_names_in_empty_table_is_noop():
    assert unmappable_env_names_in("echo %ProgramFiles%", entries=()) == []


def test_evidence_regex_matches_corpus_quirk_paths():
    # 语料名含中文/空格/斜杠；validator 只要求 corpus/<任意>:<行号>
    assert re.match(r"^corpus/.+:\d+$", "corpus/第三方工具/devcon/i386/删除U盘.bat:1")


# --------------------------------------------------------------------------
# 首批条目（C3 路径/环境，v1.10.0a1）
# --------------------------------------------------------------------------


def test_first_batch_passes_validation():
    assert validate_name_mappings() == []


def test_first_batch_evidence_points_to_real_corpus_lines():
    assert WINDOWS_NAMES
    for item in WINDOWS_NAMES:
        assert re.match(r"^corpus/.+:\d+$", item.evidence), item.win


def test_first_batch_is_path_env_only():
    assert {item.kind for item in WINDOWS_NAMES} <= {"env_var", "path_root"}


def test_path_roots_are_registered_but_not_integrated():
    roots = [item for item in WINDOWS_NAMES if item.kind == "path_root"]
    assert {item.win for item in roots} == {"drive", "unc"}
    assert all(not item.integrated for item in roots)


def test_program_files_is_honest_todo():
    entry = env_mapping_for("%ProgramFiles%")
    assert entry is not None
    assert (entry.form, entry.linux, entry.integrated) == ("none", "", True)


def test_all_users_profile_follows_projectdata_convention():
    from bat2sh.core import rules

    entry = env_mapping_for("%AllUsersProfile%")
    assert entry is not None
    assert entry.linux == rules.BATCH_ENV_MAP["PROGRAMDATA"]


def test_env_entries_never_shadow_existing_env_map():
    from bat2sh.core import rules

    for item in WINDOWS_NAMES:
        if item.kind == "env_var":
            assert item.win.upper() not in rules.BATCH_ENV_MAP, item.win


def test_service_kind_not_populated_without_c7():
    assert [item for item in WINDOWS_NAMES if item.kind == "service"] == []
