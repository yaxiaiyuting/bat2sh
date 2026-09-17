"""v2.0.0 解析层/词法层硬化回归测试（P1/P2/P3a）。

每个用例断言**语义**（产物是否合法 bash、结构是否正确），不编码转换器内部实现。
根因与语料证据见 `docs/v2.0.0-review.md`。
"""

from __future__ import annotations

P1_REPRO = (
    "@echo off\n"
    "for /f \"delims=\" %%i in ('dir /s/b/a/ad') do (\n"
    "    dir /ta/a \"%%i\"\\*.exe 2>nul|findstr /r \"^%today%\" && (\n"
    "        echo a >>list.htm\n"
    "        echo b >>list.htm))\n"
    "start list.htm\n"
)

P3_REPRO = (
    "@echo off\n"
    "echo  # Checking DHCP ...\n"
    "ipconfig | find /i \"Lease\" > nul\n"
    "if errorlevel 1 (\n"
    "  rem trying other method for DHCP\n"
    "  ipconfig | find /i \"DHCP-Server\" > nul\n"
    "  if errorlevel 1 (\n"
    "    echo no dhcp\n"
    "  )\n"
    ")\n"
)


def test_p1_degraded_pipeline_open_paren_stays_balanced(convert_bat, bash_check):
    out, _ = convert_bat(P1_REPRO)
    bash_check(out)
    assert "多余的 ')'" not in out


def test_p1_degraded_pipeline_body_commented_and_tail_dispatched(convert_bat):
    out, _ = convert_bat(P1_REPRO)
    lines = out.splitlines()
    assert any(line.strip() == "# echo a >>list.htm" for line in lines)
    assert any(line.strip() == "# echo b >>list.htm" for line in lines)
    assert any("nohup list.htm" in line and not line.strip().startswith("#") for line in lines)


def test_p2_quote_strip_substitution_in_if_exist(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\nset "p=C:\\a"\nif exist "%p:"=%" (echo yes)\n')
    bash_check(out)
    assert '${p//\\"/}' in out
    assert 'echo "yes"' in out


def test_p2_plain_quoted_if_exist_unchanged(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\nif exist "C:\\a" (echo yes)\n')
    bash_check(out)
    assert '[ -e "C:/a" ]' in out


def test_p2_wildcard_if_exist_still_uses_compgen(convert_bat):
    out, _ = convert_bat("@echo off\nif exist *.txt (echo has)\n")
    assert 'compgen -G "*.txt"' in out


def test_p3a_structural_previous_line_not_bound_as_errorlevel(convert_bat, bash_check):
    out, _ = convert_bat(P3_REPRO)
    bash_check(out)
    assert "if ! if !" not in out


def test_p3a_simple_errorlevel_still_binds_previous_command(convert_bat, bash_check):
    out, _ = convert_bat('@echo off\ndir /b > nul\nif errorlevel 1 echo failed\n')
    bash_check(out)
    assert "if ! ls -1 >/dev/null; then" in out
