"""v1.9.0 丢失检测：任何源行都必须落为代码、注释或诊断，不得静默蒸发。

背景：`cmd_todo_hint`（wmic/subst/net/attrib/… 等）此前 `return None`，被调用方
`if line is None: return []` 整行丢弃——命令既不执行也不留 `# TODO` 标记。
语料证据：`013 为Administrator改名.bat`（Wmic 整条蒸发，产物近空脚本）、
`023 删除用户.bat`、`079 文件夹变磁盘.bat`、`001 C盘防毒批处理.bat`（134 条 attrib）。
"""

from __future__ import annotations

import pytest

TODO_HINT_COMMANDS = (
    "Wmic ComputerSystem Where \"Name='Administrator'\" Call ReName \"X\"",
    "subst q: F:\\桌面\\RaySource",
    "net user 123 /delete",
    "attrib +h foo.txt",
)


@pytest.mark.parametrize("command", TODO_HINT_COMMANDS)
def test_todo_hint_command_emits_explicit_todo(convert_bat, command):
    out, report = convert_bat("@echo off\n" + command + "\n")
    assert "# TODO: 手动检查: " in out
    assert report.todo_count == 1


def test_todo_hint_command_not_emitted_as_executable(convert_bat):
    out, _ = convert_bat("@echo off\nsubst q: F:\\x\n")
    assert not any(
        line.strip().startswith("subst") for line in out.splitlines()
    )


def test_noop_directives_do_not_trigger_loss_warning(convert_bat):
    out, report = convert_bat("@echo off & setlocal enabledelayedexpansion\necho hi\n")
    assert [w for w in report.warnings if w.category == "loss"] == []
    assert 'echo "hi"' in out


@pytest.mark.parametrize(
    "line",
    ["@echo off&color b", "@echo off & setlocal enabledelayedexpansion", "color 0a"],
)
def test_single_noop_line_has_no_loss_warning(convert_bat, line):
    _, report = convert_bat(line + "\n")
    assert [w for w in report.warnings if w.category == "loss"] == []


def test_source_lines_accounted_when_only_todo_commands(convert_bat):
    source = "@echo off\n" + "\n".join(TODO_HINT_COMMANDS) + "\n"
    out, report = convert_bat(source)
    todo_lines = [l for l in out.splitlines() if l.lstrip().startswith("# TODO")]
    assert len(todo_lines) == len(TODO_HINT_COMMANDS) == report.todo_count
