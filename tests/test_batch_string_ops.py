"""字符串操作 %VAR:~N,M% / %VAR:old=new% 映射为 bash 参数扩展。"""

from __future__ import annotations


def test_substring_start_length(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nset "STR=Hello, World!"\necho %STR:~0,5%\n')
    assert "${STR:0:5}" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "Hello\n"


def test_substring_start_only(convert_bat):
    out, _ = convert_bat('@echo off\nset "STR=Hello, World!"\necho %STR:~7%\n')
    assert "${STR:7}" in out


def test_substring_negative_start_keeps_space(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nset "STR=Hello, World!"\necho %STR:~-3%\n')
    assert "${STR: -3}" in out
    assert "${STR:-3}" not in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "ld!\n"


def test_substring_start_length_two(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nset "STR=Hello, World!"\necho %STR:~2,4%\n')
    assert "${STR:2:4}" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "llo,\n"


def test_replace_word(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nset "STR=Hello, World!"\necho %STR:World=BAT%\n')
    assert "${STR//World/BAT}" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "Hello, BAT!\n"


def test_replace_single_char(convert_bat):
    out, _ = convert_bat('@echo off\nset "STR=Hello, World!"\necho %STR:o=0%\n')
    assert "${STR//o/0}" in out


def test_replace_delete(convert_bat):
    out, _ = convert_bat('@echo off\nset "STR=default"\necho %STR:def=%\n')
    assert "${STR//def/}" in out


def test_replace_single_char_all_occurrences(convert_bat, bash_run):
    out, _ = convert_bat('@echo off\nset "STR=foo"\necho %STR:o=0%\n')
    assert "${STR//o/0}" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "f00\n"


def test_replace_multiple_hits(convert_bat, bash_run):
    out, _ = convert_bat(
        '@echo off\nset "STR=foo bar foo baz"\necho %STR:foo=X%\n'
    )
    assert "${STR//foo/X}" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "X bar X baz\n"


def test_replace_delete_all_occurrences(convert_bat, bash_run):
    out, _ = convert_bat(
        '@echo off\nset "STR=foo bar foo"\necho %STR:o=%\n'
    )
    assert "${STR//o/}" in out
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "f bar f\n"


def test_wildcard_replace_is_todo(convert_bat):
    out, report = convert_bat("@echo off\nset \"STR=abc\"\necho %STR:*:=%\n")
    assert report.todo_count == 1
    assert "# TODO" in out
    assert "%STR:*:=%" in out


def test_wildcard_in_old_part_is_todo(convert_bat):
    out, report = convert_bat("@echo off\nset \"STR=abc\"\necho %STR:a*=b%\n")
    assert report.todo_count == 1
    assert "# TODO" in out


def test_underscore_variable_name(convert_bat):
    out, _ = convert_bat('@echo off\nset "MY_STR=abcdef"\necho %MY_STR:~1,2%\n')
    assert "${MY_STR:1:2}" in out


def test_multiple_ops_same_line(convert_bat):
    out, _ = convert_bat(
        '@echo off\nset "STR=Hello, World!"\necho %STR:~0,2%_%STR:~-2%\n'
    )
    assert "${STR:0:2}_${STR: -2}" in out


def test_tilde_n0_not_misparsed_as_string_op(convert_bat):
    out, _ = convert_bat("@echo off\necho %~n0\n")
    assert '"$0"' in out
    assert "${n0" not in out
