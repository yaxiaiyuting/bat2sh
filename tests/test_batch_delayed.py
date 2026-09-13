"""延迟扩展 !VAR! / !%NAME%! 映射为 bash 变量与间接引用。"""

from __future__ import annotations

DELAYED = "setlocal enabledelayedexpansion\n"


def test_plain_delayed_variable(convert_bat, bash_run):
    out, _ = convert_bat(
        "@echo off\n" + DELAYED + 'set "VAR=hello"\necho !VAR!\n'
    )
    assert "${VAR}" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "hello\n"


def test_indirect_delayed_variable(convert_bat, bash_run):
    out, _ = convert_bat(
        "@echo off\n"
        + DELAYED
        + 'set "NAME=DYNAMIC"\nset "DYNAMIC=动态值"\necho !%NAME%!\n'
    )
    assert "${!NAME}" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "动态值\n"


def test_nested_delayed_assignment(convert_bat, bash_run):
    out, _ = convert_bat(
        "@echo off\n"
        + DELAYED
        + 'set "A=B"\nset "B=Value"\nset "R=!%A%!"\necho %R%\n'
    )
    assert 'R="${!A}"' in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "Value\n"


def test_without_delayed_expansion_keeps_literal(convert_bat):
    out, _ = convert_bat('@echo off\nset "X=1"\necho !X!\n')
    assert "!X!" in out
    assert "${X}" not in out


def test_mixed_percent_and_delayed(convert_bat):
    out, _ = convert_bat(
        "@echo off\n" + DELAYED + 'set "X=1"\nset "Y=2"\necho %X%!Y!\n'
    )
    assert "${X}${Y}" in out


def test_runtime_matches_source_semantics(convert_bat, bash_run):
    out, _ = convert_bat(
        "@echo off\n"
        + DELAYED
        + 'set "VAR_NAME=DYNAMIC"\n'
        + 'set "DYNAMIC=这是动态变量"\n'
        + "echo 延迟扩展: !%VAR_NAME%!\n"
        + 'set "A=B"\n'
        + 'set "B=Value"\n'
        + 'set "RESULT2=!%A%!"\n'
        + "echo 延迟嵌套: %RESULT2%\n"
    )
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "延迟扩展: 这是动态变量\n延迟嵌套: Value\n"
