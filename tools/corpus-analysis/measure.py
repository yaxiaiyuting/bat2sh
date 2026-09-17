#!/usr/bin/env python3
"""bat2sh 语料测量仪器（可复现；v1.11.0 固化）。

口径（与 ``tools/corpus-analysis/analyze.py`` 的 bwrap / fixture / stdin 一致）：

- 语料：``--corpus`` 递归 ``*.bat`` / ``*.cmd``（默认仓库外的真实语料目录）。
- 原始转换口径：``ConvertSettings(bash_check=False)``（v1.8.0 起为发布口径）。
- 语法通过：``bash_syntax_error(text) is None``；分母 = 语法通过数。
- ``rc==0``：``bwrap --unshare-all`` 沙箱运行退出码 0。
- **功能完好（严格）**：``rc==0`` **且** 无 TODO（``report.todo_count == 0`` 且产物无 ``# TODO`` 标记）。
- ``degraded``：``rc==0`` 且含 TODO。

用法::

    python3 tools/corpus-analysis/measure.py --corpus ~/下载/非常批处理 --out /tmp/v111
    python3 tools/corpus-analysis/measure.py --corpus DIR --out DIR --json

设计约束（纪律 9 强化：测量工具必须可复现）：

- 只读源文件；一切输出写 ``--out``。
- 不依赖网络；``bwrap`` 不可用时逐项失败而非静默跳过。
- 输出 ``measure.json``：summary + 逐文件 ``rc`` / ``todo_count`` / ``markers`` / ``todos``。
  两次独立运行应**逐字段一致**（确定性）。
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

RUN_TIMEOUT = 30
OUTER_TIMEOUT = 45
MAX_FIXTURES = 12
SUFFIXES = (".bat", ".cmd")

FILE_SUFFIX_RE = r"(?:txt|log|dat|csv|ini|conf|cfg|list|md|json|xml|htm|html|png|jpg|bmp|tsv|bat|sh)"
READER_RE = r"(?:cat|type|more|head|tail|sort|uniq|wc|grep|sed|awk|tr|od|xxd|read|diff|cmp)"


def repo_root_from_file() -> Path:
    return Path(__file__).resolve().parents[2]


def load_core(repo: Path):
    sys.path.insert(0, str(repo / "python"))
    from bat2sh.core.engine import convert_file  # noqa: PLC0415
    from bat2sh.core.settings import ConvertSettings  # noqa: PLC0415
    from bat2sh.core.syntax import bash_syntax_error  # noqa: PLC0415

    return convert_file, ConvertSettings, bash_syntax_error


def iter_corpus(corpus: Path):
    for path in sorted(corpus.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUFFIXES:
            yield path


def fixture_names(script: str) -> list[str]:
    """复用 analyze.py 的 fixture 生成口径。"""
    names: set[str] = set()
    pattern = re.compile(
        rf'{READER_RE}\b[^\n]{{0,120}}?"?([A-Za-z0-9_][\w@.-]*\.{FILE_SUFFIX_RE})"?'
    )
    for match in pattern.finditer(script):
        names.add(match.group(1))
    assigns: dict[str, str] = {}
    for line in script.splitlines():
        match = re.match(r"^\s*(\w+)=(.*)$", line)
        if match:
            value = match.group(2).strip().strip("\"'")
            if re.fullmatch(r"[A-Za-z0-9_@.-]+", value):
                assigns[match.group(1)] = value
    var_pattern = re.compile(rf'{READER_RE}\b[^\n]{{0,120}}"\$\{{?(\w+)\}}?"')
    for match in var_pattern.finditer(script):
        value = assigns.get(match.group(1), "")
        if value and "." in value:
            names.add(value)
    result = []
    for name in sorted(names):
        if "/" in name or "\\" in name or ":" in name or len(name) >= 64:
            continue
        result.append(name)
    return result[:MAX_FIXTURES]


def stdin_mode(script: str) -> str:
    """复用 analyze.py 的 stdin 口径：独立 read 时喂空行。"""
    if re.search(r"\bread\b", script) and not re.search(r"\b(?:while|until)\b", script):
        return "yes"
    return "null"


def sandbox_cmd(workdir: Path) -> list[str]:
    return [
        "bwrap", "--unshare-all", "--die-with-parent",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--bind", str(workdir), str(workdir), "--chdir", str(workdir),
        "env", f"HOME={workdir}", "PATH=/usr/bin:/usr/sbin", "LANG=C.UTF-8", "LC_ALL=C.UTF-8",
        "timeout", "-k", "5", str(RUN_TIMEOUT),
        "bash", "-c", "ulimit -c 0; ulimit -f 10240; exec bash script.sh",
    ]


def count_markers(text: str) -> int:
    """产物中真实 ``# TODO`` 标记数（排除脚本头的口径说明行）。"""
    n = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# 带有 # TODO 标记") or stripped.startswith("# 该脚本包含"):
            continue
        if "# TODO" in line:
            n += 1
    return n


