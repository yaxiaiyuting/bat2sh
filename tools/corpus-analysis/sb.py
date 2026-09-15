#!/usr/bin/env python3
"""单文件沙箱验证：convert_file → bwrap 运行 → 打印 rc/stderr。

用法::

    python3 sb.py <源文件路径> [tag] [--repo REPO] [--out DIR]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

FIXTURE_SUFFIXES = ("txt", "log", "dat", "csv", "ini", "conf", "list", "m3u", "htm")


def sandbox(workdir: Path) -> list[str]:
    return [
        "bwrap", "--unshare-all", "--die-with-parent",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--bind", str(workdir), str(workdir), "--chdir", str(workdir),
        "env", f"HOME={workdir}", "PATH=/usr/bin:/usr/sbin", "LANG=C.UTF-8",
        "timeout", "-k", "5", "20", "bash", "-c", "ulimit -c 0; exec bash script.sh",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="源文件路径（.bat/.cmd/.ps1）")
    parser.add_argument("tag", nargs="?", default="run", help="输出目录后缀（默认 run）")
    parser.add_argument("--repo", default="", help="bat2sh 仓库根目录（默认：本脚本上两级）")
    parser.add_argument("--out", default="", help="输出目录（默认：./sb-out）")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve() if args.repo else Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo / "python"))
    from bat2sh.core.engine import convert_file  # noqa: PLC0415
    from bat2sh.core.settings import ConvertSettings  # noqa: PLC0415

    source = Path(args.source).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve() if args.out else Path.cwd() / "sb-out"
    result = convert_file(source, ConvertSettings(), write=False)
    if result.error:
        print(f"CONVERT FAILED: {result.error}")
        return
    workdir = out_dir / f"{source.name}-{args.tag}"
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "script.sh").write_text(result.text, encoding="utf-8")
    for suffix in FIXTURE_SUFFIXES:
        for candidate in source.parent.glob(f"*.{suffix}"):
            if candidate.name.lower() != "readme":
                (workdir / candidate.name).write_text("line one\nline two\n", encoding="utf-8")
    proc = subprocess.run(
        sandbox(workdir), stdin=subprocess.DEVNULL, capture_output=True, timeout=45
    )
    err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
    print(f"rc={proc.returncode}")
    for line in err[:10]:
        print("  stderr:", line[:180])


if __name__ == "__main__":
    main()
