"""Phase 1 PoC: can proot run inside a Flet APK on Android (targetSdk 36)?

Instrumented probe battery.  Results also go to stdout (logcat tag flet.python).

Design notes, taken from reading termux/proot source:

  * proot NEVER execve()s the guest program.  translate_execve_enter() rewrites
    SYSARG_1 to a *loader* path -- $PROOT_LOADER, else <prefix>/libexec/proot/loader
    (PROOT_UNBUNDLE_LOADER), else a temp file referenced as /proc/self/fd/N.
    The loader then mmaps the guest ELF.  => only ONE file must be exec-able.
  * Android blocks execve() of app_data_file (SELinux "execute_no_trans") but
    still allows file:execute for mmap.  apk_data_file (nativeLibraryDir) allows
    both, so putting the loader there is the intended escape hatch.
  * expand_runner() (the -q/qemu path) is skipped for host-arch ELFs, and bionic
    linker64 has no "-0" option, so -q cannot be abused as a loader.
"""

from __future__ import annotations

import os
import platform
import stat
import subprocess
import tarfile
import threading
import time
import zipfile
from pathlib import Path

import flet as ft

_MACHINE = platform.machine().lower()
ABI = {"aarch64": "aarch64", "arm64": "aarch64",
       "x86_64": "x86_64", "amd64": "x86_64"}.get(_MACHINE, _MACHINE)

DATA = Path(os.environ.get("FLET_APP_STORAGE_DATA") or "/tmp/flet-proot-poc-data")
PREFIX = DATA / "usr"
BASH = PREFIX / "bin" / "bash"
PROOT = PREFIX / "bin" / "proot"
LOADER = PREFIX / "libexec" / "proot" / "loader"
ROOTFS = DATA / "rootfs"
LINKER = "/system/bin/linker64"

IS_ANDROID = os.path.exists(LINKER)

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
        return "asset missing"
    PREFIX.mkdir(parents=True, exist_ok=True)
    nf = nl = nx = 0
    with zipfile.ZipFile(zp) as z:
        for info in z.infolist():
            if info.filename == "SYMLINKS.txt":
                continue
            z.extract(info, PREFIX)
            nf += 1
        for line in z.read("SYMLINKS.txt").decode("utf-8", "replace").splitlines():
            if "\u2190" not in line:
                continue
            target, linkpath = line.split("\u2190", 1)
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


def install_proot() -> str:
    (PREFIX / "libexec" / "proot").mkdir(parents=True, exist_ok=True)
    pairs = [
        ("proot-" + ABI, PROOT),
        ("libtalloc.so.2-" + ABI, PREFIX / "lib" / "libtalloc.so.2"),
        ("libandroid-shmem.so-" + ABI, PREFIX / "lib" / "libandroid-shmem.so"),
        ("loader-" + ABI, LOADER),
    ]
    ok = []
    for src_name, dst in pairs:
        src = find_asset(src_name)
        if src is None:
            ok.append(src_name + ":MISSING")
            continue
        try:
            if dst.exists() or dst.is_symlink():
                dst.unlink()
        except OSError:
            os.chmod(dst, 0o600)
            dst.unlink()
        dst.write_bytes(src.read_bytes())
        _chmod_x(dst)
        ok.append(dst.name + ":" + str(dst.stat().st_size))
    return " ".join(ok)


def extract_rootfs() -> str:
    if (ROOTFS / "bin" / "busybox").exists():
        return "already present"
    tp = find_asset("alpine-" + ABI + ".tar.gz")
    if tp is None:
        return "asset missing"
    ROOTFS.mkdir(parents=True, exist_ok=True)
    n = 0
    with tarfile.open(tp, "r:gz") as t:
        try:
            t.extractall(ROOTFS, filter="fully_trusted")
        except TypeError:
            t.extractall(ROOTFS)
        n = len(t.getmembers())
    for p in ROOTFS.rglob("*"):
        if p.is_symlink() or p.is_dir():
            continue
        try:
            st = p.stat().st_mode
            if st & stat.S_IXUSR:
                os.chmod(p, (st | 0o555) & ~0o222)
        except OSError:
            pass
    return "members=%d" % n


def base_env() -> dict:
    env = dict(os.environ)
    env.update({
        "PREFIX": str(PREFIX),
        "PATH": str(PREFIX) + "/bin:" + str(PREFIX) + "/bin/applets",
        "LD_LIBRARY_PATH": str(PREFIX / "lib"),
        "HOME": str(DATA / "home"),
        "TMPDIR": str(PREFIX / "tmp"),
        # proot looks at PROOT_TMP_DIR (not TMPDIR) for its loader / f2fs probe
        "PROOT_TMP_DIR": str(PREFIX / "tmp"),
        "TERM": "xterm-256color",
        "LANG": "en_US.UTF-8",
        "SHELL": str(BASH),
    })
    (DATA / "home").mkdir(parents=True, exist_ok=True)
    (PREFIX / "tmp").mkdir(parents=True, exist_ok=True)
    return env


def guest_env() -> dict:
    env = base_env()
    env.update({
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/root",
    })
    return env


