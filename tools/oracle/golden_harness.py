"""wine cmd 黄金行为对照 harness（B3，v1.9.2）。

用途：把「bat → bash 转换的运行时语义」从人工判断变为可回归 —— 用 wine 的 cmd.exe
执行源 .bat，与 bat2sh 产物经 bash 执行的结果逐例比对（规范化后）。

**oracle 权威顺序（R5）**：真机 cmd / 官方文档 > wine。wine 是重实现，仅作初筛。
已知 wine 不可信的两处（本 harness 不以 wine 断言，见 UNRELIABLE_PROBES）：
  - X5：`echo 1.0.1>out.txt` —— wine 不吞位，真实 cmd 把紧邻 `>` 的数字当文件句柄；
  - A8：findstr 多词位置参数 —— wine 的 findstr 自相矛盾（`a b file` 有输出、
        `alpha gamma file` 无输出），无法判定切分语义。

用法::

    python3 tools/oracle/golden_harness.py     # 无 wine 时跳过（exit 0）

无 wine / 无 bash 时本 harness 跳过（不 fail），与 CI 语料策略一致。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CASES_DIR = Path(__file__).resolve().parent / "cases"
_REPO = Path(__file__).resolve().parents[2]
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_CASE_NAMES = ("g01", "g02", "g03", "g04", "g05", "g06")
# v2.5.0：goto 形态用例 —— 以 **CFG 状态机**（cfg_state_machine=True）产物对照 wine。
_STATE_MACHINE_CASES = ("g07", "g08", "g09", "g10", "g11", "g12")

UNRELIABLE_PROBES: dict[str, str] = {
    "x5_fd_digit": "echo 1.0.1>out.txt（wine 不吞位；真实 cmd 中紧邻 > 的数字是文件句柄）",
    "a8_findstr_multiword": "findstr a b file.txt（wine findstr 自相矛盾，不可判定切分）",
}


def wine_available() -> bool:
    if shutil.which("wine") is None:
        return False
    prefix = Path(__import__("os").environ.get("HOME", "")) / ".wine"
    return (prefix / "drive_c" / "windows" / "system32" / "cmd.exe").is_file()


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ANSI_RE.sub("", text)
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _load_converter():
    if str(_REPO / "python") not in sys.path:
        sys.path.insert(0, str(_REPO / "python"))
    from bat2sh.core.engine import convert_text  # noqa: PLC0415
    from bat2sh.core.settings import ConvertSettings  # noqa: PLC0415
    from bat2sh.core.types import SourceKind  # noqa: PLC0415

    return convert_text, ConvertSettings, SourceKind


def to_bash(bat_text: str, *, state_machine: bool = False) -> str:
    convert_text, ConvertSettings, SourceKind = _load_converter()
    script, _report = convert_text(
        bat_text,
        SourceKind.BATCH,
        ConvertSettings(bash_check=False, cfg_state_machine=state_machine),
        "golden.bat",
    )
    return script


def _run(cmd: list[str], cwd: Path, stdin: str = "") -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        env={**__import__("os").environ, "WINEDEBUG": "-all"},
    )
    return proc.stdout


def run_wine(bat_text: str, workdir: Path) -> str:
    (workdir / "case.bat").write_bytes(bat_text.replace("\n", "\r\n").encode("utf-8"))
    return _run(["wine", "cmd", "/c", "case.bat"], workdir)


def run_bash(script: str, workdir: Path) -> str:
    (workdir / "case.sh").write_text(script, encoding="utf-8")
    return _run([shutil.which("bash") or "bash", "case.sh"], workdir)


def compare_case(name: str) -> dict:
    bat = (CASES_DIR / f"{name}.bat").read_text(encoding="utf-8")
    state_machine = name in _STATE_MACHINE_CASES
    script = to_bash(bat, state_machine=state_machine)
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        wine_out = normalize(run_wine(bat, workdir))
        bash_out = normalize(run_bash(script, workdir))
    return {
        "name": name,
        "wine": wine_out,
        "bash": bash_out,
        "match": wine_out == bash_out,
        "state_machine": state_machine,
    }


def run_all() -> list[dict]:
    return [compare_case(name) for name in _CASE_NAMES + _STATE_MACHINE_CASES]


def main() -> int:
    if not wine_available():
        print("SKIP: 未找到 wine —— 黄金对照 harness 跳过（不 fail）")
        return 0
    results = run_all()
    width = max(len(r["wine"]) for r in results) + 2
    print(f"{'case':6} {'mode':14} {'wine':{width}} {'bat2sh->bash':{width}} verdict")
    for r in results:
        verdict = "MATCH" if r["match"] else "**DIFF**"
        mode = "state-machine" if r["state_machine"] else "default"
        print(f"{r['name']:6} {mode:14} {r['wine']!r:{width}} {r['bash']!r:{width}} {verdict}")
    print()
    print("x5/A8 caveat:", "; ".join(UNRELIABLE_PROBES.values()))
    matched = sum(1 for r in results if r["match"])
    print(f"\n黄金对照: {matched}/{len(results)} MATCH")
    return 0 if matched == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
