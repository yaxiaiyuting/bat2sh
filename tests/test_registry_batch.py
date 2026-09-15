"""批处理 reg 命令结构化 TODO 的回归测试（v1.6.0 阶段 B / Fix B-1）。"""

from __future__ import annotations


def test_reg_query_not_dropped(convert_bat, bash_check):
    out, report = convert_bat('@echo off\nreg query "HKLM\\SOFTWARE\\Foo" /v Bar\n')
    assert "reg query" in out
    assert r'# TODO[REG] op=read key="HKLM\SOFTWARE\Foo" value="Bar"' in out
    assert report.todo_count == 1
    assert report.todos[0].category == "registry"
    bash_check(out)


def test_reg_add_structured_write(convert_bat, bash_check):
    out, report = convert_bat(
        '@echo off\nreg add "HKCU\\Software\\MyApp" /v Setting /t REG_SZ /d value /f\n'
    )
    assert r'# TODO[REG] op=write key="HKCU\Software\MyApp" value="Setting"' in out
    assert any("可写注册表" in d.message for d in report.todos)
    bash_check(out)


def test_reg_delete_structured(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\nreg delete "HKLM\\SOFTWARE\\MyApp" /f\n')
    assert r'# TODO[REG] op=delete key="HKLM\SOFTWARE\MyApp"' in out
    bash_check(out)


def test_reg_import_export_structured(convert_bat, bash_check):
    out, _ = convert_bat(
        '@echo off\nreg export "HKLM\\SOFTWARE\\MyApp" backup.reg\nreg import backup.reg\n'
    )
    assert r'# TODO[REG] op=export key="HKLM\SOFTWARE\MyApp"' in out
    assert r'# TODO[REG] op=import key="backup.reg"' in out
    bash_check(out)


def test_regedit_structured_import(convert_bat, bash_check):
    out, report = convert_bat("@echo off\nregedit /s showall.reg\n")
    assert "# TODO[REG] op=import" in out
    assert "regedit /s showall.reg" in out
    assert report.todo_count == 1
    bash_check(out)


def test_reg_exe_structured(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\nreg.exe query "HKLM\\SOFTWARE\\Foo"\n')
    assert r'# TODO[REG] op=read key="HKLM\SOFTWARE\Foo"' in out
    bash_check(out)


def test_reg_reads_report_records(convert_bat):
    out, report = convert_bat('@echo off\nreg query "HKLM\\SOFTWARE\\Foo"\n')
    assert report.todo_count == 1
    assert report.todos[0].line == 2
    assert "手动检查" in report.todos[0].message


def test_non_reg_todo_hint_unchanged(convert_bat):
    out, _ = convert_bat("@echo off\nnet use Z: \\\\server\\share\n")
    assert "TODO[REG]" not in out
