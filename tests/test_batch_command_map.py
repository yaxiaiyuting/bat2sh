"""A 类命令干净映射测试：certutil / driverquery / assoc / ftype / %SystemRoot%。"""

from __future__ import annotations

import hashlib
from pathlib import Path


def test_certutil_md5_maps_and_runs(convert_bat, bash_run, tmp_path: Path):
    target = tmp_path / "data.txt"
    target.write_text("hello", encoding="utf-8")
    out, report = convert_bat(f'@echo off\ncertutil -hashfile "{target}" MD5\n')
    assert "md5sum" in out
    assert report.todo_count == 0
    assert report.warning_count == 1
    proc = bash_run(out)
    assert proc.returncode == 0
    assert hashlib.md5(b"hello").hexdigest() in proc.stdout


def test_certutil_sha256_maps_and_runs(convert_bat, bash_run, tmp_path: Path):
    target = tmp_path / "data.txt"
    target.write_text("hello", encoding="utf-8")
    out, report = convert_bat(f"@echo off\ncertutil -hashfile {target} SHA256\n")
    assert "sha256sum" in out
    assert report.todo_count == 0
    proc = bash_run(out)
    assert hashlib.sha256(b"hello").hexdigest() in proc.stdout


def test_certutil_other_algorithm_todo(convert_bat):
    out, report = convert_bat("@echo off\ncertutil -hashfile a.txt SHA1\n")
    assert report.todo_count == 1
    assert "# TODO" in out
    assert "md5sum" not in out
    assert "sha256sum" not in out


def test_certutil_non_hashfile_todo(convert_bat):
    out, report = convert_bat("@echo off\ncertutil -decode a.b64 a.bin\n")
    assert report.todo_count == 1


def test_driverquery_maps_to_lsmod_only(convert_bat):
    out, report = convert_bat("@echo off\ndriverquery\n")
    assert "lsmod" in out
    assert "lspci" not in out
    assert any("语义不同" in d.message for d in report.warnings)
    assert report.todo_count == 0


def test_assoc_known_extension_queries_default(convert_bat):
    out, report = convert_bat("@echo off\nassoc .txt\n")
    assert "xdg-mime query default text/plain" in out
    assert "query filetype" not in out
    assert report.todo_count == 0


def test_ftype_known_name_queries_default(convert_bat):
    out, report = convert_bat("@echo off\nftype txtfile\n")
    assert "xdg-mime query default text/plain" in out
    assert report.todo_count == 0


def test_assoc_unknown_extension_todo(convert_bat):
    out, report = convert_bat("@echo off\nassoc .xyz\n")
    assert report.todo_count == 1
    assert "# TODO" in out


def test_ftype_setting_form_todo(convert_bat):
    out, report = convert_bat("@echo off\nftype txtfile=notepad.exe\n")
    assert report.todo_count == 1
    assert "# TODO" in out


def test_systemroot_preserves_name_and_allows_override(convert_bat, bash_run, monkeypatch):
    out, _ = convert_bat("@echo off\necho %SystemRoot%\n")
    assert "${SystemRoot:-/}" in out
    monkeypatch.delenv("SystemRoot", raising=False)
    assert bash_run(out).stdout.strip() == "/"
    monkeypatch.setenv("SystemRoot", "/custom")
    assert bash_run(out).stdout.strip() == "/custom"


def test_call_set_indirect_basic(convert_bat):
    out, report = convert_bat('@echo off\ncall set "R=%%%A%%%"\n')
    assert 'R="${!A}"' in out
    assert report.todo_count == 0


def test_call_set_indirect_name_with_underscore_digits(convert_bat):
    out, _ = convert_bat('@echo off\ncall set "OUT_1=%%%VAR_2%%%"\n')
    assert 'OUT_1="${!VAR_2}"' in out


def test_call_set_indirect_runs(convert_bat, bash_run):
    text = (
        '@echo off\nset "A=target"\nset "target=resolved"\n'
        'call set "R=%%%A%%%"\necho %R%\n'
    )
    out, report = convert_bat(text)
    assert report.todo_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "resolved"


def test_call_set_unmatched_pattern_todo(convert_bat):
    out, report = convert_bat('@echo off\ncall set "R=pre_%%%A%%%"\n')
    assert report.todo_count == 1
    assert "# TODO" in out


def test_call_set_multiple_parts_todo(convert_bat):
    out, report = convert_bat('@echo off\ncall set "R=%%%A%%%%%%%%B%%%"\n')
    assert report.todo_count == 1
    assert "!A!" not in out


def test_errorlevel_warn_defaults_to_todo(convert_bat):
    out, report = convert_bat("@echo off\necho rc=%ERRORLEVEL%\n")
    assert report.todo_count == 1
    assert "# TODO" in out
    assert "${__bat2sh_rc}" not in out


def test_errorlevel_map_uses_rc_capture(convert_bat):
    out, report = convert_bat("@echo off\necho rc=%ERRORLEVEL%\n", last_exit_code="map")
    assert "# 注意：$? 只反映紧邻上一条命令的退出码" in out
    assert "__bat2sh_rc=$?" in out
    assert 'echo "rc=${__bat2sh_rc}"' in out
    assert report.todo_count == 0


def test_errorlevel_map_captures_once(convert_bat):
    out, _ = convert_bat(
        "@echo off\necho a=%ERRORLEVEL%\necho b=%ERRORLEVEL%\n", last_exit_code="map"
    )
    assert out.count("__bat2sh_rc=$?") == 1
    assert out.count("${__bat2sh_rc}") == 2


def test_errorlevel_map_runs_after_failure(convert_bat, bash_run):
    text = "@echo off\ncmd /c exit 3\necho rc=%ERRORLEVEL%\n"
    out, report = convert_bat(text, last_exit_code="map", strict_mode=False)
    assert report.todo_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0
    assert "rc=3" in proc.stdout


def test_errorlevel_map_shares_capture_with_powershell(convert_bat, convert_ps):
    bat_out, _ = convert_bat("@echo off\necho %ERRORLEVEL%\n", last_exit_code="map")
    ps_out, _ = convert_ps("Write-Output $LASTEXITCODE\n", last_exit_code="map")
    assert "__bat2sh_rc=$?" in bat_out
    assert "__bat2sh_rc=$?" in ps_out
    assert "${__bat2sh_rc}" in bat_out
    assert "${__bat2sh_rc}" in ps_out


def test_errorlevel_in_for_f_command_todo(convert_bat):
    text = '@echo off\nfor /f "delims=" %%i in (\'echo %ERRORLEVEL%\') do echo %%i\n'
    out, report = convert_bat(text)
    assert report.todo_count == 1
    assert "# TODO" in out


def test_errorlevel_warn_paren_block_stays_balanced(convert_bat):
    text = "@echo off\nif %ERRORLEVEL% equ 0 (\n    echo ok\n)\necho done\n"
    out, report = convert_bat(text)
    assert report.todo_count == 1
    assert 'echo "done"' in out
    assert not any("多余" in d.message for d in report.warnings)