def run_one(path: Path, corpus: Path, index: int, out_dir: Path, core) -> dict:
    convert_file, ConvertSettings, bash_syntax_error = core
    entry: dict = {"name": path.name, "rel": str(path.relative_to(corpus)), "index": index}
    try:
        result = convert_file(path, ConvertSettings(bash_check=False), write=False)
    except Exception as exc:  # noqa: BLE001
        entry["convert_error"] = f"{type(exc).__name__}: {exc}"
        return entry
    if result.error:
        entry["convert_error"] = result.error
        return entry
    report = result.report
    text = result.text
    entry["todo_count"] = report.todo_count
    entry["markers"] = count_markers(text)
    entry["syntax_ok"] = bash_syntax_error(text) is None
    entry["todos"] = [
        {"line": d.line, "category": d.category, "message": d.message, "original": d.original}
        for d in report.todos
    ]
    if not entry["syntax_ok"]:
        entry["rc"] = None
        return entry
    workdir = out_dir / "runs" / f"{index:03d}"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "script.sh").write_text(text, encoding="utf-8")
    for name in fixture_names(text):
        target = workdir / name
        if not target.exists():
            try:
                target.write_text("line one\nline two\nline three\n", encoding="utf-8")
            except OSError:
                pass
    cmd = sandbox_cmd(workdir)
    if stdin_mode(text) == "yes":
        cmd = ["bash", "-c", 'yes "" | ' + shlex.join(cmd)]
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=OUTER_TIMEOUT)
        entry["rc"] = proc.returncode
        entry["stderr"] = proc.stderr.decode("utf-8", "replace")[:2000]
    except subprocess.TimeoutExpired:
        entry["rc"] = None
        entry["timeout"] = True
    entry["duration_s"] = round(time.monotonic() - started, 2)
    return entry


def summarize(entries: list[dict]) -> dict:
    syntax_ok = [e for e in entries if e.get("syntax_ok")]
    rc0 = [e for e in syntax_ok if e.get("rc") == 0]
    strict = [e for e in rc0 if e.get("todo_count") == 0 and e.get("markers") == 0]
    degraded = [e for e in rc0 if not (e.get("todo_count") == 0 and e.get("markers") == 0)]
    crash = [
        e for e in entries
        if e.get("rc") is not None and e["rc"] >= 128 and (e["rc"] - 128) in (4, 6, 7, 8, 11)
    ]
    return {
        "corpus": len(entries),
        "syntax_ok": len(syntax_ok),
        "rc0": len(rc0),
        "strict": len(strict),
        "degraded": len(degraded),
        "degraded_todos": sum(e.get("todo_count", 0) for e in degraded),
        "crash": len(crash),
        "timeout": sum(1 for e in entries if e.get("timeout")),
        "convert_error": sum(1 for e in entries if e.get("convert_error")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True, help="语料根目录（递归 *.bat/*.cmd）")
    parser.add_argument("--out", required=True, help="输出目录（runs/ 与 measure.json）")
    parser.add_argument("--repo", default="", help="bat2sh 仓库根（默认：本脚本上两级）")
    parser.add_argument("--json", action="store_true", help="仅打印 summary JSON")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve() if args.repo else repo_root_from_file()
    corpus = Path(args.corpus).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    if not corpus.is_dir():
        parser.error(f"语料目录不存在: {corpus}")
    out_dir.mkdir(parents=True, exist_ok=True)
    core = load_core(repo)

    entries = []
    for index, path in enumerate(iter_corpus(corpus), 1):
        entry = run_one(path, corpus, index, out_dir, core)
        entries.append(entry)
        if not args.json:
            status = entry.get("convert_error") or (
                "SYNTAX_FAIL" if not entry.get("syntax_ok") else f"rc={entry.get('rc')}"
            )
            print(f"[{index:03d}] {status:14s} todo={entry.get('todo_count', '-')} {entry['rel']}", flush=True)
    summary = summarize(entries)
    (out_dir / "measure.json").write_text(
        json.dumps({"summary": summary, "entries": entries}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
