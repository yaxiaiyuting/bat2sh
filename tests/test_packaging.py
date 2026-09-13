"""打包资源校验：MIME 定义与 .desktop 桌面项。

只读校验；MIME 数据库编译仅在临时目录中进行，不触碰系统数据库。
"""

from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MIME_XML = REPO_ROOT / "data" / "mime" / "bat2sh.xml"
DESKTOP_FILE = REPO_ROOT / "bat2sh.desktop"

MIME_NS = {"mime": "http://www.freedesktop.org/standards/shared-mime-info"}


def _mime_types() -> dict[str, ET.Element]:
    root = ET.parse(MIME_XML).getroot()
    return {node.get("type"): node for node in root.findall("mime:mime-type", MIME_NS)}


def test_mime_xml_declares_bat2sh_types_with_globs_and_inheritance():
    types = _mime_types()
    assert set(types) == {
        "application/x-bat2sh-batch",
        "application/x-bat2sh-powershell",
    }

    batch = types["application/x-bat2sh-batch"]
    assert {glob.get("pattern") for glob in batch.findall("mime:glob", MIME_NS)} == {
        "*.bat",
        "*.cmd",
    }
    assert {
        parent.get("type") for parent in batch.findall("mime:sub-class-of", MIME_NS)
    } == {"application/x-bat"}

    powershell = types["application/x-bat2sh-powershell"]
    assert {
        glob.get("pattern") for glob in powershell.findall("mime:glob", MIME_NS)
    } == {"*.ps1"}
    assert {
        parent.get("type")
        for parent in powershell.findall("mime:sub-class-of", MIME_NS)
    } == {"application/x-powershell"}


def test_mime_xml_compiles_with_update_mime_database(tmp_path):
    tool = shutil.which("update-mime-database")
    if tool is None:
        pytest.skip("update-mime-database 不可用")
    packages = tmp_path / "mime" / "packages"
    packages.mkdir(parents=True)
    shutil.copy(MIME_XML, packages / "bat2sh.xml")
    proc = subprocess.run(
        [tool, str(tmp_path / "mime")], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


def test_desktop_declares_mime_types_and_file_exec():
    text = DESKTOP_FILE.read_text(encoding="utf-8")
    mime_line = next(line for line in text.splitlines() if line.startswith("MimeType="))
    wanted = {
        "application/x-bat2sh-batch",
        "application/x-bat2sh-powershell",
        "application/x-bat",
        "application/x-powershell",
    }
    assert wanted <= set(mime_line.removeprefix("MimeType=").split(";"))
    assert "Exec=bat2sh %F" in text


def test_desktop_file_passes_desktop_file_validate():
    tool = shutil.which("desktop-file-validate")
    if tool is None:
        pytest.skip("desktop-file-validate 不可用")
    proc = subprocess.run([tool, str(DESKTOP_FILE)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
