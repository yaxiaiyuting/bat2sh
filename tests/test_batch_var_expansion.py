"""v1.8.1 归因轮：变量展开的两个真实缺陷修复回归。"""

from __future__ import annotations


def test_adjacent_variables_expand(convert_bat, bash_check):
    out, _ = convert_bat(
        "@echo off\nset name=%file_n%%num%%file_x%\necho %A%%B%%C%\n", bash_check=False
    )
    bash_check(out)
    assert 'name="${file_n:-}${num:-}${file_x:-}"' in out
    assert 'echo "${A:-}${B:-}${C:-}"' in out


def test_escaped_percent_still_works(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\necho 100%% done\n", bash_check=False)
    bash_check(out)
    assert 'echo "100% done"' in out


def test_arith_modulo_and_random(convert_bat, bash_run):
    out, report = convert_bat(
        "@echo off\nset /a num=%random%%%6+1\necho %num%\n", bash_check=False
    )
    assert report.error_count == 0
    assert "num=$(( $RANDOM%6+1 ))" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert 1 <= int(proc.stdout.strip()) <= 6


def test_arith_compound_modulo_assign(convert_bat, bash_run):
    out, _ = convert_bat(
        "@echo off\nset /a x=10\nset /a x%%=3\necho %x%\n", bash_check=False
    )
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "1"


def test_for_variable_in_arithmetic_keeps_loop_var(convert_bat, bash_check, bash_run):
    out, report = convert_bat(
        "@echo off\nfor %%i in (2 3) do set /a S=%%i*%%i\necho %S%\n", bash_check=False
    )
    assert report.error_count == 0
    bash_check(out)
    assert "S=$(( ${i}*${i} ))" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "9"


def test_set_a_reads_unset_variable_as_zero(convert_bat, bash_check, bash_run):
    out, report = convert_bat("@echo off\nset /a a=%a%+1\necho %a%\n", bash_check=False)
    assert report.error_count == 0
    bash_check(out)
    assert "a=$(( ${a:-0}+1 ))" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "1"


def test_set_a_does_not_guard_loop_variable(convert_bat, bash_check):
    out, _ = convert_bat(
        "@echo off\nfor %%i in (2 3) do set /a S=%%i*%%i\necho %S%\n", bash_check=False
    )
    bash_check(out)
    assert "S=$(( ${i}*${i} ))" in out
    assert "${i:-0}" not in out
