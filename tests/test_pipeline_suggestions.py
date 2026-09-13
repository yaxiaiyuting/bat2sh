"""复杂管道 TODO 参考建议测试：纯注释、三层置信度、for /f 保护。"""

from __future__ import annotations

from bat2sh.cli import main
from bat2sh.core.suggestions import split_pipeline_segments, suggest_pipeline


def suggest_body(original: str) -> str:
    lines = suggest_pipeline(original)
    assert lines is not None, f"应生成建议: {original}"
    return "\n".join(lines)


def test_dir_pipeline_is_medium_confidence():
    body = suggest_body("dir | findstr x")
    assert "参考(中)" in body
    assert "ls | grep x" in body
    assert "差异:" in body


def test_netstat_pipeline_is_medium_with_difference():
    body = suggest_body("netstat -an | findstr LISTENING")
    assert "ss -an | grep LISTENING" in body
    assert "参考(中)" in body
    assert "差异:" in body


def test_sc_query_pipeline_maps_2nul():
    body = suggest_body("sc query wuauserv 2>nul | findstr STATE")
    assert "systemctl is-active wuauserv 2>/dev/null" in body
    assert "grep STATE" in body
    assert "参考(中)" in body


def test_wmic_pipeline_is_low_with_idea_only():
    body = suggest_body("wmic os get Caption | findstr Caption")
    assert "参考(低)" in body
    assert "/etc/os-release" in body or "lsb_release" in body
    assert "说明:" in body
    assert "差异:" not in body


def test_longest_pipeline_uses_lowest_confidence():
    medium = suggest_body("type a.txt | findstr x | tasklist")
    assert "参考(中)" in medium
    assert "cat a.txt | grep x | ps aux" in medium

    low = suggest_body("type a.txt | findstr x | wmic cpu get Name")
    assert "参考(低)" in low
    assert "lscpu" in low or "/proc/cpuinfo" in low


def test_escaped_pipe_is_not_a_separator():
    segments = split_pipeline_segments('findstr "a^|b" file.txt | findstr x')
    assert len(segments) == 2
    assert "^|" in segments[0]
    body = suggest_body('findstr "a^|b" file.txt | findstr x')
    assert "参考(高)" in body
    assert 'grep "a^|b" file.txt | grep x' in body


def test_reg_query_pipeline_is_low():
    body = suggest_body("reg query HKLM /v Name | findstr Name")
    assert "参考(低)" in body
    assert "说明: reg query 无 Linux 对应物" in body


def test_single_segment_and_unknown_command_have_no_suggestion():
    assert suggest_pipeline("dir | findstr x".split(" | ")[0]) is None
    assert suggest_pipeline("echo hi | findstr x") is None
    assert suggest_pipeline("") is None


def test_generated_todo_contains_suggestion(convert_bat):
    out, report = convert_bat("@echo off\ndir | findstr x && echo ok\n")
    assert "# TODO: 复杂管道需手动重写" in out
    assert "#  原命令: dir | findstr x && echo ok" in out
    assert "#  参考(中):" in out
    assert "#  差异:" in out
    assert report.todo_count == 1


def test_redirect_and_multistage_pipelines_get_suggestions(convert_bat):
    out, _ = convert_bat("@echo off\ndir 2>nul | findstr x\n")
    assert "#  参考(中): ls 2>/dev/null | grep x" in out

    out, _ = convert_bat("@echo off\ndir | findstr a | findstr b\n")
    assert "#  参考(中): ls | grep a | grep b" in out


def test_for_f_pipeline_keeps_plain_todo(convert_bat):
    text = "@echo off\nfor /f \"delims=\" %%i in ('dir ^| findstr x') do echo %%i\n"
    out, report = convert_bat(text)
    assert "参考(" not in out
    assert "# TODO: 手动检查: for /f" in out
    assert report.todo_count == 1


def test_unknown_segment_keeps_plain_todo(convert_bat):
    out, report = convert_bat("@echo off\nfoo.exe | findstr x && echo ok\n")
    assert "参考(" not in out
    assert "# TODO: 手动检查:" in out
    assert report.todo_count >= 1


def test_suggestion_lines_are_comments_and_syntax_valid(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\ndir | findstr x && echo ok\n")
    markers = ("原命令:", "参考(", "差异:", "说明:")
    for line in out.splitlines():
        if any(marker in line for marker in markers):
            assert line.lstrip().startswith("#"), f"建议行必须是注释: {line!r}"
    bash_check(out)


def test_run_still_refuses_script_with_suggestions(tmp_path):
    path = tmp_path / "pipeline.bat"
    path.write_text("@echo off\ndir | findstr x && echo ok\n", encoding="utf-8")
    assert main([str(path), "--run", "--yes"]) == 4
