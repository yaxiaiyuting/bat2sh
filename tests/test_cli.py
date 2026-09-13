"""CLI 参数与退出码的回归测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bat2sh import __version__
from bat2sh.cli import main

CLEAN_BAT = "@echo off\necho hello\n"
TODO_BAT = "@echo off\nfor /f \"delims=,\" %%i in ('dir /b') do echo %%i\n"


def make_bat(tmp_path: Path, name: str = "demo.bat", text: str = CLEAN_BAT) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_repo_package_is_imported():
    import bat2sh

    repo_python = Path(__file__).resolve().parents[1] / "python"
    assert Path(bat2sh.__file__).resolve().parents[1] == repo_python


# ----------------------------------------------------------------------
# 基本参数解析
# ----------------------------------------------------------------------
def test_version_option(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_inputs_prints_help_and_returns_1(capsys):
    code = main([])
    assert code == 1
    assert "usage" in capsys.readouterr().out.lower()


def test_cli_flag_compatibility(tmp_path, capsys):
    path = make_bat(tmp_path)
    code = main(["--cli", str(path), "--print"])
    assert code == 0
    assert "echo \"hello\"" in capsys.readouterr().out


def test_output_flag_with_multiple_inputs_returns_1(tmp_path, capsys):
    first = make_bat(tmp_path, "a.bat")
    second = make_bat(tmp_path, "b.bat")
    code = main([str(first), str(second), "-o", str(tmp_path / "x.sh")])
    assert code == 1
    assert "仅适用于单个输入文件" in capsys.readouterr().err


# ----------------------------------------------------------------------
# --print 与退出码
# ----------------------------------------------------------------------
def test_print_only_exit_0(tmp_path, capsys):
    path = make_bat(tmp_path)
    code = main([str(path), "--print"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("#!/usr/bin/env bash\n")
    assert not (tmp_path / "demo.sh").exists()


def test_print_only_todo_without_flag_exit_0(tmp_path, capsys):
    path = make_bat(tmp_path, text=TODO_BAT)
    code = main([str(path), "--print"])
    out = capsys.readouterr().out
    assert code == 0
    assert "# TODO: 手动检查" in out


def test_print_only_todo_with_fail_on_todo_exit_3(tmp_path):
    path = make_bat(tmp_path, text=TODO_BAT)
    assert main([str(path), "--print", "--fail-on-todo"]) == 3


def test_fail_on_todo_aggregates_multiple_files(tmp_path):
    todo = make_bat(tmp_path, "todo.bat", TODO_BAT)
    clean = make_bat(tmp_path, "clean.bat")
    assert main([str(todo), str(clean), "--outdir", str(tmp_path / "out")]) == 0
    assert (
        main(
            [str(todo), str(clean), "--outdir", str(tmp_path / "out"), "--fail-on-todo"]
        )
        == 3
    )


def test_unsupported_suffix_print_returns_2(tmp_path, capsys):
    path = tmp_path / "note.txt"
    path.write_text("hello\n", encoding="utf-8")
    code = main([str(path), "--print"])
    assert code == 2
    assert "不支持的源文件类型" in capsys.readouterr().err


def test_unsupported_suffix_write_returns_2(tmp_path, capsys):
    path = tmp_path / "note.txt"
    path.write_text("hello\n", encoding="utf-8")
    code = main([str(path)])
    assert code == 2
    assert "不支持的源文件类型" in capsys.readouterr().err


def test_missing_file_returns_2(tmp_path, capsys):
    code = main([str(tmp_path / "missing.bat")])
    assert code == 2
    assert "文件不存在" in capsys.readouterr().err


# ----------------------------------------------------------------------
# 写出行为
# ----------------------------------------------------------------------
def test_single_output_writes_executable(tmp_path):
    path = make_bat(tmp_path)
    out_path = tmp_path / "custom.sh"
    assert main([str(path), "-o", str(out_path)]) == 0
    assert out_path.is_file()
    assert os.access(out_path, os.X_OK)


def test_no_exec_does_not_set_executable_bit(tmp_path):
    path = make_bat(tmp_path)
    out_path = tmp_path / "custom.sh"
    assert main([str(path), "-o", str(out_path), "--no-exec"]) == 0
    assert out_path.is_file()
    assert not os.access(out_path, os.X_OK)


def test_outdir_and_suffix(tmp_path):
    path = make_bat(tmp_path)
    outdir = tmp_path / "generated"
    assert main([str(path), "--outdir", str(outdir), "--suffix", ".bash"]) == 0
    assert (outdir / "demo.bash").is_file()


def test_print_only_writes_nothing_to_disk(tmp_path):
    path = make_bat(tmp_path)
    assert main([str(path), "--print"]) == 0
    assert list(tmp_path.glob("*.sh")) == []


def test_no_overwrite_refuses_and_keeps_old_content(tmp_path, capsys):
    path = make_bat(tmp_path)
    out_path = tmp_path / "demo.sh"
    out_path.write_text("OLD\n", encoding="utf-8")
    code = main([str(path), "--no-overwrite"])
    assert code == 2
    assert out_path.read_text(encoding="utf-8") == "OLD\n"
    assert "输出文件已存在" in capsys.readouterr().err


def test_backup_existing_creates_backup(tmp_path):
    path = make_bat(tmp_path)
    out_path = tmp_path / "demo.sh"
    out_path.write_text("OLD\n", encoding="utf-8")
    assert main([str(path), "--backup"]) == 0
    backups = list(tmp_path.glob("demo.sh.bak-*"))
    assert backups, "应生成输出备份文件"
    assert out_path.read_text(encoding="utf-8") != "OLD\n"


def test_backup_source_creates_source_backup(tmp_path):
    path = make_bat(tmp_path)
    assert main([str(path), "--backup-source"]) == 0
    assert list(tmp_path.glob("demo.bat.bak-*"))


# ----------------------------------------------------------------------
# 报告与静默
# ----------------------------------------------------------------------
def test_report_plain_text_on_stderr(tmp_path, capsys):
    path = make_bat(tmp_path)
    assert main([str(path), "--report"]) == 0
    captured = capsys.readouterr()
    assert "已转换行数" in captured.err
    assert "警告数量" in captured.err
    assert "已转换行数" not in captured.out


def test_quiet_suppresses_status_output(tmp_path, capsys):
    path = make_bat(tmp_path)
    assert main([str(path), "--quiet"]) == 0
    assert capsys.readouterr().out == ""


def test_encoding_override_reads_gbk(tmp_path, capsys):
    path = tmp_path / "gbk.bat"
    path.write_bytes("@echo off\necho 中文测试\n".encode("gbk"))
    code = main([str(path), "--print", "--encoding", "gbk"])
    assert code == 0
    assert "中文测试" in capsys.readouterr().out
