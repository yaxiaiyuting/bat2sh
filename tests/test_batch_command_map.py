"""A 类命令干净映射测试：certutil / driverquery / assoc / ftype / SystemRoot 等。"""

from __future__ import annotations

import hashlib
import re
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


def test_if_slash_i_variables_lowercase_expansion(convert_bat, bash_run):
    text = '@echo off\nset "A=HELLO"\nset "B=hello"\nif /i "%A%"=="%B%" echo same\n'
    out, report = convert_bat(text)
    assert "[[ ${A,,} == ${B,,} ]]" in out
    assert "shopt" not in out
    assert "nocasematch" not in out
    assert report.todo_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0
    assert "same" in proc.stdout


def test_if_slash_i_literals_compare_true(convert_bat, bash_run):
    out, report = convert_bat('@echo off\nif /i "HELLO"=="hello" echo same\n')
    assert report.todo_count == 0
    assert "shopt" not in out
    proc = bash_run(out)
    assert proc.returncode == 0
    assert "same" in proc.stdout


def test_if_slash_i_case_difference_runs(convert_bat, bash_run):
    text = (
        '@echo off\nset "A=Alpha"\nset "B=ALPHA"\n'
        'if /i "%A%"=="%B%" echo eq\n'
        'if /i "%A%"=="beta" echo ne\n'
    )
    out, _ = convert_bat(text)
    proc = bash_run(out)
    assert proc.returncode == 0
    assert "eq" in proc.stdout
    assert "ne" not in proc.stdout


def test_if_slash_i_wildcard_todo(convert_bat):
    out, report = convert_bat('@echo off\nif /i "%A%"=="*.txt" echo x\n')
    assert report.todo_count == 1
    assert "# TODO" in out
    assert "${A,,}" not in out


def test_if_slash_i_complex_expression_todo(convert_bat):
    out, report = convert_bat('@echo off\nif /i "%A%_x"=="%B%_x" echo x\n')
    assert report.todo_count == 1
    assert "# TODO" in out


def test_date_maps_to_iso_and_runs(convert_bat, bash_run):
    out, report = convert_bat("@echo off\necho %DATE%\n")
    assert "$(date +%Y-%m-%d)" in out
    assert any("区域设置" in d.message for d in report.warnings)
    proc = bash_run(out)
    assert proc.returncode == 0
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", proc.stdout.strip())


def test_time_maps_to_iso_and_runs(convert_bat, bash_run):
    out, report = convert_bat("@echo off\necho %TIME%\n")
    assert "$(date +%H:%M:%S)" in out
    assert any("区域设置" in d.message for d in report.warnings)
    proc = bash_run(out)
    assert proc.returncode == 0
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", proc.stdout.strip())


def test_date_in_for_f_string_todo(convert_bat):
    text = '@echo off\nfor /f "tokens=1-3 delims=-" %%a in ("%DATE%") do echo %%a\n'
    out, report = convert_bat(text)
    assert report.todo_count == 1
    assert "$(date" not in out
    assert "# TODO" in out


def test_time_in_for_f_command_todo(convert_bat):
    text = "@echo off\nfor /f \"delims=\" %%i in ('echo %TIME%') do echo %%i\n"
    out, report = convert_bat(text)
    assert report.todo_count == 1
    assert "$(date" not in out


def test_choice_basic_maps_to_read(convert_bat):
    out, report = convert_bat("@echo off\nchoice /c YN /t 1 /d Y\n")
    assert "read -r -n 1 -t 1" in out
    assert any("choice" in d.message for d in report.warnings)
    assert report.todo_count == 0


def test_choice_with_prompt_maps(convert_bat):
    out, _ = convert_bat('@echo off\nchoice /c YN /m "继续?"\n')
    assert "read -r -n 1" in out
    assert '-p "继续?"' in out
    assert " -t " not in out


def test_choice_followed_by_errorlevel_todo(convert_bat):
    text = "@echo off\nchoice /c YN /t 5 /d Y\necho 选择了 %ERRORLEVEL%\n"
    out, report = convert_bat(text)
    assert report.todo_count >= 1
    assert "read -r" not in out


def test_simple_pipeline_converts(convert_bat):
    out, report = convert_bat("@echo off\ntasklist | findstr explorer\n")
    assert "ps aux | grep explorer" in out
    assert report.todo_count == 0


