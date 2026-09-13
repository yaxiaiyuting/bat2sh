"""bash -n 后置校验（安全网）测试：失败降级为注释、--no-bash-check 跳过。"""

from __future__ import annotations

from bat2sh.cli import main
from bat2sh.core.batch import BatchConverter
from bat2sh.core.settings import ConvertSettings

BROKEN = "#!/usr/bin/env bash\nif\n"


def broken_converter(monkeypatch, **options) -> BatchConverter:
    converter = BatchConverter(ConvertSettings(**options), "broken.bat")
    monkeypatch.setattr(converter, "_compose", lambda: BROKEN)
    return converter


def test_broken_output_is_degraded(monkeypatch, bash_check):
    converter = broken_converter(monkeypatch)
    out = converter.convert("@echo off\necho hi\n")
    assert "未通过 bash -n" in out
    assert "原脚本内容（保留为注释，供人工转换）:" in out
    assert "# echo hi" in out
    bash_check(out)
    assert converter.report.todo_count == 1
    assert any("bash -n" in d.message for d in converter.report.warnings)


def test_valid_output_not_degraded(convert_bat):
    out, report = convert_bat("@echo off\necho hi\n")
    assert "未通过 bash -n" not in out
    assert report.todo_count == 0


def test_no_bash_check_skips_validation(monkeypatch):
    converter = broken_converter(monkeypatch, bash_check=False)
    out = converter.convert("@echo off\necho hi\n")
    assert "未通过 bash -n" not in out
    assert out == BROKEN
    assert converter.report.todo_count == 0


def test_degraded_script_is_refused_by_run(tmp_path, monkeypatch):
    monkeypatch.setattr(BatchConverter, "_compose", lambda self: BROKEN)
    bat = tmp_path / "broken.bat"
    bat.write_text("@echo off\necho hi\n", encoding="utf-8")
    assert main([str(bat), "--run", "--yes"]) == 4


def test_cli_no_bash_check_keeps_broken_output(tmp_path, monkeypatch):
    monkeypatch.setattr(BatchConverter, "_compose", lambda self: BROKEN)
    bat = tmp_path / "broken.bat"
    bat.write_text("@echo off\necho hi\n", encoding="utf-8")
    out_path = tmp_path / "broken.sh"
    assert main([str(bat), "-o", str(out_path), "--no-bash-check"]) == 0
    assert out_path.read_text(encoding="utf-8") == BROKEN


def test_cli_default_writes_degraded_output(tmp_path, monkeypatch):
    monkeypatch.setattr(BatchConverter, "_compose", lambda self: BROKEN)
    bat = tmp_path / "broken.bat"
    bat.write_text("@echo off\necho hi\n", encoding="utf-8")
    out_path = tmp_path / "broken.sh"
    assert main([str(bat), "-o", str(out_path)]) == 0
    written = out_path.read_text(encoding="utf-8")
    assert "未通过 bash -n" in written
    assert "# echo hi" in written
