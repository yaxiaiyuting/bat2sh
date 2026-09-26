"""v1.8.2 A-3：未知命令 / POSIX 透传路径反斜杠未转换修复回归。

语料依据（v1.8.2 artifact 分类 §2.A A2/A7）：
- ``宽带连接.bat:1`` ``c:\\windows\\system32\\rasdial …`` → 产物保留反斜杠
- ``注册表/设注册表某个键的键值为变量1.bat:2`` ``%temp%\\d~.vbs``
- ``史上最牛X批处理工具包…bat`` 大量 ``c:\\windows\\…``
"""

from __future__ import annotations


def test_unknown_command_path_backslashes_converted(convert_bat, bash_check):
    out, _ = convert_bat("@echo off\nc:\\windows\\system32\\mytool foo bar\n", bash_check=False)
    bash_check(out)
    assert "c:/windows/system32/mytool foo bar" in out
    assert "\\" not in out.split("源文件:")[1]


def test_mapped_path_prefix_command_resolves_to_todo(convert_bat):
    # v1.9.0 B-1：盘符全路径先取 basename 再查映射表（rasdial 为 C 档 → 建议 + TODO）
    out, report = convert_bat("@echo off\nc:\\windows\\system32\\rasdial foo bar\n")
    assert "# TODO: 手动检查:" in out
    assert not any(line.strip().startswith("c:/windows") for line in out.splitlines())
    assert report.todo_count >= 1


def test_start_inner_windows_only_command_becomes_todo(convert_bat):
    # v1.9.0 B-2：`start` 的目标若不是路径，应识别 Windows 专有命令并诚实 TODO
    out, report = convert_bat('@echo off\nSTART /WAIT REGEDIT /S "x.reg"\n')
    assert "# TODO: 手动检查: START /WAIT REGEDIT" in out
    assert report.todo_count >= 1


def test_start_inner_normal_command_unchanged(convert_bat):
    out, report = convert_bat("@echo off\nstart /wait notepad\n")
    assert "notepad" in out
    assert report.todo_count == 0


def test_unknown_command_relative_path_converted(convert_bat):
    out, _ = convert_bat("@echo off\nfoo\\bar baz\n")
    assert "foo/bar baz" in out


def test_posix_keep_path_backslashes_converted(convert_bat):
    out, _ = convert_bat("@echo off\ngit\\bin\\git status\n")
    assert "git/bin/git status" in out


def test_redirect_target_backslashes_converted(convert_bat):
    out, _ = convert_bat('@echo off\n>"%temp%\\d~.vbs" echo hi\n')
    assert '"${TMPDIR:-/tmp}/d~.vbs"' in out


# ----------------------------------------------------------------------
# F5（oracle 未报，诊断期发现；= F3-a 的全量面）：
# 反斜杠紧跟**变量展开插入的替换**时未转换为路径分隔符
#
# 机制：`convert_backslashes` 在 `_expand_vars` **之后**运行。源里 `\` 紧跟变量名，
# 展开后紧跟 `$`，于是被判为"转义序列"而保留 ⇒ 产物是**字面反斜杠文件名**。
# 151 语料实测 14 文件 / 48 处（如 `}"${destination}\${name_log}_log.log"`）。
# ----------------------------------------------------------------------
def test_substitution_detection_unit():
    """单元口径：只认 `${` / `$(` / A1 占位符，且排除连写与 `\\?\\` 前缀。"""
    from bat2sh.core.utils import convert_backslashes as cb

    # 命中：展开插入的替换
    assert cb("${D}\\${N}") == "${D}/${N}"
    assert cb('"${D}\\${N}"') == '"${D}/${N}"'
    assert cb("${D}\\$(basename x)") == "${D}/$(basename x)"
    assert cb('"a\\${b}\\${c}"') == '"a/${b}/${c}"'
    # 命中：A1 块内冻结占位符（合成期替换为 ${...}）
    assert cb("${D}\\\x00A1:1:n\x00") == "${D}/\x00A1:1:n\x00"
    # 不命中：反斜杠连写（UNC / 字面反斜杠）——交给原有规则整体保留
    assert cb("\\\\${N}") == "\\\\${N}"
    # 不命中：Windows 扩展长度 / 设备前缀 —— `\${N}` 必须原样保留。
    # （前缀里的 `\?` / `\.` 由**既有**规则转成 `/?` `/\.`，F5 不改那部分；
    #   F5 只保证**不**把紧邻的 `\${N}` 变成 `/${N}`，否则
    #   `_convert_path_token` 的通配符回退会把它变成活通配符。）
    assert cb("\\\\?\\${N}").endswith("\\${N}")
    assert cb("\\\\.\\${N}").endswith("\\${N}")
    # 不命中：单个 `$`（不是替换）
    assert cb("\\$5") == "\\$5"
    # 原有行为不变
    assert cb('"C:\\dir\\file.txt"') == '"C:/dir/file.txt"'


def test_var_to_var_path_actually_resolves(convert_bat, tmp_path):
    """运行语义：`%D%\\%N%` 必须落到子目录，而不是字面反斜杠文件名。"""
    import subprocess

    out, report = convert_bat(
        "@echo off\n"
        'set "D=%~dp0d"\n'
        'set "N=x"\n'
        'mkdir "%D%"\n'
        'echo hi>"%D%\\%N%.txt"\n',
        bash_check=False,
    )
    assert report.todo_count == 0
    (tmp_path / "run.sh").write_text(out, encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(tmp_path / "run.sh")], capture_output=True, text=True,
        cwd=tmp_path, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "d" / "x.txt").read_text(encoding="utf-8") == "hi\n"
    assert not any("\\" in p.name for p in tmp_path.rglob("*"))


def test_redirect_and_non_redirect_both_converted(convert_bat):
    """重定向目标与普通参数走**同一条**规则（旧窄修只覆盖重定向）。"""
    out, _ = convert_bat(
        '@echo off\nset "D=%~dp0d"\nset "N=x"\ncopy /y "%D%\\%N%" "%D%\\%N%.bak"\n',
        bash_check=False,
    )
    assert "\\" not in out.split('D="${SCRIPT_DIR}/d"', 1)[1]


def test_windows_extended_prefix_left_untouched(convert_bat):
    """`\\\\?\\%1` 属"不做映射"（同盘符/UNC），不得被改写成活通配符。

    若转换，`_convert_path_token` 的通配符回退会产出未加引号的
    `rm -rf \\/?/${1:-}`（`?` 成为活通配符，可能误删根下单字符目录）。
    """
    out, _ = convert_bat("@echo off\nDEL /F /A /Q \\\\?\\%1\n", bash_check=False)
    assert "\\${1:-}" in out
    assert "/${1:-}" not in out
