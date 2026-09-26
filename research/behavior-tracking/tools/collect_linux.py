#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bat2sh 行为采集 —— **Linux 侧**（bwrap 沙箱）

镜像 `tools/collect.py`（W 侧，真机 Windows）的**输出结构**，
使同一脚本的两次执行可以逐字段对比（设计见 `../oracle-design.md`）。

    W = 真机 cmd.exe 执行原始 .bat   →  tools/collect.py
    L = 产物 .sh 在 bwrap 沙箱执行    →  本文件

用法：
    python3 tools/collect_linux.py --script samples/poc-02-fileops.bat \\
            --output results/oracle/L-poc-02.json
    python3 tools/collect_linux.py --artifact /tmp/x.sh --source samples/x.bat \\
            --guest-name x.bat --output results/oracle/L-x.json

设计要点（**每条都有理由，见 ../oracle-design.md**）：

1. **产物沿用 W 侧 guest 文件名**（含 `.bat`），内容是 bash。
   实测 `%~nx0` → `$(basename "$0")`、`for %%i in (*.bat)` → `for i in *.bat`，
   脚本**能观测自己的名字和目录里有哪些 .bat**。若产物叫 `X.sh`，
   目录列表在两侧不同 —— 那是**采集设施引入的假差异**。

2. **bwrap 必须显式 `--symlink usr/bin /bin`**：Arch 的 `/bin`、`/lib` 是符号链接，
   不补则 `execvp` 失败（实测 `bwrap: execvp /bin/echo: No such file or directory`）。

3. **工作根每次全新重建**（`tmpdir-recreate`）—— 对应 W 侧的 qcow2 覆盖层回滚，
   作用相同：保证样本起点逐字节相同。

4. **每个文件算三个哈希**（只读两次盘）：
   - `Hash`             原始字节 SHA256（与 W 的 `Hash` 同定义，可直接比）
   - `hash_lf_to_crlf`  LF→CRLF 后的 SHA256（规则 N10）
   - `hash_cp936_crlf`  UTF-8→CP936 且 LF→CRLF 后的 SHA256（规则 N11，语料 110/151 是 GBK）
   哈希相等等价于"内容 = W 内容（模该变换）"，是**精确陈述**，不是"差不多"。

退出码：
  0  采集成功
  1  环境检查失败（bwrap 缺失等，**硬失败**）
  2  转换失败
  3  沙箱执行故障
  4  用法错误
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCHEMA_VERSION = 4                    # 与 W 侧 collect.py 的 SCHEMA_VERSION 对齐
COLLECTOR_VERSION = "1.0.0"
DEFAULT_BWRAP = "bwrap"

#: 转换器可执行文件（`--bat2sh` 可覆盖）。默认取 PATH 上的 `bat2sh`；
#: 验证**工作树**（而非已安装包）时指向包装脚本，并把解析结果记入指纹。
DEFAULT_BAT2SH = "bat2sh"
HASH_MAX_BYTES = 8 << 20              # 超过 8 MiB 只记 size（语料样本都远小于此）
FIXED_TZ = "Asia/Shanghai"            # 与 W 侧 fixed_time 的 UTC+8 对齐
LOCALE = "C.UTF-8"                    # 确定性排序；顺序差异由 D4 归因，不预先抹平

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parents[2]

# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest().upper()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def lf_to_crlf(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n").replace(b"\n", b"\r\n")


def cp936_crlf(b: bytes) -> bytes | None:
    """UTF-8 字节 → CP936 字节 → CRLF。不可解码/不可编码时返回 None（规则**不适用**）。

    返回 None 而不是抛错：规则不适用**不得**产生假匹配。
    """
    try:
        text = b.decode("utf-8")
    except UnicodeDecodeError:
        return None
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    try:
        return norm.encode("cp936").replace(b"\n", b"\r\n")
    except UnicodeEncodeError:
        return None


