"""v1.9.0：053 块栈修复——行尾未配平 `else (` 不再提前闭合，`))` 正确收尾。

根因：`_convert_if` 对行内 `else (` 的未配平分支仍 `pop`+补 `fi`，与
`_close_block_line`（会 push `await_paren_close` 块）不对称 → 块栈失同步 →
循环体出循环、`%%i` 逸出、`))` 落空栈报「多余的 ')'」。

语料证据：`将所在目录的BAT文件合并成一个BAT文件…bat:12`（for /f + 嵌套 if/else）。
"""

from __future__ import annotations

REPRO = (
    "@echo off\n"
    "for %%i in (a b) do if %%i==a (echo A ) else (if %%i==b (echo B ) else (\n"
    "echo body1\n"
    "echo body2\n"
    "))\n"
    "echo after\n"
)


def test_nested_else_paren_body_stays_inside_loop(convert_bat):
    out, _ = convert_bat(REPRO)
    assert "多余的 ')'" not in out
    lines = out.splitlines()
    i_body = next(i for i, l in enumerate(lines) if 'echo "body2"' in l)
    i_done = next(i for i, l in enumerate(lines) if l.strip() == "done")
    i_after = next(i for i, l in enumerate(lines) if 'echo "after"' in l)
    assert i_body < i_done < i_after
    assert sum(1 for l in lines[i_body:i_done] if l.strip() == "fi") == 2


def test_nested_else_paren_loop_var_not_leaked(convert_bat):
    out, report = convert_bat(
        "@echo off\n"
        "for %%i in (a b) do if %%i==a (echo A ) else (if %%i==b (echo B ) else (\n"
        "echo %%i\n"
        "))\n"
    )
    assert "${i}" in out
    assert "%i" not in out
    assert [w for w in report.warnings if "循环变量" in w.message] == []


def test_double_paren_close_pop_two_blocks(convert_bat):
    out, _ = convert_bat(
        "@echo off\n"
        "if 1==1 (\n"
        "if 2==2 (\n"
        "echo deep\n"
        "))\n"
    )
    assert "多余的 ')'" not in out
    assert out.count("fi") == 2


def test_corpus_053_shape_keeps_body_lines_indented(convert_bat):
    out, report = convert_bat(
        "@echo off\n"
        "for /f %%i in ('dir/b *.bat') do if %%i==a (echo x) else (if %%i==b (echo y) else (\n"
        "set/a a+=1\n"
        "type %%i>>t.txt\n"
        "))\n"
    )
    lines = out.splitlines()
    i_type = next(i for i, l in enumerate(lines) if "t.txt" in l)
    i_done = next(i for i, l in enumerate(lines) if l.strip().startswith("done"))
    assert i_type < i_done
    assert lines[i_type].startswith(" ")


def test_unbalanced_else_without_nested_if(convert_bat):
    out, _ = convert_bat(
        "@echo off\n"
        "for %%i in (a b) do if %%i==a (echo A) else (\n"
        "echo B\n"
        ")\n"
        "echo after\n"
    )
    assert "多余的 ')'" not in out
    assert out.index('echo "B"') < out.index("done") < out.index('echo "after"')