def test_pipeline_with_redirect_todo(convert_bat):
    out, report = convert_bat("@echo off\ndir 2>nul | findstr x\n")
    assert report.todo_count == 1
    assert "# TODO" in out
    executable = [
        line
        for line in out.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert not any("grep" in line for line in executable)


def test_multistage_pipeline_todo(convert_bat):
    out, report = convert_bat("@echo off\ndir | findstr a | findstr b\n")
    assert report.todo_count == 1
    assert "# TODO" in out


def test_pipeline_with_ampersand_todo(convert_bat):
    out, report = convert_bat("@echo off\ndir | findstr x && echo ok\n")
    assert report.todo_count == 1
    assert "# TODO" in out


def test_pipeline_inside_for_f_command_todo(convert_bat):
    text = "@echo off\nfor /f \"delims=\" %%i in ('dir ^| findstr x') do echo %%i\n"
    out, report = convert_bat(text)
    assert report.todo_count == 1
    assert "# TODO" in out
    assert "grep" not in out


def test_delayed_errorlevel_warn_is_todo(convert_bat):
    text = "@echo off\nsetlocal enabledelayedexpansion\nif !ERRORLEVEL! neq 0 echo fail\n"
    out, report = convert_bat(text)
    assert report.todo_count >= 1
    assert "${ERRORLEVEL}" not in out
    assert "__bat2sh_rc" not in out


def test_delayed_errorlevel_map_uses_rc(convert_bat):
    text = "@echo off\nsetlocal enabledelayedexpansion\nif !ERRORLEVEL! neq 0 echo fail\n"
    out, report = convert_bat(text, last_exit_code="map")
    assert "${__bat2sh_rc}" in out
    assert "__bat2sh_rc=$?" in out
    assert report.todo_count == 0


def test_delayed_variable_still_expands(convert_bat):
    text = '@echo off\nsetlocal enabledelayedexpansion\nset "X=1"\necho !X!\n'
    out, _ = convert_bat(text)
    assert 'echo "${X}"' in out
    assert "!X!" not in out


def test_delayed_errorlevel_map_runs(convert_bat, bash_run):
    text = (
        "@echo off\nsetlocal enabledelayedexpansion\ncmd /c exit 3\n"
        "if !ERRORLEVEL! neq 0 echo failed\necho done\n"
    )
    out, report = convert_bat(text, last_exit_code="map", strict_mode=False)
    assert report.todo_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "failed" in proc.stdout
    assert "done" in proc.stdout


def test_type_nul_creates_empty_file(convert_bat, bash_run, tmp_path):
    out, report = convert_bat("@echo off\ntype nul > empty.txt\n")
    assert report.todo_count == 0
    assert ": >" in out
    script = f'cd "{tmp_path}"\n' + out
    proc = bash_run(script)
    assert proc.returncode == 0, proc.stderr
    target = tmp_path / "empty.txt"
    assert target.is_file()
    assert target.stat().st_size == 0


def test_copy_nul_creates_empty_file(convert_bat, bash_run, tmp_path):
    out, report = convert_bat("@echo off\ncopy nul empty2.txt\n")
    assert report.todo_count == 0
    assert "/dev/null" in out
    script = f'cd "{tmp_path}"\n' + out
    proc = bash_run(script)
    assert proc.returncode == 0, proc.stderr
    target = tmp_path / "empty2.txt"
    assert target.is_file()
    assert target.stat().st_size == 0


def test_type_regular_file_still_cat(convert_bat):
    out, _ = convert_bat("@echo off\ntype a.txt\n")
    assert "cat a.txt" in out


def test_nul_redirect_still_devnull(convert_bat):
    out, _ = convert_bat("@echo off\necho hi >nul\n")
    assert ">/dev/null" in out


def test_unicode_variable_declaration_and_reference_match(convert_bat):
    text = '@echo off\nset "中文变量=中文值"\necho %中文变量%\n'
    out, _ = convert_bat(text)
    assert '____="中文值"' in out
    assert 'echo "${____}"' in out
    assert "%中文变量%" not in out
    assert "${中文变量}" not in out


def test_unicode_path_preserved(convert_bat):
    text = '@echo off\nset "中文路径=C:\\测试目录"\necho %中文路径%\n'
    out, _ = convert_bat(text)
    assert "C:/测试目录" in out
    assert "C:\\\\" not in out


def test_unicode_variable_runs(convert_bat, bash_run):
    text = '@echo off\nset "中文变量=中文值"\necho %中文变量%\n'
    out, _ = convert_bat(text)
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "中文值" in proc.stdout


def test_unicode_name_collision_warns(convert_bat):
    text = (
        '@echo off\nset "中文变量=中文值"\nset "中文路径=C:\\测试目录"\n'
        "echo %中文路径%\n"
    )
    out, report = convert_bat(text)
    assert any("重命名后同名" in d.message for d in report.warnings)
