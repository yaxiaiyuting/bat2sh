"""set /a 算术转换测试：取模、位运算、进制、复合赋值与变量。"""

from __future__ import annotations

import pytest


def run_assignment(convert_bat, bash_run, line: str) -> str:
    out, report = convert_bat(f"@echo off\n{line}\necho %R%\n")
    assert report.todo_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_modulo_not_misconverted_to_dollar(convert_bat, bash_run):
    out, report = convert_bat("@echo off\nset /a R=20%%3\necho %R%\n")
    assert "20%3" in out
    assert "$3" not in out
    assert report.todo_count == 0
    assert bash_run(out).stdout.strip() == "2"


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("10+20", "30"),
        ("20-3", "17"),
        ("6*7", "42"),
        ("20/4", "5"),
        ("20%%3", "2"),
        ("(10+20)*3/2-5", "40"),
    ],
)
def test_basic_operators(expr, expected, convert_bat, bash_run):
    assert run_assignment(convert_bat, bash_run, f"set /a R={expr}") == expected


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("5 & 3", "1"),
        ("5 | 3", "7"),
        ("5 ^ 3", "6"),
        ("~5", "-6"),
        ("1 << 3", "8"),
        ("16 >> 2", "4"),
    ],
)
def test_bitwise_operators(expr, expected, convert_bat, bash_run):
    assert run_assignment(convert_bat, bash_run, f'set /a "R={expr}"') == expected


@pytest.mark.parametrize("expr,expected", [("0x1F", "31"), ("010", "8")])
def test_hex_and_octal_literals(expr, expected, convert_bat, bash_run):
    assert run_assignment(convert_bat, bash_run, f"set /a R={expr}") == expected


@pytest.mark.parametrize(
    "op,expected",
    [("+=5", "15"), ("-=4", "6"), ("*=3", "30"), ("/=5", "2"), ("%%=3", "1")],
)
def test_compound_assignments(op, expected, convert_bat, bash_run):
    out, report = convert_bat(f"@echo off\nset /a R=10\nset /a R{op}\necho %R%\n")
    assert report.todo_count == 0
    assert bash_run(out).stdout.strip() == expected


def test_quoted_expression(convert_bat, bash_run):
    assert run_assignment(convert_bat, bash_run, 'set /a "R=10+20"') == "30"


def test_variables_with_modulo(convert_bat, bash_run):
    text = "@echo off\nset /a A=10\nset /a B=3\nset /a R=%A% %% %B%\necho %R%\n"
    out, report = convert_bat(text)
    assert "$3" not in out
    assert report.todo_count == 0
    assert bash_run(out).stdout.strip() == "1"
