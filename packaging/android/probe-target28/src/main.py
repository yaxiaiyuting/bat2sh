"""Phase A 探针：targetSdk 28 + Termux 本体（不用 proot）。

判据（任务书 3.2）：
  * 子进程 + 管道  -> rc=0
  * 脚本内 fork    -> rc=0

沿用上一 session 已验证的三条硬约束：
  1. bootstrap zip 的根目录就是 $PREFIX -> 解压到 <DATA>/usr
  2. zip 不含符号链接，靠 SYMLINKS.txt（格式 <target>←<linkpath>）
  3. Termux 二进制 PT_INTERP=/system/bin/linker64，必须注入
     PREFIX / PATH / LD_LIBRARY_PATH / HOME / TMPDIR

本文件刻意不含任何反斜杠转义，便于嵌入生成脚本。
"""

from __future__ import annotations

import os
import platform
import stat
import subprocess
import threading
import time
import zipfile
from pathlib import Path

import flet as ft

NL = chr(10)
ARROW = chr(0x2190)

_MACHINE = platform.machine().lower()
ABI = {"aarch64": "aarch64", "arm64": "aarch64",
       "x86_64": "x86_64", "amd64": "x86_64"}.get(_MACHINE, _MACHINE)

DATA = Path(os.environ.get("FLET_APP_STORAGE_DATA") or "/tmp/probe-target28-data")
PREFIX = DATA / "usr"
BASH = PREFIX / "bin" / "bash"
LINKER = "/system/bin/linker64"

LOG: list[str] = []


def log(msg: str) -> None:
    line = "[" + time.strftime("%H:%M:%S") + "] " + str(msg)
    LOG.append(line)
    print(line, flush=True)


def find_asset(name: str) -> Path | None:
    here = Path(__file__).resolve()
    cands: list[Path] = []
    for var in ("FLET_ASSETS_DIR", "FLET_ASSETS", "FLET_APP_ASSETS"):
        v = os.environ.get(var)
        if v:
            cands.append(Path(v))
    cands += [here.parent / "assets", here.parent.parent / "assets",
              Path.cwd() / "assets", DATA / "assets"]
    for c in cands:
        p = c / name
        if p.is_file():
            return p
    return None