def probe(label: str, argv: list[str], env: dict | None = None,
          timeout: int = 25) -> dict:
    t0 = time.time()
    res = {"label": label, "argv": argv, "rc": None, "out": "", "err": "",
           "how": "", "secs": 0.0}
    log("--- PROBE " + label + ": " + " ".join(argv))
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, env=env or base_env())
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
           res["out"].strip()[:160], res["err"].strip()[:240]))
    return res


def find_native_lib_dirs() -> list[Path]:
    """/data/app is not listable by apps, so derive nativeLibraryDir from maps."""
    dirs: list[Path] = []
    try:
        maps = Path("/proc/self/maps").read_text(errors="replace")
    except OSError:
        return dirs
    for line in maps.splitlines():
        if "base.apk" not in line:
            continue
        p = line.split()[-1]
        if p.endswith("base.apk"):
            d = Path(p).parent / "lib" / ABI
            if d not in dirs:
                dirs.append(d)
    return dirs


def probe_memfd_exec(loader_bytes: bytes) -> dict:
    res = {"label": "memfd execve /proc/self/fd/N", "how": "", "rc": None,
           "err": "", "out": "", "secs": 0.0}
    if not hasattr(os, "memfd_create"):
        res["how"] = "NO-MEMFD-API"
        return res
    fd = None
    try:
        fd = os.memfd_create("prootloader")
        os.write(fd, loader_bytes)
        os.fchmod(fd, 0o700)
        r = subprocess.run(["/proc/self/fd/" + str(fd)], capture_output=True,
                           text=True, timeout=10, pass_fds=(fd,))
        res.update(rc=r.returncode, out=r.stdout, err=r.stderr, how="ran")
    except PermissionError as exc:
        res.update(how="EXEC-DENIED", err=str(exc))
    except OSError as exc:
        res.update(how="OSError errno=" + str(exc.errno), err=str(exc))
    except Exception as exc:  # noqa: BLE001
        res.update(how="EXC", err=type(exc).__name__ + ": " + str(exc))
    if fd is not None:
        try:
            os.close(fd)
        except Exception:
            pass
    log("--- memfd exec -> %s rc=%s err=%r" % (res["how"], res["rc"], res["err"][:200]))
    return res