def hashes_for(p: Path) -> dict:
    entry: dict = {"FullName": str(p)}
    try:
        size = p.stat().st_size
    except OSError as exc:
        return {**entry, "error": str(exc)}
    entry["Length"] = size
    if size > HASH_MAX_BYTES:
        entry["Hash"] = None
        entry["hash_skipped"] = f"size > {HASH_MAX_BYTES}"
        return entry
    raw = p.read_bytes()
    entry["Hash"] = sha256_bytes(raw)
    entry["hash_lf_to_crlf"] = sha256_bytes(lf_to_crlf(raw))
    c = cp936_crlf(raw)
    entry["hash_cp936_crlf"] = sha256_bytes(c) if c is not None else None
    return entry


def manifest(root: Path) -> tuple[dict, list[str]]:
    """递归清单。返回 (files, dirs)。files 的键是相对 root 的 POSIX 路径。"""
    files: dict = {}
    dirs: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        for d in sorted(dirnames):
            if rel_dir == ".":
                dirs.append(d)
            else:
                dirs.append(f"{rel_dir}/{d}")
        for f in sorted(filenames):
            p = Path(dirpath) / f
            key = f if rel_dir == "." else f"{rel_dir}/{f}"
            files[key] = hashes_for(p)
    return files, sorted(dirs)


def diff(before: dict, after: dict) -> dict:
    """与 W 侧 `vm.diff()` **同定义**（集合差 + Hash 比较）。"""
    created = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified = sorted(p for p in set(before) & set(after)
                      if before[p].get("Hash") != after[p].get("Hash"))
    unchanged = sorted(p for p in set(before) & set(after)
                       if before[p].get("Hash") == after[p].get("Hash"))
    return {"created": created, "modified": modified,
            "deleted": deleted, "unchanged": unchanged}


# --------------------------------------------------------------------------
# 转换
# --------------------------------------------------------------------------


def bat2sh_identity(exe: str) -> dict:
    """记录**实际使用**的转换器（路径 + `--version`），堵住"用哪个 bat2sh"的复现缺口。"""
    resolved = shutil.which(exe) or exe
    try:
        proc = subprocess.run([resolved, "--version"], capture_output=True,
                              text=True, timeout=60)
        version = (proc.stdout or proc.stderr).strip().splitlines()[0]
    except Exception as exc:  # noqa: BLE001
        version = f"<取版本失败: {exc}>"
    return {"argv0": exe, "resolved": resolved, "version": version}


def convert(src: Path, out: Path, exe: str = DEFAULT_BAT2SH) -> tuple[bool, str, list[str]]:
    """调 bat2sh **CLI**（产品门面，而非内部 API），argv 记入指纹以便复现。

    口径说明：CLI 默认 `bash_check=True`（= 用户实际拿到的产物）。
    语料统计用的是"原始转换口径 `bash_check=False`"（`measure.py`），
    但本 oracle 要回答的是"**用户拿到的东西**跑起来对不对"，故用 CLI 默认。
    """
    argv = [exe, "--cli", "-q", "-o", str(out), str(src)]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    if not out.is_file():
        return False, (proc.stderr or proc.stdout or "").strip(), argv
    return True, "", argv


def neutralize_errexit(p: Path) -> bool:
    """规则 N13 的**诊断**手段（不是归一化）：把产物里的 `set -euo pipefail` 中和掉。

    用途：若 L 因 `set -e` 提前中止而 W 继续执行，重跑一次即可拿到
    "差异是否源于 errexit"的**证据**（对应已知差异 D5）。
    ⚠️ 重跑结果**不替换**正式 L 指纹，只作归因证据。
    """
    text = p.read_text(encoding="utf-8", errors="replace")
    new, n = re.subn(
        r"^(\s*)set\s+-euo\s+pipefail\s*$",
        r"\1set +e +u; set +o pipefail  # DIAGNOSTIC(N13): errexit 已中和",
        text, count=1, flags=re.M)
    if n == 0:                       # 兜底：产物里没有该行就附加一行
        new = text + "\nset +e +u; set +o pipefail  # DIAGNOSTIC(N13)\n"
    p.write_text(new, encoding="utf-8")
    return n > 0


