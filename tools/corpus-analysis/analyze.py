#!/usr/bin/env python3
"""bat2sh 语料批量分析：转换 + 静态分析 + bwrap 沙箱运行 + 结果关联。

用法::

    python3 analyze.py run --downloads ~/下载 --out /tmp/corpus-out [--repo REPO]
    python3 analyze.py anonymize --input /tmp/corpus-out/results.json \\
        --output tools/corpus-analysis/results-anonymized.json

设计（v1.4.1）：
- 只读源文件；全部输出写到 ``--out`` 目录（converted/ 与 runs/）。
- 沙箱：``bwrap --unshare-all``（无网络），仅挂载 /usr 与临时 workdir，
  不挂载真实 HOME/etc/var/root。
- 每个文件先按默认设置（strict_mode=True）跑一次；运行失败的文件关闭
  strict_mode 复跑，用于区分 "set -e 早退" 与 "真实转换缺陷"。
- ``anonymize`` 移除全部脚本原文/输出/绝对路径，仅保留文件名、分类、计数、
  错误类型与命令 token，供归档发布。
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

CORPUS_SUBDIRS = (
    ("bat-master", "bat-master"),
    ("windows-batch", "windows-batch-script-master"),
    ("common-powershell", "common_powershell_scripts-main"),
)
ROOT_EXTRA_NAME = "download-root"
SUFFIXES = (".bat", ".cmd", ".ps1")

RUN_TIMEOUT = 30
OUTER_TIMEOUT = 45
MAX_FIXTURES = 12

FILE_SUFFIX_RE = (
    r"(?:txt|log|dat|csv|ini|conf|cfg|list|md|json|xml|htm|html|png|jpg|bmp|tsv|bat|sh)"
)
READER_RE = r"(?:cat|type|more|head|tail|sort|uniq|wc|grep|sed|awk|tr|od|xxd|read|diff|cmp)"

UNSAFE_PATTERNS: list[tuple[str, str]] = [
    (r"\bmkfs\.?\w*\b", "mkfs"),
    (r"\bdd\b[^\n]*\bof=/dev/", "dd of=/dev"),
    (r"\b(?:fdisk|parted|sgdisk)\b", "disk-partition-tool"),
    (r"\b(?:shutdown|reboot|poweroff|halt)\b", "power-control"),
    (r"\b(?:sudo|pkexec|doas)\b", "privilege-escalation"),
    (r"\bmountvol\b|\bmount\b|\bumount\b", "mount"),
    (r"\bchmod\s+(?:-[a-zA-Z]+\s+)*777\s+/(?:\s|$)", "chmod-777-root"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;?\s*:", "fork-bomb"),
    (r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:bash|sh)\b", "remote-pipe-to-shell"),
]

RM_TARGETS = {"/", "/*", "~", "~/", "$HOME", "${HOME}", "$HOME/", "/home", "/root"}

SIMPLE_TOKEN_RE = re.compile(r"^[\w.@+-]{1,40}$")


def repo_root_from_file() -> Path:
    return Path(__file__).resolve().parents[2]


def load_core(repo: Path):
    sys.path.insert(0, str(repo / "python"))
    from bat2sh.core.engine import convert_file  # noqa: PLC0415
    from bat2sh.core.settings import ConvertSettings  # noqa: PLC0415
    from bat2sh.core.syntax import bash_syntax_error  # noqa: PLC0415

    return convert_file, ConvertSettings, bash_syntax_error


def iter_corpus(downloads: Path):
    for group, subdir in CORPUS_SUBDIRS:
        directory = downloads / subdir
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in SUFFIXES:
                yield group, path
    for path in sorted(downloads.iterdir()):
        if path.is_file() and path.suffix.lower() in SUFFIXES:
            yield ROOT_EXTRA_NAME, path


def unsafe_reasons(script: str) -> list[str]:
    reasons: list[str] = []
    for match in re.finditer(r"\brm\s+([^\n;|&]*)", script):
        args = match.group(1)
        if not re.search(r"-[a-zA-Z]*r", args):
            continue
        for token in args.split():
            target = token.strip("\"'`")
            if target in RM_TARGETS:
                reasons.append(f"rm -r {target}")
    for pattern, label in UNSAFE_PATTERNS:
        if re.search(pattern, script):
            reasons.append(label)
    return sorted(set(reasons))


def fixture_names(script: str) -> list[str]:
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
    if re.search(r"\bread\b", script) and not re.search(r"\b(?:while|until)\b", script):
        return "yes"
    return "null"


def sandbox_cmd(workdir: Path) -> list[str]:
    return [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/sbin", "/sbin",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--bind", str(workdir), str(workdir),
        "--chdir", str(workdir),
        "env", f"HOME={workdir}", "PATH=/usr/bin:/usr/sbin", "LANG=C.UTF-8", "LC_ALL=C.UTF-8",
        "timeout", "-k", "5", str(RUN_TIMEOUT),
        "bash", "-c", "ulimit -c 0; ulimit -f 10240; exec bash script.sh",
    ]


def classify(rc: int | None, stdout: str, stderr: str, timed_out: bool) -> tuple[str, list[str]]:
    flags: list[str] = []
    if timed_out:
        return "TIMEOUT", flags
    if rc in (124, 137, 143):
        return "TIMEOUT", flags
    if rc is not None and rc >= 128 and (rc - 128) in (4, 6, 7, 8, 11):
        return "CRASH", flags
    if "command not found" in stderr:
        flags.append("MISSING_CMD")
    if "No such file or directory" in stderr:
        flags.append("MISSING_FILE")
    if "Permission denied" in stderr:
        flags.append("PERMISSION")
    if rc == 0:
        return (flags[0] if flags else "OK"), flags
    if flags:
        return flags[0], flags
    return "RC_NONZERO", flags


def run_script(entry: dict, tag: str, out_dir: Path) -> dict:
    workdir = out_dir / "runs" / f"{entry['id']}-{tag}"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "script.sh").write_text(entry["bash"], encoding="utf-8")
    fixtures = fixture_names(entry["bash"])
    for name in fixtures:
        target = workdir / name
        if not target.exists():
            try:
                target.write_text("line one\nline two\nline three\n", encoding="utf-8")
            except OSError:
                pass
    mode = stdin_mode(entry["bash"])
    cmd = sandbox_cmd(workdir)
    if mode == "yes":
        cmd = ["bash", "-c", 'yes "" | ' + shlex.join(cmd)]
    logs_dir = out_dir / "runs" / "_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / f"{entry['id']}-{tag}.stdout.log"
    stderr_path = logs_dir / f"{entry['id']}-{tag}.stderr.log"
    started = time.monotonic()
    timed_out = False
    rc: int | None
    with open(stdout_path, "wb") as out_f, open(stderr_path, "wb") as err_f:
        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=out_f,
                stderr=err_f,
                timeout=OUTER_TIMEOUT,
            )
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc, timed_out = None, True
    duration = round(time.monotonic() - started, 2)
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")[:200_000]
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")[:200_000]
    category, flags = classify(rc, stdout, stderr, timed_out)
    return {
        "tag": tag,
        "category": category,
        "flags": flags,
        "rc": rc,
        "timed_out": timed_out,
        "duration_s": duration,
        "stdin": mode,
        "fixtures": fixtures,
        "workdir": str(workdir),
        "stdout_head": "\n".join(stdout.splitlines()[:50]),
        "stdout_bytes": stdout_path.stat().st_size,
        "stderr": stderr[:8000],
        "stderr_bytes": stderr_path.stat().st_size,
    }


def analysis_reason(run: dict) -> str:
    if run["timed_out"] or run["category"] == "TIMEOUT":
        return "timeout"
    if run["category"] == "CRASH":
        return f"crash rc={run['rc']}"
    stderr = run["stderr"]
    missing = re.findall(r"([^\s:]+): command not found", stderr)
    if missing:
        return "missing command: " + missing[0]
    nofile = re.findall(r"([^:\n]+): No such file or directory", stderr)
    if nofile:
        return "missing path: " + nofile[0].strip()
    line = next((ln.strip() for ln in stderr.splitlines() if ln.strip()), "")
    line = re.sub(r"script\.sh: line \d+: ", "", line)
    line = re.sub(r"\d+", "N", line)[:120]
    return f"rc={run['rc']} {line}".strip()


def analyze_file(group: str, path: Path, index: int, out_dir: Path, core, keep_text: bool) -> dict:
    convert_file, ConvertSettings, bash_syntax_error = core
    source = path.read_text(encoding="utf-8", errors="replace")
    entry: dict = {
        "id": f"{index:03d}-{group}-{path.name}",
        "group": group,
        "source_path": str(path),
        "source_lines": len(source.splitlines()),
        "bash": "",
        "conversion": {},
        "static": {},
        "run": None,
        "run_relaxed": None,
        "correlation": "",
    }
    result = convert_file(path, ConvertSettings(), write=False)
    if result.error:
        entry["conversion"] = {"status": "FAILED", "error": result.error}
        entry["correlation"] = "CONVERT_FAILED"
        return entry
    report = result.report
    degraded = any(d.category == "syntax" for d in report.errors)
    entry["bash"] = result.text
    entry["conversion"] = {
        "status": "DEGRADED" if degraded else "OK",
        "encoding": result.encoding,
        "converted_lines": report.converted_lines,
        "unchanged_lines": report.unchanged_lines,
        "todo_count": report.todo_count,
        "warning_count": report.warning_count,
        "error_count": report.error_count,
        "todos": [
            {"line": d.line, "category": d.category, "message": d.message, "original": d.original}
            for d in report.todos
        ],
        "warnings": [
            {"line": d.line, "category": d.category, "message": d.message}
            for d in report.warnings
        ],
        "errors": [
            {"line": d.line, "category": d.category, "message": d.message}
            for d in report.errors
        ],
    }
    if keep_text:
        out_group = out_dir / "converted" / group
        out_group.mkdir(parents=True, exist_ok=True)
        (out_group / f"{index:03d}-{path.name}.sh").write_text(result.text, encoding="utf-8")
    syntax_problem = bash_syntax_error(result.text)
    entry["static"] = {"syntax_ok": syntax_problem is None, "syntax_error": syntax_problem or ""}
    if degraded:
        entry["correlation"] = "DEGRADED"
        return entry
    reasons = unsafe_reasons(result.text)
    if reasons:
        entry["static"]["unsafe"] = reasons
        entry["correlation"] = "UNSAFE_SKIPPED"
        return entry
    run = run_script(entry, "strict", out_dir)
    entry["run"] = run
    if run["category"] == "OK":
        entry["correlation"] = "USABLE"
        return entry
    entry["correlation"] = "CONVERT_OK_RUN_FAILED"
    relaxed = convert_file(path, ConvertSettings(strict_mode=False), write=False)
    if relaxed.error:
        entry["run_relaxed"] = {"error": relaxed.error}
    else:
        entry["bash"] = relaxed.text
        entry["run_relaxed"] = run_script(entry, "relaxed", out_dir)
        entry["bash"] = result.text
    return entry


def summarize(entries: list[dict]) -> dict:
    conversion_counts = Counter(e["conversion"].get("status", "FAILED") for e in entries)
    run_counts = Counter(e["run"]["category"] for e in entries if e.get("run") is not None)
    correlation_counts = Counter(e["correlation"] for e in entries)
    todo_total = sum(e["conversion"].get("todo_count", 0) for e in entries)
    warning_total = sum(e["conversion"].get("warning_count", 0) for e in entries)
    error_total = sum(e["conversion"].get("error_count", 0) for e in entries)
    todo_originals = Counter()
    for e in entries:
        for todo in e["conversion"].get("todos", []):
            token = (todo.get("original") or todo.get("message") or "").strip()
            token = token.split()[0] if token else "?"
            todo_originals[token] += 1
    failure_reasons = Counter(
        analysis_reason(e["run"])
        for e in entries
        if e.get("run") is not None and e["run"]["category"] not in ("OK",)
    )
    relaxed_survived = 0
    for e in entries:
        rel = e.get("run_relaxed")
        if isinstance(rel, dict) and rel.get("category") == "OK":
            relaxed_survived += 1
    return {
        "files": len(entries),
        "conversion": dict(conversion_counts),
        "run": dict(run_counts),
        "correlation": dict(correlation_counts),
        "todo_total": todo_total,
        "warning_total": warning_total,
        "error_total": error_total,
        "todo_originals_top": todo_originals.most_common(30),
        "failure_reasons_top": failure_reasons.most_common(30),
        "failed_then_ok_without_strict": relaxed_survived,
    }


def cmd_run(args: argparse.Namespace) -> None:
    repo = Path(args.repo).expanduser().resolve() if args.repo else repo_root_from_file()
    core = load_core(repo)
    downloads = Path(args.downloads).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for index, (group, path) in enumerate(iter_corpus(downloads), 1):
        print(f"[{index:03d}] {group}/{path.name}", flush=True)
        entries.append(analyze_file(group, path, index, out_dir, core, not args.no_text))
    payload = {"summary": summarize(entries), "entries": entries}
    (out_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2), flush=True)


def cmd_anonymize(args: argparse.Namespace) -> None:
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    out_entries: list[dict] = []
    missing_commands = Counter()
    for e in entries:
        conv = e.get("conversion") or {}
        run = e.get("run")
        rel = e.get("run_relaxed")
        kind = "ps1" if str(e.get("source_path", "")).lower().endswith(".ps1") else "bat"
        anon_conv: dict = {
            "status": conv.get("status", "FAILED"),
            "encoding": conv.get("encoding", ""),
            "converted_lines": conv.get("converted_lines", 0),
            "unchanged_lines": conv.get("unchanged_lines", 0),
            "todo_count": conv.get("todo_count", 0),
            "warning_count": conv.get("warning_count", 0),
            "error_count": conv.get("error_count", 0),
        }
        for key in ("todos", "warnings", "errors"):
            items = conv.get(key) or []
            cats = Counter(str(d.get("category") or "other") for d in items)
            anon_conv[f"{key[:-1]}_categories"] = dict(sorted(cats.items()))
        anon_run = anonymize_run(run, missing_commands)
        anon_rel = anonymize_run(rel, missing_commands)
        out_entries.append(
            {
                "id": e.get("id", ""),
                "group": e.get("group", ""),
                "kind": kind,
                "source_lines": e.get("source_lines", 0),
                "conversion": anon_conv,
                "static": {
                    "syntax_ok": (e.get("static") or {}).get("syntax_ok", True),
                    "unsafe": (e.get("static") or {}).get("unsafe", []),
                },
                "run": anon_run,
                "run_relaxed": anon_rel,
                "correlation": e.get("correlation", ""),
            }
        )
    summary = anonymize_summary(out_entries, missing_commands)
    payload = {
        "meta": {
            "tool": "bat2sh v1.4.1 corpus analysis",
            "method": "bwrap --unshare-all 沙箱运行（无网络；仅挂载 /usr 与临时 workdir）",
            "anonymized": True,
            "note": "仅保留文件名、分类、计数、错误类型与命令 token；不含脚本原文/输出/绝对路径",
        },
        "summary": summary,
        "entries": out_entries,
    }
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已写入 {args.output}：{len(out_entries)} 条记录", flush=True)


def anonymize_run(run, missing_commands: Counter) -> dict | None:
    if run is None:
        return None
    if not isinstance(run, dict):
        return None
    if "error" in run:
        return {"error": True}
    out = {
        "category": run.get("category", ""),
        "flags": list(run.get("flags") or []),
        "rc": run.get("rc"),
        "timed_out": bool(run.get("timed_out", False)),
        "duration_s": run.get("duration_s", 0),
        "stdin": run.get("stdin", ""),
        "fixture_count": len(run.get("fixtures") or []),
        "stdout_bytes": run.get("stdout_bytes", 0),
        "stderr_bytes": run.get("stderr_bytes", 0),
    }
    fixtures = [n for n in (run.get("fixtures") or []) if SIMPLE_TOKEN_RE.match(n)]
    if fixtures:
        out["fixtures"] = fixtures
    cmds = [
        t for t in re.findall(r"([^\s:]+): command not found", run.get("stderr") or "")
        if SIMPLE_TOKEN_RE.match(t)
    ]
    if cmds:
        missing_commands.update(cmds)
        out["missing_commands"] = sorted(set(cmds))
    return out


def anonymize_summary(entries: list[dict], missing_commands: Counter) -> dict:
    conversion = Counter(e["conversion"]["status"] for e in entries)
    run = Counter(
        e["run"]["category"] for e in entries if isinstance(e.get("run"), dict) and e["run"]
    )
    correlation = Counter(e["correlation"] for e in entries)
    relaxed_ok = sum(
        1
        for e in entries
        if isinstance(e.get("run_relaxed"), dict) and e["run_relaxed"].get("category") == "OK"
    )
    todo_total = sum(e["conversion"]["todo_count"] for e in entries)
    warning_total = sum(e["conversion"]["warning_count"] for e in entries)
    error_total = sum(e["conversion"]["error_count"] for e in entries)
    return {
        "files": len(entries),
        "conversion": dict(sorted(conversion.items())),
        "run": dict(sorted(run.items())),
        "correlation": dict(sorted(correlation.items())),
        "todo_total": todo_total,
        "warning_total": warning_total,
        "error_total": error_total,
        "missing_commands_top": dict(missing_commands.most_common(20)),
        "failed_then_ok_without_strict": relaxed_ok,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="批量转换 + 沙箱运行分析")
    run_p.add_argument("--repo", default="", help="bat2sh 仓库根目录（默认：本脚本上两级）")
    run_p.add_argument("--downloads", required=True, help="语料根目录（含 bat-master 等子目录）")
    run_p.add_argument("--out", required=True, help="输出目录（results.json/converted/runs）")
    run_p.add_argument("--no-text", action="store_true", help="不落盘转换后脚本文本")
    run_p.set_defaults(func=cmd_run)

    anon_p = sub.add_parser("anonymize", help="生成脱敏版 results（移除原文/输出/路径）")
    anon_p.add_argument("--input", required=True, help="原始 results.json")
    anon_p.add_argument("--output", required=True, help="脱敏输出路径")
    anon_p.set_defaults(func=cmd_anonymize)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
