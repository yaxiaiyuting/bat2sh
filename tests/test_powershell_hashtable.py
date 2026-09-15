"""哈希表字面量的回归测试（v1.6.0 阶段 A / Fix 105）。"""

from __future__ import annotations


def _uncommented(out: str) -> list[str]:
    return [
        line for line in out.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_flat_hashtable_to_associative_array(convert_ps, bash_check):
    out, report = convert_ps('$cfg = @{\n    "a" = "1"\n    b = 2\n    c = $true\n}\n')
    assert report.error_count == 0
    assert out.count("declare -A cfg=(") == 1
    assert '["a"]="1"' in out
    assert '["b"]=2' in out
    assert '["c"]=true' in out
    assert "多余的 }" not in out
    bash_check(out)


def test_inline_flat_hashtable(convert_ps, bash_check):
    out, _ = convert_ps('$cfg = @{ a = 1; b = "x" }\n')
    assert "declare -A cfg=(" in out
    assert '["a"]=1' in out
    assert '["b"]="x"' in out
    bash_check(out)


def test_ordered_flat_hashtable(convert_ps, bash_check):
    out, _ = convert_ps('$cfg = [ordered]@{ a = 1; b = 2 }\n')
    assert "declare -A cfg=(" in out
    bash_check(out)


def test_nested_hashtable_comment_degraded(convert_ps, bash_check):
    out, report = convert_ps(
        '$serverConfig = [ordered]@{\n'
        '    "web01" = @{ IP = "10.0.1.10"; Role = "Web" }\n'
        "}\n"
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    assert not [line for line in _uncommented(out) if "@{" in line]
    assert "# TODO: 手动检查: $serverConfig = [ordered]@{" in out
    assert '# "web01" = @{ IP = "10.0.1.10"; Role = "Web" }' in out
    bash_check(out)


def test_pscustomobject_hashtable_not_raw(convert_ps, bash_check):
    out, report = convert_ps(
        "$report = [PSCustomObject]@{\n"
        '    Name = "x"\n'
        "    Detail = @{ a = 1 }\n"
        "}\n"
    )
    assert report.error_count == 0
    assert "多余的 }" not in out
    assert not [line for line in _uncommented(out) if "@{" in line]
    bash_check(out)


def test_empty_hashtable(convert_ps, bash_check):
    out, report = convert_ps("$h = @{}\n")
    assert report.error_count == 0
    assert "declare -A h=(" in out
    bash_check(out)


def test_unterminated_hashtable_commented(convert_ps, bash_check):
    out, report = convert_ps("$h = @{\n    a = 1\n")
    assert report.error_count == 0
    assert "多余的 }" not in out
    assert any("未找到结束花括号" in d.message for d in report.warnings)
    assert "# TODO: 手动检查: $h = @{" in out
    bash_check(out)