# --------------------------------------------------------------------------
# 采集
# --------------------------------------------------------------------------


def bwrap_argv(run_dir: Path, script: Path) -> list[str]:
    return [
        DEFAULT_BWRAP,
        "--unshare-all",                 # 无网络 ≡ W 的 isolated
        "--die-with-parent",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/etc", "/etc",
        # ⚠️ Arch 的 /bin /sbin /lib /lib64 是符号链接，必须显式补（实测）
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/sbin", "/sbin",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--bind", str(run_dir), str(run_dir),
        "--chdir", str(run_dir),
        "/bin/bash", str(script),
    ]


def check_env(bat2sh_exe: str = DEFAULT_BAT2SH) -> list[dict]:
    checks = []
    bw = shutil.which(DEFAULT_BWRAP)
    checks.append({"check": "bwrap 存在", "ok": bool(bw),
                   "detail": f"{bw} ({subprocess.run([DEFAULT_BWRAP,'--version'],capture_output=True,text=True).stdout.strip()})" if bw else "未找到"})
    b2s = shutil.which(bat2sh_exe) or (bat2sh_exe if Path(bat2sh_exe).is_file() else None)
    checks.append({"check": "bat2sh 存在", "ok": bool(b2s), "detail": str(b2s)})
    ok = all(c["ok"] for c in checks)
    if not ok:
        raise SystemExit(1)
    return checks


