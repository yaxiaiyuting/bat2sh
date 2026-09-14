"""生成脚本的 ``bash -n`` 后置校验与降级（批处理 / PowerShell 两条路径共用）。

转换器产出完整脚本后调用 :func:`bash_syntax_error` 做语法校验；失败时通过
:func:`record_syntax_error` 记入报告的 errors 层（category="syntax"），并用
:func:`degraded_script` 把原始脚本整体降级为注释，确保 never emit broken bash。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from tempfile import NamedTemporaryFile

from .types import ConvertReport, Diagnostic

DEGRADE_MESSAGE = "生成脚本未通过 bash -n 语法检查，已降级为注释（可用 --no-bash-check 关闭校验）"


def bash_syntax_error(script: str) -> str | None:
    """对生成脚本跑 ``bash -n``：通过或环境无 bash 时返回 None，失败返回首行错误。

    错误信息中的临时文件路径替换为 ``<生成脚本>``，避免噪声。
    """
    bash = shutil.which("bash")
    if bash is None:
        return None
    try:
        with NamedTemporaryFile(
            "w", suffix=".sh", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(script)
            tmp_name = handle.name
    except OSError:
        return None
    try:
        completed = subprocess.run(
            [bash, "-n", tmp_name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
    if completed.returncode == 0:
        return None
    first = (completed.stderr or "").strip().splitlines()
    message = first[0] if first else "bash -n 检查失败"
    return message.replace(tmp_name, "<生成脚本>")


def record_syntax_error(report: ConvertReport, error: str) -> None:
    """把 ``bash -n`` 失败记入报告的 errors 层（与阶段 4 的语法错误归类一致）。"""
    report.errors.append(Diagnostic(0, DEGRADE_MESSAGE, error, category="syntax"))


def degraded_script(original_text: str, source_name: str, error: str) -> str:
    """把原始脚本整体降级为注释（供人工转换），保证产物仍可通过 ``bash -n``。"""
    body = [
        f"# {line}" if line.strip() else "#" for line in original_text.split("\n")
    ]
    header = [
        "#!/usr/bin/env bash",
        f"# 由 bat2sh 自动转换生成，源文件: {source_name}",
        "# TODO: 生成脚本未通过 bash -n 语法检查，已降级为注释",
        f"# 语法错误: {error}",
        "# 原脚本内容（保留为注释，供人工转换）:",
        "",
    ]
    return "\n".join(header + body).rstrip() + "\n"
