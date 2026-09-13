"""未赋值变量引用安全网：set -u 下补 ${NAME:-}，已赋值引用保持不变。"""

from __future__ import annotations


def test_unset_env_var_ref_guarded(convert_bat, bash_run):
    out, _ = convert_bat("@echo off\necho 域: %USERDOMAIN%\n")
    assert "${USERDOMAIN:-}" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "域: \n" in proc.stdout


def test_assigned_var_ref_unchanged(convert_bat):
    out, _ = convert_bat('@echo off\nset "X=1"\necho %X%\n')
    assert 'echo "${X}"' in out
    assert "${X:-}" not in out


def test_var_assigned_only_in_todo_block_is_guarded(convert_bat, bash_run):
    out, _ = convert_bat(
        '@echo off\nfor /f "tokens=1" %%a in ("%DATE%") do (\n'
        '    set "YEAR=%%a"\n)\necho 年=%YEAR%\n'
    )
    assert "${YEAR:-}" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr


def test_if_condition_unset_var_guarded(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nif "%UNDEF_V%"=="" echo empty\n')
    assert '[ "${UNDEF_V:-}" = "" ]' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert "empty" in proc.stdout


def test_loop_var_ref_not_guarded(convert_bat):
    out, _ = convert_bat("@echo off\nfor /f %%a in ('dir /b') do echo %%a\n")
    assert "${a:-}" not in out


def test_existing_default_forms_untouched(convert_bat):
    out, _ = convert_bat("@echo off\necho %SystemRoot%\n")
    assert "${SystemRoot:-/}" in out
