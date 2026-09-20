"""内嵌 Termux 运行时：解压 bootstrap、处理 SYMLINKS、注入环境、定位 bash。

三条硬约束（上一 session 实测，见 docs/flet-termux-poc-report.md）：
  1. bootstrap zip 的**根目录就是 $PREFIX** -> 必须解压到 <DATA>/usr，
     才会得到 <DATA>/usr/bin/bash。
  2. zip 里**不含符号链接**，改用 SYMLINKS.txt 记录，格式是
     <target>←<linkpath>（target 在前）。不处理它 bash 连 libreadline 都找不到。
  3. Termux 二进制是 Bionic 链接，PT_INTERP=/system/bin/linker64，
     DT_RUNPATH 硬编码 /data/data/com.termux/files/usr/lib。
     必须注入 PREFIX / PATH / LD_LIBRARY_PATH / HOME / TMPDIR。

Phase A 实测（docs/android-poc-v2-report.md）：targetSdk 28 时 SELinux 域为
untrusted_app_27，应用私有目录内的二进制**可以直接 execve**，因此入口进程
优先直执；linker64 仅作为其他设备/targetSdk 的兜底。
"""

from __future__ import annotations

import os
import platform
import stat
import subprocess
import zipfile
from pathlib import Path

NL = chr(10)
ARROW = chr(0x2190)
LINKER64 = "/system/bin/linker64"

_ABI_MAP = {
    "aarch64": "aarch64",
    "arm64": "aarch64",
    "x86_64": "x86_64",
    "amd64": "x86_64",
}


def host_abi() -> str:
    m = platform.machine().lower()
    return _ABI_MAP.get(m, m)


