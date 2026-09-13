"""pytest 共享 fixtures。

确保测试导入的是仓库 ``python/`` 目录下的 bat2sh（而不是系统已安装的版本），
并提供文本转换与 ``bash -n`` 语法校验辅助。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_PYTHON = REPO_ROOT / "python"
if str(REPO_PYTHON) not in sys.path:
    sys.path.insert(0, str(REPO_PYTHON))

EXAMPLES_DIR = REPO_ROOT / "examples"

from bat2sh.core.engine import convert_text  # noqa: E402
from bat2sh.core.settings import ConvertSettings  # noqa: E402
from bat2sh.core.types import ConvertReport, SourceKind  # noqa: E402


@pytest.fixture
def convert_bat():
    """把批处理文本转换为 (bash 文本, 报告)。"""

    def _convert(
        text: str, source_name: str = "test.bat", **options
    ) -> tuple[str, ConvertReport]:
        settings = ConvertSettings(**options)
        return convert_text(text, SourceKind.BATCH, settings, source_name)

    return _convert


@pytest.fixture
def convert_ps():
    """把 PowerShell 文本转换为 (bash 文本, 报告)。"""

    def _convert(
        text: str, source_name: str = "test.ps1", **options
    ) -> tuple[str, ConvertReport]:
        settings = ConvertSettings(**options)
        return convert_text(text, SourceKind.POWERSHELL, settings, source_name)

    return _convert


@pytest.fixture(scope="session")
def bash_check():
    """用 ``bash -n`` 校验脚本文本，语法错误时给出上下文。"""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash，跳过语法校验")

    def _check(text: str) -> None:
        proc = subprocess.run(
            [bash, "-n"], input=text, capture_output=True, text=True
        )
        assert proc.returncode == 0, (
            f"bash -n 校验失败（退出码 {proc.returncode}）:\n"
            f"{proc.stderr}\n--- 脚本内容 ---\n{text}"
        )

    return _check


@pytest.fixture(scope="session")
def bash_run():
    """在 bash 中执行脚本文本，返回 CompletedProcess。"""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("未找到 bash，跳过脚本执行")

    def _run(text: str) -> subprocess.CompletedProcess:
        return subprocess.run([bash], input=text, capture_output=True, text=True)

    return _run