def collect(script: Path, output: Path, *, guest_name: str | None = None,
            bat2sh_exe: str = DEFAULT_BAT2SH,
            artifact: Path | None = None, keep: bool = False,
            timeout: int = 180, workroot: Path | None = None,
            run_name: str = "samples", neutralize_errexit_flag: bool = False) -> dict:
    t0 = time.time()
    timings: dict = {}
    checks = check_env(bat2sh_exe)

    src = script.resolve()
    src_bytes = src.read_bytes()
    gname = guest_name or src.name
    if "/" in gname or "\\" in gname:
        raise SystemExit(f"guest_name 不得含路径分隔符: {gname}")

    workroot = workroot or Path(os.environ.get("ORACLE_WORKROOT", "/tmp/bat2sh-oracle"))
    # ⚠️ 工作根目录名必须与 W 侧一致（W 是 `C:\poc\samples` ⇒ basename `samples`）。
    # 理由：`for /r %%i in (.)` 这类样本会**为每个目录建同名文件，包括工作根自己**
    # （实测 V5：W 建 `samples.txt`，L 若叫 `run` 就建 `run.txt`）——
    # 工作根名不同会制造**采集设施引入的假差异**（oracle-design §3.2）。
    run_dir = Path(workroot).resolve() / f"{src.stem}-{int(time.time()*1000)}" / run_name
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    # --- 转换 ---
    t = time.time()
    if artifact is not None:
        conv_ok, conv_err, conv_argv = True, "", []
        shutil.copy2(artifact, run_dir / gname)
    else:
        conv_ok, conv_err, conv_argv = convert(src, run_dir / gname, bat2sh_exe)
    timings["convert"] = int((time.time() - t) * 1000)
    if not conv_ok:
        print(f"转换失败: {conv_err}", file=sys.stderr)
        raise SystemExit(2)
    run_dir.chmod(0o755)
    (run_dir / gname).chmod(0o755)
    if neutralize_errexit_flag:
        hit = neutralize_errexit(run_dir / gname)
        timings["neutralize_errexit"] = 1 if hit else 0

    # --- 执行前清单（已知产物：采集器自己放进去的脚本） ---
    t = time.time()
    before_files, before_dirs = manifest(run_dir)
    timings["before_manifest"] = int((time.time() - t) * 1000)
    known = [gname]

    # --- 沙箱执行 ---
    t = time.time()
    argv = bwrap_argv(run_dir, run_dir / gname)
    timeout_hit = False
    try:
        proc = subprocess.run(
            argv, capture_output=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "HOME": str(run_dir),
                 "TZ": FIXED_TZ, "LC_ALL": LOCALE, "LANG": LOCALE},
        )
        out_b, err_b, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        timeout_hit = True
        out_b = exc.stdout or b""
        err_b = exc.stderr or b""
        rc = None
    timings["execute"] = int((time.time() - t) * 1000)

    # --- 执行后清单 ---
    t = time.time()
    after_files, after_dirs = manifest(run_dir)
    timings["after_manifest"] = int((time.time() - t) * 1000)

    d = diff(before_files, after_files)
    created = [p for p in d["created"] if p not in known]
    created_raw = d["created"]
    deleted = d["deleted"]
    modified = d["modified"]
    created_dirs = sorted(set(after_dirs) - set(before_dirs))
    deleted_dirs = sorted(set(before_dirs) - set(after_dirs))

    fp = {
        "schema_version": SCHEMA_VERSION,
        "harness": {
            "tool": "collect_linux.py",
            "version": COLLECTOR_VERSION,
            "git_head": git_head(),
            "invocation": sys.argv,
            "convert_argv": conv_argv,
            "convert_tool": bat2sh_identity(bat2sh_exe),
            "side": "L",
        },
        "script": {
            "name": src.name,
            "sha256": sha256_bytes(src_bytes),
            "size": len(src_bytes),
            "local_path": str(src),
            "guest_path": f"<WORK>/{gname}",
            "guest_name": gname,
            "renamed": gname != src.name,
        },
        "environment": {
            "guest_os": f"Linux (bwrap)",
            "kernel_release": os.uname().release,
            "machine": os.uname().machine,
            "console_codepage": 65001,           # UTF-8；W 侧是 936 —— 显式声明，便于对照
            "timezone": FIXED_TZ,
            "locale": LOCALE,
            "clock_fixed": False,                # ← L 侧**无法**固定时钟（D7）
        },
        "rollback": {
            "method": "tmpdir-recreate",
            "run_dir": str(run_dir),
            "kept": keep,
        },
        "execution": {
            "argv": argv,
            "stdin": "/dev/null",
            "exit_code": rc,
            "signal": None,
            "duration_ms": timings["execute"],
            "timeout": timeout_hit,
            "out_truncated": False,
            "err_truncated": False,
        },
        "stdout": {"b64": base64.b64encode(out_b).decode(),
                   "text": out_b.decode("utf-8", "replace")},
        "stderr": {"b64": base64.b64encode(err_b).decode(),
                   "text": err_b.decode("utf-8", "replace")},
        "filesystem": {
            "method": "manifest-diff-linux-v1",
            "scope": ["<WORK>"],
            "baseline_manifest_hash": manifest_hash(before_files),
            "baseline_manifest": before_files,
            "before_count": len(before_files),
            "after_count": len(after_files),
            "created": created,
            "modified": modified,
            "deleted": deleted,
            "unchanged_count": len(d["unchanged"]),
            "known_artifacts": [{"path": gname, "reason": "harness artifact"}],
            "created_raw": created_raw,
            "after_manifest": after_files,
            "dirs_method": "walk",
            "baseline_dirs": before_dirs,
            "after_dirs": after_dirs,
            "created_dirs": created_dirs,
            "deleted_dirs": deleted_dirs,
            "blind_spots": ["reads", "transient-effects", "metadata-only-writes",
                            "registry-not-collected", "process-not-collected",
                            "network-not-collected"],
        },
        "process": [],
        "network": {"mode": "isolated", "isolated": True,
                    "isolation_method": "bwrap-unshare-all",
                    "attempted": None,
                    "attempted_basis": "unshare-all：无网络命名空间，无出网路径（结构性零）",
                    "connections": [], "bytes_sent": 0, "bytes_recv": 0,
                    "egress_frames": 0},
        "env_checks": checks,
        "execution_workdir": "<WORK>",
        "notes": [
            "clock_not_fixed: L 侧无法固定时钟（bwrap 不能设 CAP_SYS_TIME）；"
            "含 %date%/%time% 的样本只能靠规则 N8 形状化（D7）",
            "artifact 沿用 W 侧 guest 文件名（含 .bat）—— 见 oracle-design §3.2.1",
        ],
        "timings": {**timings, "total_ms": int((time.time() - t0) * 1000)},
    }

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(fp, ensure_ascii=False, indent=2), encoding="utf-8")

    if not keep:
        shutil.rmtree(run_dir.parent, ignore_errors=True)

    return fp


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def manifest_hash(m: dict) -> str:
    blob = json.dumps({k: m[k].get("Hash") for k in sorted(m)},
                      ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="bat2sh 行为采集（Linux/bwrap 侧）")
    ap.add_argument("--script", help="源 .bat/.cmd 路径（自动转换）")
    ap.add_argument("--artifact", help="已是 bash 的产物路径（跳过转换）")
    ap.add_argument("--source", help="--artifact 时的原始 .bat（用于记录 name/sha256）")
    ap.add_argument("--guest-name", help="沙箱内文件名（默认沿用源文件名，含 .bat）")
    ap.add_argument("--output", required=True, help="指纹输出 .json")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--workroot", default=None)
    ap.add_argument("--run-name", default="samples",
                    help="沙箱工作根目录名；**必须与 W 侧 C:\\poc\\samples 的 basename 一致**")
    ap.add_argument("--bat2sh", default=DEFAULT_BAT2SH,
                    help="转换器可执行文件（默认 PATH 上的 bat2sh）。验证**工作树**时"
                         "指向包装脚本；解析结果与 --version 会记入指纹的 "
                         "harness.convert_tool，避免'用哪个 bat2sh'不可复现")
    ap.add_argument("--keep", action="store_true", help="保留沙箱目录（调试）")
    ap.add_argument("--neutralize-errexit", action="store_true",
                    help="**诊断**（规则 N13）：中和 set -euo pipefail 后执行，用于归因 D5")
    args = ap.parse_args()

    if args.artifact:
        src = Path(args.source) if args.source else Path(args.artifact)
        if not src.is_file():
            print(f"源文件不存在: {src}", file=sys.stderr)
            return 4
        fp = collect(src, Path(args.output), guest_name=args.guest_name,
                     bat2sh_exe=args.bat2sh,
                     artifact=Path(args.artifact), keep=args.keep,
                     timeout=args.timeout, workroot=args.workroot,
                     run_name=args.run_name,
                     neutralize_errexit_flag=args.neutralize_errexit)
    elif args.script:
        src = Path(args.script)
        if not src.is_file():
            print(f"样本不存在: {src}", file=sys.stderr)
            return 4
        fp = collect(src, Path(args.output), guest_name=args.guest_name,
                     bat2sh_exe=args.bat2sh,
                     keep=args.keep, timeout=args.timeout, workroot=args.workroot,
                     run_name=args.run_name,
                     neutralize_errexit_flag=args.neutralize_errexit)
    else:
        print("需要 --script 或 --artifact", file=sys.stderr)
        return 4

    e = fp["execution"]
    fs = fp["filesystem"]
    print(f"样本        : {fp['script']['name']}  sha256={fp['script']['sha256'][:16]}…")
    print(f"guest_name  : {fp['script']['guest_name']}")
    print(f"exit_code   : {e['exit_code']}  timeout={e['timeout']}")
    print(f"stdout      : {fp['stdout']['text']!r}")
    print(f"stderr      : {fp['stderr']['text']!r}")
    print(f"created     : {fs['created']}")
    print(f"created_dirs: {fs['created_dirs']}")
    print(f"deleted     : {fs['deleted']}")
    print(f"指纹已写入  : {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
