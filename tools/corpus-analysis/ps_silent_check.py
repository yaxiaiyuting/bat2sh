#!/usr/bin/env python3
"""PS 语料静默错误复检（v1.8.0，只读）。

静默错误定义（docs/v1.8.0-design.md §1.2）：
  转换产物通过 `bash -n`、沙箱运行 rc==0（“看起来成功”），
  但可见行为（rc 或归一化 stdout）与原始 pwsh 不一致。

用法::

    python3 tools/corpus-analysis/ps_silent_check.py [--pwsh DIR] [--out FILE]

`--pwsh` 指向便携 pwsh 目录（含 `pwsh` 可执行文件）。缺省时只做「bash 侧」统计，
不判定静默错误。只读：不写仓库，产物写入 `--out`（默认 /tmp）。

依赖：bwrap、bash、python3。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "tests" / "fixtures" / "real-corpus" / "fleschutz"
TIMEOUT = "12"


def sandbox_bash(workdir: Path) -> list[str]:
    return [
        "timeout", "-k", "3", TIMEOUT,
        "bwrap", "--unshare-all", "--die-with-parent",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--bind", str(workdir), str(workdir), "--chdir", str(workdir),
        "env", f"HOME={workdir}", "PATH=/usr/bin:/usr/sbin", "LANG=C.UTF-8",
        "bash", "-c", "ulimit -c 0; exec bash script.sh",
    ]


def sandbox_pwsh(workdir: Path, pwsh_dir: str) -> list[str]:
    return [
        "timeout", "-k", "3", TIMEOUT,
        "bwrap", "--unshare-all", "--die-with-parent",
        "--ro-bind", "/usr", "/usr", "--ro-bind", "/etc", "/etc",
        "--ro-bind", pwsh_dir, "/opt/pwsh",
        "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--bind", str(workdir), str(workdir), "--chdir", str(workdir),
        "env", "-i", f"HOME={workdir}", "PATH=/opt/pwsh:/usr/bin:/usr/sbin",
        "LANG=C.UTF-8", "LC_ALL=C.UTF-8", "TERM=dumb",
        "POWERSHELL_TELEMETRY_OPTOUT=1", "DOTNET_CLI_TELEMETRY_OPTOUT=1",
        "POWERSHELL_UPDATECHECK=Off", "DOTNET_NOLOGO=1",
        "/opt/pwsh/pwsh", "-NoLogo", "-NoProfile", "-NonInteractive",
        "-ExecutionPolicy", "Bypass", "-File", str(workdir / "script.ps1"),
    ]


def run(cmd: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=40)
    except subprocess.TimeoutExpired:
        return 124, "", "HOST-TIMEOUT"
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", "replace"),
        proc.stderr.decode("utf-8", "replace"),
    )


def normalize(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines()]
    return "\n".join(line for line in lines if line)


def one(path: Path, out_dir: Path, pwsh_dir: str | None) -> dict:
    sys.path.insert(0, str(REPO / "python"))
    from bat2sh.core.encoding import decode_bytes
    from bat2sh.core.engine import convert_text
    from bat2sh.core.settings import ConvertSettings
    from bat2sh.core.types import SourceKind

    workdir = out_dir / path.stem
    workdir.mkdir(parents=True, exist_ok=True)
    decoded = decode_bytes(path.read_bytes(), None)
    raw, report = convert_text(
        decoded.text, SourceKind.POWERSHELL, ConvertSettings(bash_check=False), path.name
    )
    (workdir / "script.sh").write_text(raw, encoding="utf-8")
    (workdir / "script.ps1").write_text(decoded.text, encoding="utf-8")
    syntax_ok = subprocess.run(
        ["bash", "-n"], input=raw, capture_output=True, text=True
    ).returncode == 0

    bash_rc, bash_out, bash_err = run(sandbox_bash(workdir))
    row: dict = {
        "name": path.name,
        "syntax_ok": syntax_ok,
        "bash_rc": bash_rc,
        "bash_out": normalize(bash_out)[:200],
        "bash_err": normalize(bash_err)[:160],
        "todos": report.todo_count,
        "silent": False,
        "reason": "",
    }
    if pwsh_dir and syntax_ok:
        ps_rc, ps_out, ps_err = run(sandbox_pwsh(workdir, pwsh_dir))
        row["ps_rc"] = ps_rc
        if bash_rc == 0 and (ps_rc != bash_rc or normalize(bash_out) != normalize(ps_out)):
            row["silent"] = True
            row["reason"] = f"bash rc=0 但与 pwsh 不一致（pwsh rc={ps_rc}）"
        row["ps_out"] = normalize(ps_out)[:200]
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pwsh", default="", help="便携 pwsh 目录（含 pwsh 可执行文件）")
    parser.add_argument("--out", default="/tmp/bat2sh-ps-silent", help="输出目录")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(CORPUS.glob("*.ps1"))
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda p: one(p, out_dir, args.pwsh or None), files))

    (out_dir / "results.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total = len(rows)
    syntax_pass = sum(r["syntax_ok"] for r in rows)
    ran_ok = sum(1 for r in rows if r["syntax_ok"] and r["bash_rc"] == 0)
    print(f"total={total} syntax_pass={syntax_pass} ({syntax_pass/total:.1%})")
    print(f"bash 运行 rc==0（syntax_ok）: {ran_ok}")
    if args.pwsh:
        silent = [r for r in rows if r["silent"]]
        print(f"静默错误: {len(silent)}/{ran_ok} = {len(silent)/ran_ok:.1%}" if ran_ok else "")
        for r in silent:
            print(f"  {r['name']}: {r['reason']}")
    print(f"结果: {out_dir / 'results.json'}")


if __name__ == "__main__":
    main()