def _chmod_x(p: Path) -> bool:
    try:
        st = p.stat().st_mode
        os.chmod(p, (st | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                 & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        return True
    except OSError:
        return False


def find_asset(name: str) -> Path | None:
    """Flet 打包后 assets 的位置随平台/版本而异，逐个候选探测。"""
    here = Path(__file__).resolve().parent
    cands: list[Path] = []
    for var in ("FLET_ASSETS_DIR", "FLET_ASSETS", "FLET_APP_ASSETS"):
        v = os.environ.get(var)
        if v:
            cands.append(Path(v))
    cands += [here / "assets", here.parent / "assets", Path.cwd() / "assets"]
    for c in cands:
        p = c / name
        if p.is_file():
            return p
    return None


class Termux:
    """内嵌 Termux 运行时的定位、解压与环境注入。"""

    def __init__(self, data_dir: Path) -> None:
        self.data = Path(data_dir)
        self.abi = host_abi()
        self.prefix = self.data / "usr"
        self.bash = self.prefix / "bin" / "bash"
        self.home = self.data / "home"
        self.tmp = self.prefix / "tmp"
        self.work = self.data / "work"
        self.linker64 = Path(LINKER64)
        # direct | linker64 | none | unresolved
        self.entry_mode = "unresolved"

    # ------------------------------------------------------------ 状态
    @property
    def is_android(self) -> bool:
        return self.linker64.exists()

    @property
    def ready(self) -> bool:
        return self.bash.exists()

    # ------------------------------------------------------------ 解压
    def ensure(self) -> str:
        """首次启动解压 bootstrap；已就绪则直接返回。"""
        if self.bash.exists():
            return "runtime ready"
        zp = find_asset("bootstrap-" + self.abi + ".zip")
        if zp is None:
            return "bootstrap asset MISSING: bootstrap-%s.zip" % self.abi
        self.prefix.mkdir(parents=True, exist_ok=True)
        nf = nl = nx = 0
        with zipfile.ZipFile(zp) as z:
            for info in z.infolist():
                if info.filename == "SYMLINKS.txt":
                    continue
                z.extract(info, self.prefix)
                nf += 1
            for line in z.read("SYMLINKS.txt").decode("utf-8", "replace").splitlines():
                if ARROW not in line:
                    continue
                target, linkpath = line.split(ARROW, 1)
                lp = self.prefix / linkpath.lstrip("./")
                try:
                    lp.parent.mkdir(parents=True, exist_ok=True)
                    if lp.is_symlink() or lp.exists():
                        lp.unlink()
                    os.symlink(target, lp)
                    nl += 1
                except OSError:
                    pass
        for sub in ("bin", "libexec", "lib"):
            d = self.prefix / sub
            if d.is_dir():
                for p in d.rglob("*"):
                    if p.is_file() and not p.is_symlink() and _chmod_x(p):
                        nx += 1
        return "extracted files=%d links=%d exec=%d" % (nf, nl, nx)

    # ------------------------------------------------------------ 环境
    def prepare_dirs(self) -> None:
        for d in (self.home, self.tmp, self.work):
            d.mkdir(parents=True, exist_ok=True)

    def env(self) -> dict:
        e = dict(os.environ)
        e.update({
            "PREFIX": str(self.prefix),
            "PATH": str(self.prefix / "bin") + ":" + str(self.prefix / "bin" / "applets"),
            "LD_LIBRARY_PATH": str(self.prefix / "lib"),
            "HOME": str(self.home),
            "TMPDIR": str(self.tmp),
            "TERM": "xterm-256color",
            "LANG": "en_US.UTF-8",
            "SHELL": str(self.bash),
        })
        return e

    # ------------------------------------------------------------ 运行
    def argv(self, args, use_linker=None):
        """构造入口 argv。

        强制要求：**不可**写成 bash -c "bash ..."（内层 bash 是子进程）；
        必须把 bash 本身作为入口进程（直执或经 linker64）。
        """
        if use_linker is None:
            use_linker = self.entry_mode == "linker64"
        base = [str(self.bash)]
        if use_linker and self.is_android:
            return [LINKER64] + base + list(args)
        return base + list(args)

    def run(self, args, timeout: float = 60.0, cwd=None):
        """跑 bash，返回 (rc, stdout, stderr, mode)。

        入口策略：直执优先，被拒（PermissionError）则回退 linker64。
        结果会缓存到 self.entry_mode，后续调用直接走可用的那条路。
        """
        self.prepare_dirs()
        if not self.bash.exists():
            return 127, "", "bash 不存在：先解压 bootstrap", "none"

        attempts = []
        if self.entry_mode == "linker64" and self.is_android:
            attempts = [("linker64", self.argv(args, True))]
        elif self.entry_mode == "direct":
            attempts = [("direct", self.argv(args, False))]
        elif self.is_android:
            attempts = [("direct", self.argv(args, False)),
                        ("linker64", self.argv(args, True))]
        else:
            attempts = [("direct", self.argv(args, False))]

        last = ""
        mode = "none"
        for mode, argv in attempts:
            try:
                r = subprocess.run(argv, capture_output=True, text=True,
                                   timeout=timeout, env=self.env(),
                                   cwd=str(cwd) if cwd else None)
                self.entry_mode = mode
                return r.returncode, r.stdout, r.stderr, mode
            except PermissionError as exc:
                last = "PermissionError: " + str(exc)
                continue
            except FileNotFoundError as exc:
                last = "FileNotFoundError: " + str(exc)
                continue
            except subprocess.TimeoutExpired:
                return 124, "", "超时 %ss 已终止" % timeout, mode
            except OSError as exc:
                last = type(exc).__name__ + ": " + str(exc)
                continue
        self.entry_mode = "none"
        return 127, "", last, "failed"

    # ------------------------------------------------------------ 便捷封装
    def syntax_check(self, script_path: Path):
        """bash -n 校验。返回 (checked, ok, message)。"""
        if not self.ready:
            return False, False, "Termux 运行时不可用，未执行校验"
        rc, out, err, mode = self.run(["-n", str(script_path)], timeout=30)
        if rc == 0:
            return True, True, "bash -n 通过（%s）" % mode
        msg = (err or out or "").strip() or ("bash -n 退出码 %s" % rc)
        return True, False, msg

    def run_script(self, script_path: Path, timeout: float = 60.0, cwd=None):
        """执行脚本。返回 (rc, stdout, stderr, mode)。"""
        if not self.ready:
            return 127, "", "Termux 运行时不可用", "none"
        return self.run([str(script_path)], timeout=timeout, cwd=cwd or self.work)