def battery() -> str:
    out: list[str] = []
    probes: list[dict] = []

    def add(s: str) -> None:
        out.append(s)
        log(s)

    add("machine=%s ABI=%s IS_ANDROID=%s" % (_MACHINE, ABI, IS_ANDROID))
    add("DATA=%s" % DATA)
    add("extract_bootstrap -> %s" % extract_bootstrap())
    add("install_proot     -> %s" % install_proot())
    add("extract_rootfs    -> %s" % extract_rootfs())

    nlibs = find_native_lib_dirs()
    nlib = nlibs[0] if nlibs else None
    nlib_loader = (nlib / "libprootloader.so") if nlib else None
    add("nativeLibraryDir=%s" % nlib)
    add("nativeLayoutLoader=%s exists=%s"
        % (nlib_loader, bool(nlib_loader and nlib_loader.exists())))
    add("proot=%s loader=%s rootfs sh=%s"
        % (PROOT.exists(), LOADER.exists(), (ROOTFS / "bin" / "busybox").exists()))

    rootfs_bb = str(ROOTFS / "bin" / "busybox")
    genv = guest_env()
    PARGS = [LINKER, str(PROOT), "-r", str(ROOTFS),
             "-b", "/dev", "-b", "/proc", "-b", "/sys", "-w", "/"]

    probes.append(probe("A direct-exec rootfs busybox", [rootfs_bb, "echo", "hi"]))
    probes.append(probe("B linker64 proot --version", [LINKER, str(PROOT), "--version"]))
    probes.append(probe("C proot plain sh -c",
                        PARGS + ["/bin/sh", "-c", "echo hello; id; ls /"], env=genv))

    e_d = dict(genv)
    e_d["PROOT_LOADER"] = str(LOADER)
    probes.append(probe("D PROOT_LOADER=appdata",
                        PARGS + ["/bin/sh", "-c", "echo hi-D; ls /bin | head -3"],
                        env=e_d))

    if nlib_loader is not None:
        e_e = dict(genv)
        e_e["PROOT_LOADER"] = str(nlib_loader)
        probes.append(probe("E PROOT_LOADER=nativeLib",
                            PARGS + ["/bin/sh", "-c", "echo hi-E; id; ls /"],
                            env=e_e))
        probes.append(probe("E2 PROOT_LOADER=nativeLib uname",
                            PARGS + ["/bin/uname", "-a"], env=e_e))
        probes.append(probe("E3 PROOT_LOADER=nativeLib pipes",
                            PARGS + ["/bin/sh", "-c",
                                     "ls /bin | head -4; echo A | tr a-z A-Z"],
                            env=e_e))

        # Round 2: PROOT_NO_SECCOMP disables proot's seccomp accelerator, which is
        # the prime suspect for fork() -> ENOSYS ("can't fork: Function not implemented").
        e_ns = dict(e_e)
        e_ns["PROOT_NO_SECCOMP"] = "1"
        probes.append(probe("E4 NOSECCOMP sh -c id/ls",
                            PARGS + ["/bin/sh", "-c", "echo hi-E4; id; ls / | head -3"],
                            env=e_ns))
        probes.append(probe("E5 NOSECCOMP loop+pipe",
                            PARGS + ["/bin/sh", "-c",
                                     "for i in 1 2 3; do echo n=$i; done; echo abc | tr a-z A-Z"],
                            env=e_ns))
        probes.append(probe("E6 NOSECCOMP /bin/ls /",
                            PARGS + ["/bin/ls", "/"], env=e_ns))
        e_ns2 = dict(e_ns)
        e_ns2["PROOT_TMP_DIR"] = str(ROOTFS / "tmp")
        probes.append(probe("E7 NOSECCOMP write+read file",
                            PARGS + ["/bin/sh", "-c",
                                     "echo x > /tmp/t; cat /tmp/t; uname -m; pwd"],
                            env=e_ns2))
        probes.append(probe("E8 NOSECCOMP sh -c nested subshell",
                            PARGS + ["/bin/sh", "-c", "(echo sub; echo sub2) | wc -l"],
                            env=e_ns))

    # I. does fork() work in the app process WITHOUT proot?  (Termux bash pipeline:
    #    two forks, no exec) -- isolates "proot forbids fork" from "Android forbids fork".
    probes.append(probe("I termux bash pipeline (fork, no exec)",
                        [LINKER, str(BASH), "-c",
                         "echo a | while read x; do echo got=$x; done"],
                        env=base_env(), timeout=15))

    # J. plain proot with verbose syscall log, to catch the failing syscall
    probes.append(probe("J proot plain verbose",
                        [LINKER, str(PROOT), "-v", "4", "-r", str(ROOTFS),
                         "-b", "/dev", "-b", "/proc", "-b", "/sys", "-w", "/",
                         "/bin/sh", "-c", "echo hi-J; ls /"],
                        env=genv, timeout=20))

    probes.append(probe("F proot plain guest echo (no shell)",
                        PARGS + ["/bin/echo", "hi-F"], env=genv))
    probes.append(probe("G linker64 rootfs busybox (musl)",
                        [LINKER, rootfs_bb, "echo", "hi-G"],
                        env=dict(base_env(),
                                 LD_LIBRARY_PATH=str(PREFIX / "lib") + ":" + str(ROOTFS / "lib"))))

    try:
        lb = LOADER.read_bytes()
    except OSError:
        lb = b""
    if lb:
        probes.append(probe_memfd_exec(lb))

    if nlib is not None:
        try:
            entries = sorted(p.name for p in nlib.iterdir())
        except OSError as exc:
            add("nativeLibraryDir unreadable: %s" % exc)
            entries = []
        add("nativeLibraryDir n=%d hasLoader=%s first=%s writable=%s"
            % (len(entries), "libprootloader.so" in entries, entries[:4],
               os.access(nlib, os.W_OK)))
        for cand in entries:
            if cand.endswith(".so"):
                probes.append(probe("H direct-exec nativeLib/" + cand,
                                    [str(nlib / cand)], timeout=15))
                break

    c = next((p for p in probes if p["label"].startswith("C ")), None)
    e = next((p for p in probes if p["label"].startswith("E ")), None)
    e4 = next((p for p in probes if p["label"].startswith("E4")), None)
    if c and c["how"] == "ok" and "hello" in (c["out"] or ""):
        verdict = "PASS-PLAIN: proot subprocess exec works with no workaround"
    elif e4 and e4["how"] == "ok" and "hi-E4" in (e4["out"] or ""):
        verdict = "PASS: PROOT_LOADER=nativeLibraryDir + PROOT_NO_SECCOMP=1"
    elif e and e["how"] == "ok" and "hi-E" in (e["out"] or ""):
        verdict = "PARTIAL: loader works, guest forks fail (fork ENOSYS)"
    else:
        verdict = "FAIL: proot subprocess exec unavailable"
    add("")
    add("=== VERDICT: " + verdict + " ===")
    add("    C(plain)=%s  E(nativeLib)=%s  E4(noSeccomp)=%s"
        % (c["how"] if c else "n/a", e["how"] if e else "n/a",
           e4["how"] if e4 else "n/a"))
    for p in probes:
        add("  [%12s] %s rc=%s %ss" % (p["how"], p["label"], p["rc"], p["secs"]))
        if (p.get("out") or "").strip():
            add("        out: " + p["out"].strip()[:400])
        if (p.get("err") or "").strip():
            add("        err: " + p["err"].strip()[:400])
    return "\n".join(out)


def main(page: ft.Page) -> None:
    page.title = "proot PoC"
    page.scroll = ft.ScrollMode.AUTO
    status = ft.Text("running proot probes ...", selectable=True)
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

    page.add(ft.Text("proot in Flet APK - Phase 1 probes", size=18,
                     weight=ft.FontWeight.BOLD),
             ft.Row([busy, status]), report)
    threading.Thread(target=startup, daemon=True).start()


ft.run(main)
