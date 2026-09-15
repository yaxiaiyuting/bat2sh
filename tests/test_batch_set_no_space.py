"""`set/a`、`set/p` 无空格形态归一化回归测试。

语料依据（v1.4.1 沙箱体检 §10，046-bat-master-汉字横排变竖排---转置.bat）：
``set/a Ye-=1`` / ``set/a Gu+=1`` 之前原样透传为命令（`set/a: No such file or directory`）。
batch 允许 ``set`` 与 ``/a``/``/p`` 之间无空格。
"""

from __future__ import annotations


def test_set_a_without_space_is_arithmetic(convert_bat, bash_check, bash_run):
    out, report = convert_bat("@echo off\nset/a x=1+2\necho %x%\n")
    bash_check(out)
    assert "x=$(( 1+2 ))" in out
    assert report.todo_count == 0
    proc = bash_run(out)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "3\n"


def test_set_a_compound_operator_without_space(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nset/a Ye-=1\nset/a Gu+=1\n")
    bash_check(out)
    assert "Ye=$(( Ye - (1) ))" in out
    assert "Gu=$(( Gu + (1) ))" in out


def test_set_p_with_variable_without_space(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nset/p x=prompt\necho %x%\n")
    bash_check(out)
    assert 'read -rp "prompt" x' in out


def test_set_p_prompt_only_without_space_unchanged(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nset/p=%v%<nul\n")
    bash_check(out)
    assert 'printf \'%s\' "${v:-}"' in out


def test_set_with_space_not_regressed(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nset /a n=1\nset /a n+=1\n")
    bash_check(out)
    assert "n=$(( 1 ))" in out
    assert "n=$(( n + (1) ))" in out


def test_set_slash_equals_not_treated_as_switch(convert_bat):
    out, _ = convert_bat("@echo off\nset/a=y\n")
    assert "set/a=y" in out