def _chmod_x(p: Path) -> bool:
    try:
        st = p.stat().st_mode
        os.chmod(p, (st | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                 & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        return True
    except OSError:
        return False


def extract_bootstrap() -> str:
    if BASH.exists():
        return "already present"
    zp = find_asset("bootstrap-" + ABI + ".zip")
    if zp is None:
        return "asset MISSING"
    PREFIX.mkdir(parents=True, exist_ok=True)
    nf = nl = nx = 0
    with zipfile.ZipFile(zp) as z:
        for info in z.infolist():
            if info.filename == "SYMLINKS.txt":
                continue
            z.extract(info, PREFIX)
            nf += 1
        for line in z.read("SYMLINKS.txt").decode("utf-8", "replace").splitlines():
            if ARROW not in line:
                continue
            target, linkpath = line.split(ARROW, 1)
            lp = PREFIX / linkpath.lstrip("./")
            try:
                lp.parent.mkdir(parents=True, exist_ok=True)
                if lp.is_symlink() or lp.exists():
                    lp.unlink()
                os.symlink(target, lp)
                nl += 1
            except OSError:
                pass
    for sub in ("bin", "libexec", "lib"):
        d = PREFIX / sub
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file() and not p.is_symlink() and _chmod_x(p):
                    nx += 1
    return "files=%d links=%d exec=%d" % (nf, nl, nx)


def bash_env() -> dict:
    env = dict(os.environ)
    env.update({
        "PREFIX": str(PREFIX),
        "PATH": str(PREFIX) + "/bin:" + str(PREFIX) + "/bin/applets",
        "LD_LIBRARY_PATH": str(PREFIX / "lib"),
        "HOME": str(DATA / "home"),
        "TMPDIR": str(PREFIX / "tmp"),
        "TERM": "xterm-256color",
        "LANG": "en_US.UTF-8",
        "SHELL": str(BASH),
    })
    (DATA / "home").mkdir(parents=True, exist_ok=True)
    (PREFIX / "tmp").mkdir(parents=True, exist_ok=True)
    return env


def probe(label: str, argv: list[str], timeout: int = 30) -> dict:
    t0 = time.time()
    res = {"label": label, "argv": argv, "rc": None, "out": "", "err": "",
           "how": "", "secs": 0.0}
    log("--- PROBE " + label + ": " + " ".join(argv))
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, env=bash_env())
        res.update(rc=r.returncode, out=r.stdout, err=r.stderr,
                   how="ok" if r.returncode == 0 else "ran-nonzero")
    except PermissionError as exc:
        res.update(rc=-1, err="PermissionError: " + str(exc), how="EXEC-DENIED")
    except FileNotFoundError as exc:
        res.update(rc=-2, err="FileNotFoundError: " + str(exc), how="ENOENT")
    except OSError as exc:
        res.update(rc=-3, err=type(exc).__name__ + ": " + str(exc),
                   how="OSError errno=" + str(exc.errno))
    except subprocess.TimeoutExpired:
        res.update(rc=124, err="timeout %ds" % timeout, how="TIMEOUT")
    except Exception as exc:  # noqa: BLE001
        res.update(rc=-9, err=type(exc).__name__ + ": " + str(exc), how="EXC")
    res["secs"] = round(time.time() - t0, 2)
    log("    -> %s rc=%s %ss out=%r err=%r"
        % (res["how"], res["rc"], res["secs"],
           res["out"].strip()[:200], res["err"].strip()[:240]))
    return res


def selinux_domain() -> str:
    try:
        return Path("/proc/self/attr/current").read_text(errors="replace").strip()
    except OSError as exc:
        return "unreadable: " + str(exc)


def battery() -> str:
    out: list[str] = []
    probes: list[dict] = []

    def add(s: str) -> None:
        out.append(s)
        log(s)

    add("machine=%s ABI=%s" % (_MACHINE, ABI))
    add("SELinux self domain = %s" % selinux_domain())
    add("DATA=%s" % DATA)
    add("extract_bootstrap -> %s" % extract_bootstrap())
    add("bash exists=%s" % BASH.exists())

    # 探针脚本：合法（内含管道 / 外部命令 / 循环 fork）
    good = DATA / "probe-good.sh"
    good.write_text(chr(10).join([
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "echo SCRIPT-START",
        "ls $PREFIX/bin | head -3",
        "for f in a b c; do echo item=$f; done | tr a-z A-Z",
        "echo COUNT=$(ls $PREFIX/bin | wc -l)",
        "echo SCRIPT-OK",
    ]) + chr(10), encoding="utf-8")
    # 探针脚本：非法（bash -n 必须报错）
    bad = DATA / "probe-bad.sh"
    bad.write_text(chr(10).join([
        "if [ 1 -eq 1 ; then",
        "  echo broken",
    ]) + chr(10), encoding="utf-8")

    L = [LINKER, str(BASH)]

    probes.append(probe("A 直执 bash（不经 linker64）",
                        [str(BASH), "-c", "echo direct-ok; id"]))
    probes.append(probe("B linker64 bash 基线",
                        L + ["-c", "echo hello; id; uname -a"]))
    probes.append(probe("C 管道 + 外部命令（沙箱内路径）",
                        L + ["-c", "ls $PREFIX/bin | head -5 | while read x; "
                                   "do echo L=$x; done"]))
    probes.append(probe("C2 管道 cat/tr/wc",
                        L + ["-c", "echo abc | cat | tr a-z A-Z | wc -c"]))
    probes.append(probe("D 脚本内 fork（bash script.sh）",
                        L + [str(good)]))
    probes.append(probe("E for + pipe + tr",
                        L + ["-c", "for f in a b c; do echo i=$f; done | tr a-z A-Z"]))
    probes.append(probe("F bash -n 合法脚本", L + ["-n", str(good)]))
    probes.append(probe("G bash -n 非法脚本（期望 rc!=0）", L + ["-n", str(bad)]))
    # 直接执行脚本本身（需要 exec 位 + shebang -> 内核再 execve bash）
    try:
        os.chmod(good, 0o755)
    except OSError:
        pass
    probes.append(probe("D2 ./script.sh 直接执行（shebang）", [str(good)]))

    # 嵌套：脚本调用脚本
    outer = DATA / "probe-outer.sh"
    outer.write_text(chr(10).join([
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "echo OUTER-START",
        "bash $PREFIX/../probe-good.sh",
        "echo OUTER-OK",
    ]) + chr(10), encoding="utf-8")
    probes.append(probe("D3 脚本调用脚本（嵌套 fork）", L + [str(outer)]))

    probes.append(probe("H env 报告",
                        L + ["-c", "echo PREFIX=$PREFIX; echo PATH=$PATH; "
                                   "echo LD_LIBRARY_PATH=$LD_LIBRARY_PATH; pwd; id"]))

    c = next((p for p in probes if p["label"].startswith("C ")), None)
    d = next((p for p in probes if p["label"].startswith("D ")), None)
    g = next((p for p in probes if p["label"].startswith("G ")), None)
    c2 = next((p for p in probes if p["label"].startswith("C2")), None)
    d2 = next((p for p in probes if p["label"].startswith("D2")), None)
    d3 = next((p for p in probes if p["label"].startswith("D3")), None)
    fork_ok = all(p is not None and p["how"] == "ok" for p in (c, c2, d, d2, d3))
    if fork_ok:
        verdict = "PASS: 子进程 exec / fork 恢复，完整 shell 能力可用"
    else:
        verdict = "FAIL: fork 仍不可用 -> 暂停，评估降级方案"

    add("")
    add("=== VERDICT: " + verdict + " ===")
    add("    C=%s C2=%s D=%s D2=%s D3=%s | G(bash -n 检出)=%s"
        % (c["how"] if c else "n/a", c2["how"] if c2 else "n/a",
           d["how"] if d else "n/a", d2["how"] if d2 else "n/a",
           d3["how"] if d3 else "n/a", ("rc=%s" % g["rc"]) if g else "n/a"))
    for p in probes:
        add("  [%12s] %s rc=%s %ss" % (p["how"], p["label"], p["rc"], p["secs"]))
        if (p.get("out") or "").strip():
            add("        out: " + p["out"].strip()[:400])
        if (p.get("err") or "").strip():
            add("        err: " + p["err"].strip()[:400])
    return chr(10).join(out)


def main(page: ft.Page) -> None:
    page.title = "Phase A: targetSdk 28 probe"
    page.scroll = ft.ScrollMode.AUTO
    status = ft.Text("running Phase A probes ...", selectable=True)
    report = ft.TextField(multiline=True, read_only=True, min_lines=20,
                          max_lines=40, text_size=11, value="", expand=True)
    busy = ft.ProgressRing(width=18, height=18, visible=True)

    def startup() -> None:
        try:
            txt = battery()
        except Exception as exc:  # noqa: BLE001
            txt = "battery crashed: %s: %s" % (type(exc).__name__, exc)
            log(txt)
        report.value = txt
        status.value = "done"
        busy.visible = False
        page.update()

    page.add(ft.Text("Phase A - targetSdk 28 + Termux runtime", size=18,
                     weight=ft.FontWeight.BOLD),
             ft.Row([busy, status]), report)
    threading.Thread(target=startup, daemon=True).start()


ft.run(main)
