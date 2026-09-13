"""examples/ 的端到端冒烟测试。

只断言：转换成功、关键特征存在、``bash -n`` 通过、警告/TODO 数量符合当前预期。
不要求生成结果与已提交的 examples/*.sh 字节一致（它们仅单独做语法校验）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bat2sh.core.engine import convert_file
from bat2sh.core.settings import ConvertSettings
from bat2sh.core.types import SourceKind

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"

CASES: dict[str, dict] = {
    "hello.bat": {
        "kind": SourceKind.BATCH,
        "warnings": 0,
        "todos": 0,
        "features": [
            'NAME="World"',
            'GREETING="Hello"',
            'echo "${GREETING}, ${NAME}!"',
            'echo "当前目录: $(pwd)"',
            'if [ -e "config.ini" ]; then',
            "else",
            'read -rp "Press Enter to continue..." || true',
            "exit 0",
        ],
    },
    "deploy.bat": {
        "kind": SourceKind.BATCH,
        "warnings": 1,
        "todos": 0,
        "features": [
            "shopt -s nullglob",
            "label_copy_files() {",
            'for f in "${SRC}"/*.exe "${SRC}"/*.dll; do',
            "if ! label_copy_files; then",
            "exit 1",
            'ls -1 "${DST}"',
            "exit 0",
        ],
    },
    "backup.ps1": {
        "kind": SourceKind.POWERSHELL,
        "warnings": 6,
        "todos": 0,
        "features": [
            "__bat2sh_join_path() {",
            'Source="${1:-C:/Data}"',
            'Destination="${2:-D:/Backup}"',
            'files=("${Source}"/*.txt)',
            'count=$(( ${count:-0} + 1 ))',
            'target=$(__bat2sh_join_path "${Destination}" "${file}")',
            "exit 0",
        ],
    },
    "cleanup.ps1": {
        "kind": SourceKind.POWERSHELL,
        "warnings": 4,
        "todos": 0,
        "features": [
            "Remove_OldLogs() {",
            'local Path="${1:-/tmp/logs}"',
            'local Keep="${2:-5}"',
            'rm -f "${log}"',
            "clear",
        ],
    },
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_example_conversion(name: str, bash_check):
    case = CASES[name]
    result = convert_file(EXAMPLES_DIR / name, ConvertSettings(), write=False)
    assert result.error == ""
    assert result.kind is case["kind"]
    assert result.report.warning_count == case["warnings"]
    assert result.report.todo_count == case["todos"]
    for feature in case["features"]:
        assert feature in result.text, f"{name} 缺少特征: {feature}"
    bash_check(result.text)


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES_DIR.glob("*.sh")))
def test_committed_shell_scripts_are_valid(name: str, bash_check):
    bash_check((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def test_examples_sources_are_untouched_baseline():
    # 回归基线：源文件扩展名集合保持稳定
    names = sorted(p.name for p in EXAMPLES_DIR.iterdir() if p.is_file())
    assert names == [
        "backup.ps1",
        "backup.sh",
        "cleanup.ps1",
        "cleanup.sh",
        "deploy.bat",
        "deploy.sh",
        "hello.bat",
        "hello.sh",
        "stress_test.bat",
    ]
