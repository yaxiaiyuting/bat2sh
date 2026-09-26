#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语料可对比性分类（W vs L 运行时 oracle 的样本筛选）

**研究基础设施，不是 bat2sh 产品代码。**

分类回答一个问题：**这个 .bat 能不能用「真机 W vs 产物 L」的差分来判定转换正确性？**

分类是**静态**的（只读源文件 + 调用 bat2sh 转换 API 读 report），不执行样本。

    A 纯文件操作   —— 无环境依赖、无网络、无交互；W/L 差异**只能是**转换错误
    B 部分可对比   —— 主体是文件操作，但有少量已知平台差异源（时间/随机/环境读取）
    C 不可对比     —— 交互 / 网络 / 系统状态 / 外部程序 / 不可映射路径 ⇒ 差异无鉴别力

判据来源：
  · `../poc-samples.md` §1（C1–C5）、`../batch-samples.md` §1（C1–C7）
  · `batch-result.md` §4.1（**LF-only 的 .bat 在 cmd 下解析错乱** —— W 侧起点就坏了）
  · `../../../tools/oracle/README.md`（wine oracle 的权威顺序与不可信探针）

用法：
    python3 classify_corpus.py --corpus ~/下载/非常批处理 --out /tmp/classify
    python3 classify_corpus.py --corpus DIR --json        # 只打印汇总
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 标记表

# **硬**标记：命中即 C（差异无鉴别力，无法归因到 bat2sh）
HARD: dict[str, list[str]] = {
    "interactive": [
        r"(?im)^\s*pause\b", r"(?i)\bpause\s*$", r"(?i)\bset\s+/p\b",
        r"(?i)\bchoice\b", r"(?i)\bcmd\s*/k", r"(?i)\bstart\s+/w\b",
        r"(?i)\bstart\s+\"\"", r"(?i)\btimeout\s+/t\b",
        # 需要命令行参数才能工作 —— 采集器不传参，W/L 两侧都拿不到同一输入
        r"(?<![\w%])%(\*|[0-9]|~[0-9a-z]*[0-9])",
    ],
    "network": [
        r"(?i)\bping\b", r"(?i)\bcurl\b", r"(?i)\bwget\b", r"(?i)\bftp\b",
        r"(?i)\btelnet\b", r"(?i)\bnslookup\b", r"(?i)\btracert\b",
        r"(?i)\bnet\s+use\b", r"(?i)\bnet\s+share\b", r"(?i)\bbitsadmin\b",
        r"(?i)\barp\s+-", r"(?i)\broute\s+", r"(?i)\bipconfig\b",
        r"(?i)\bnetsh\b", r"(?i)\bnetstat\b", r"(?i)\brasdial\b",
        r"(?i)\biedkcs32\b", r"(?i)\bwininet\b",
        # UNC / 设备路径：\\server\share、\\?\C:\…
        r"\\\\[?A-Za-z0-9_.]",
    ],
    "system": [
        r"(?i)\breg\s+(add|delete|import|export|copy|save|restore|load|unload|query)\b",
        r"(?i)\bsc\s+(config|start|stop|create|delete|query|failure)\b",
        r"(?i)\bnet\s+(user|localgroup|accounts|start|stop|config)\b",
        r"(?i)\bwmic\b", r"(?i)\btaskkill\b", r"(?i)\btasklist\b",
        r"(?i)\bshutdown\b", r"(?i)\bdiskpart\b", r"(?i)\bbcdedit\b",
        r"(?i)\bschtasks\b", r"(?i)\brunas\b", r"(?i)\bicacls\b",
        r"(?i)\bcacls\b", r"(?i)\btakeown\b", r"(?i)\battrib\b",
        r"(?i)\bsysteminfo\b", r"(?i)\bchkdsk\b", r"(?i)\bdefrag\b",
        r"(?i)\bfsutil\b", r"(?i)\bvssadmin\b", r"(?i)\bpowercfg\b",
        r"(?i)\bdism\b", r"(?i)\bsfc\b", r"(?i)\bgpupdate\b",
        r"(?i)\bassoc\b", r"(?i)\bftype\b", r"(?i)\bwusa\b",
        r"(?i)\bmsiexec\b", r"(?i)\bcipher\b", r"(?i)\bcompact\b",
        r"(?i)\bconvert\s+[A-Za-z]:", r"(?i)\bmountvol\b", r"(?i)\bopenfiles\b",
        r"(?i)\bqwinsta\b", r"(?i)\brwinsta\b", r"(?i)\bsubst\b",
        r"(?i)\bchcp\b", r"(?i)\bwevtutil\b", r"(?i)\btzutil\b",
        r"(?i)\bsecedit\b", r"(?i)\bauditpol\b", r"(?i)\bnetsh\b",
        r"(?i)\bdriverquery\b", r"(?i)\btasklist\b", r"(?i)\bwhoami\b",
        r"(?i)\bhostname\b", r"(?i)\bgetmac\b", r"(?i)\bnet\s+print\b",
        # 实测补漏：这三类在首轮扫描里逃过了（人工复核 A 类时发现）
        r"(?i)\bregsvr32\b", r"(?i)\brundll32\b", r"(?i)\bdebug\b",
        r"(?i)\bpkgmgr\b", r"(?i)\bservermanagercmd\b", r"(?i)\bwscript\b",
        r"(?i)\bschtasks\b", r"(?i)\bcertutil\b", r"(?i)\bexpand\b",
        r"(?i)\bnet\s+localgroup\b", r"(?i)\bgprupdate\b", r"(?i)\bntrights\b",
    ],
    "external": [
        r"(?i)\.exe\b", r"(?i)\.vbs\b", r"(?i)\.ps1\b", r"(?i)\.msi\b",
        r"(?i)\bcscript\b", r"(?i)\bwscript\b", r"(?i)\bmshta\b",
        r"(?i)\bpowershell\b", r"(?i)\bexplorer\b", r"(?i)\bmsg\b",
        r"(?i)\bregedit\b", r"(?i)\bmmc\b", r"(?i)\bcontrol\b",
        r"(?i)\bwmic\b", r"(?i)\bnetcat\b",
    ],
    # 不可映射的绝对路径：bat2sh 不做盘符映射（实测 C:\poc\x → 字面 C:/poc/x）
    "foreign_path": [
        r"(?i)%SystemRoot%", r"(?i)%windir%", r"(?i)%ProgramFiles%",
        r"(?i)%ProgramData%", r"(?i)%APPDATA%", r"(?i)%LOCALAPPDATA%",
        r"(?i)%USERPROFILE%", r"(?i)%HOMEDRIVE%", r"(?i)%TEMP%", r"(?i)%TMP%",
        r"(?i)%ALLUSERSPROFILE%", r"(?i)%COMSPEC%",
        r"(?i)(?<!%)[A-Za-z]:\\",
    ],
    # W 侧起点即坏：LF-only 的 .bat 在 cmd.exe 下解析错乱（batch-result.md §4.1 已实证 rc=255）
    "lf_only": [],
}

# **软**标记：命中即 B（有已知平台差异源，但主体仍是文件操作）
SOFT: dict[str, list[str]] = {
    # 实测补漏：`%date:~13,6%`（子串截取，中文 Windows 下取"周X"）不带闭合的 `%date%`，
    # 首轮扫描漏掉了它 —— 这是语料里最常见的按星期分支写法。
    "clock": [r"(?i)%date%", r"(?i)%date:~[^%]*%", r"(?i)%time%",
              r"(?i)%time:~[^%]*%", r"(?i)%random%", r"(?i)%random:~[^%]*%",
              r"(?i)\bdate\s*/t\b", r"(?i)\btime\s*/t\b",
              r"(?i)%cmdcmdline%", r"(?i)%errorlevel:~"],
    "env_read": [r"(?i)%computername%", r"(?i)%username%", r"(?i)%userdomain%",
                 r"(?i)%os%", r"(?i)%processor", r"(?i)%number_of_processors%",
                 r"(?i)%path%", r"(?i)%cd%", r"(?i)%tmp%", r"(?i)%temp%",
                 r"(?i)\bset\s+[A-Za-z_][A-Za-z0-9_]*\s*$"],
    "console": [r"(?i)\btitle\b", r"(?i)\bcolor\b", r"(?i)\bcls\b",
                r"(?i)\bmode\s+con", r"(?i)\bprompt\b", r"(?i)\bver\b"],
    "rc_range": [r"(?i)\bexit\s+/b\s+(-?\d{3,}|0x[0-9a-f]+)"],
    "parse_risk": [r"(?i)\bfor\s+/f\b", r"(?i)\bdelims=", r"(?i)\btokens=",
                   r"(?i)![A-Za-z_][A-Za-z0-9_]*!", r"(?i)\bsetlocal\s+enabledelayedexpansion"],
    "fs_scan": [r"(?i)\bdir\s+/s\b", r"(?i)\bdir\s+/o", r"(?i)\bsort\b",
                r"(?i)\bfindstr\b", r"(?i)\bfind\b"],
    "wildcard": [r"\*\.\w+"],
}

# 允许的内建命令（用于「只用了内建」判定）
BUILTINS = {
    "echo", "set", "setlocal", "endlocal", "if", "exist", "not", "else",
    "goto", "call", "for", "in", "do", "mkdir", "md", "rmdir", "rd",
    "copy", "move", "ren", "rename", "del", "erase", "type", "dir",
    "cd", "chdir", "pushd", "popd", "shift", "exit", "rem", "find",
    "findstr", "sort", "more", "tree", "cls", "ver", "color", "title",
    "path", "pause", "start", "attrib", "replace", "fc", "comp",
    "verify", "prompt", "date", "time", "choice", "label", "vol",
    "xcopy", "robocopy", "help", "break", "shift", "goto",
}

_REPO = Path(__file__).resolve().parents[3]
_EXTS = (".bat", ".cmd")


def _compile(table: dict[str, list[str]]) -> dict[str, list[re.Pattern]]:
    return {k: [re.compile(p) for p in v] for k, v in table.items()}


HARD_RE = _compile(HARD)
SOFT_RE = _compile(SOFT)


def read_bytes(p: Path) -> bytes:
    return p.read_bytes()


def decode(b: bytes) -> tuple[str, str]:
    """返回 (文本, 编码名)。GBK 优先（语料主体），失败再试 UTF-8。"""
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8", "replace"), "utf-8-bom"
    try:
        return b.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return b.decode("gbk", "replace"), "gbk"


def eol_kind(b: bytes) -> str:
    crlf = b.count(b"\r\n")
    lf = b.count(b"\n") - crlf
    if crlf and lf:
        return "mixed"
    if crlf:
        return "crlf"
    if lf:
        return "lf-only"
    return "no-eol"


def command_tokens(text: str) -> list[str]:
    """粗提取「命令位置」的第一个 token（近似 cmd 语法，不做完整解析）。

    为什么需要它：扩展名清单抓不住 `CSty /chide` 这种**无扩展名的外部程序**
    （实测逃过首轮扫描）。反过来 `.dll`/`.com` 这类扩展名清单又会把
    `del 模块\\Ringxing.dll` 这种**被当数据操作的文件**误判成外部程序。
    命令位置 + 内建白名单是唯一同时避开这两类错误的判据。
    """
    tokens: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("::") or line.startswith("rem ") or line.startswith("REM "):
            continue
        # `for … do <cmd>`：do 之后才是命令
        m = re.search(r"(?i)\bdo\s+(.*)$", line)
        if m and re.match(r"(?i)^\s*for\b", line):
            line = m.group(1)
        line = line.lstrip("@").strip()
        # 按命令分隔符切段（不处理引号内的 & —— 语料里罕见）
        for seg in re.split(r"\|\||&&|[|&()]", line):
            seg = seg.strip().lstrip("@").strip()
            if not seg:
                continue
            seg = re.sub(r"(?i)^(call|start)\s+", "", seg).strip()
            seg = re.sub(r'^"[^"]*"\s+', "", seg).strip()  # start "title" cmd
            if not seg:
                continue
            tok = seg.split()[0]
            # 重定向可以紧贴命令无空格：`cd.>a.txt` / `echo x>>log`
            tok = re.split(r"[<>]", tok)[0]
            if not tok:
                continue
            if tok.startswith(":") or tok.startswith("%") or tok.startswith("!"):
                continue
            tokens.append(tok)
    return tokens


def unknown_external(text: str) -> list[str]:
    """命令位置出现、但不在内建白名单里的 token（= 需要外部程序/同目录其它脚本）。"""
    out: set[str] = set()
    for tok in command_tokens(text):
        base = tok.strip('"').strip()
        if not base or base.startswith(":"):
            continue
        # 去掉路径前缀，只看程序名
        name = re.split(r"[\\/]", base)[-1]
        stem = name[:-4] if name.lower().endswith((".exe", ".com", ".bat", ".cmd")) else name
        # `cd.>a.txt` 是"建空文件"惯用法 —— `cd.` 等价于 `cd`
        if stem.lower() not in BUILTINS and stem.endswith(".") and stem[:-1].lower() in BUILTINS:
            stem = stem[:-1]
        if stem.lower() in BUILTINS:
            continue
        if re.fullmatch(r"[%!].*[%!]", stem):  # 变量当命令名
            continue
        out.add(base)
    return sorted(out)


def scan_markers(text: str) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    hard: dict[str, list[str]] = {}
    soft: dict[str, list[str]] = {}
    for cat, pats in HARD_RE.items():
        hits = sorted({p.pattern for p in pats if p.search(text)})
        if hits:
            hard[cat] = hits
    for cat, pats in SOFT_RE.items():
        hits = sorted({p.pattern for p in pats if p.search(text)})
        if hits:
            soft[cat] = hits
    ext = unknown_external(text)
    if ext:
        hard["external"] = sorted(set(hard.get("external", [])) | {f"cmd-position: {', '.join(ext)}"})
    return hard, soft


def convert_report(text: str) -> dict:
    """调用 bat2sh 转换 API，读 report（**不写任何文件**）。"""
    if str(_REPO / "python") not in sys.path:
        sys.path.insert(0, str(_REPO / "python"))
    try:
        from bat2sh.core.engine import convert_text
        from bat2sh.core.settings import ConvertSettings
        from bat2sh.core.types import SourceKind
    except Exception as exc:  # pragma: no cover
        return {"error": f"import 失败: {exc}"}
    try:
        script, report = convert_text(
            text, SourceKind.BATCH, ConvertSettings(bash_check=False), "probe.bat"
        )
    except Exception as exc:
        return {"error": f"convert 异常: {exc}"}
    # bat2sh 产物**恒定**带一行表头注释 `# 带有 # TODO 标记的行无法自动转换…`，
    # 它不是"本样本有未转换语法"的证据 —— 不计入 todo_count（否则 151/151 全带 todo）。
    todos = [
        ln.strip()
        for ln in script.splitlines()
        if "# TODO" in ln and "无法自动转换" not in ln
    ]
    return {
        "todo_count": len(todos),
        "syntax_ok": True,
        "script_lines": len(script.splitlines()),
    }


def classify(path: Path) -> dict:
    raw = read_bytes(path)
    text, enc = decode(raw)
    eol = eol_kind(raw)
    hard, soft = scan_markers(text)
    if eol in ("lf-only",):
        hard.setdefault("lf_only", []).append("no CRLF in file")
    if eol == "mixed":
        soft.setdefault("eol_mixed", []).append("mixed CRLF/LF")

    rep = convert_report(text)

    if hard:
        cls = "C"
    elif soft:
        cls = "B"
    else:
        cls = "A"

    return {
        "path": str(path),
        "name": path.name,
        "size": len(raw),
        "encoding": enc,
        "eol": eol,
        "class": cls,
        "hard": hard,
        "soft": soft,
        "convert": rep,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="语料可对比性分类")
    ap.add_argument("--corpus", required=True, help="语料根目录（递归 *.bat/*.cmd）")
    ap.add_argument("--out", help="输出目录（写 classify.json）")
    ap.add_argument("--json", action="store_true", help="只打印汇总 JSON")
    args = ap.parse_args()

    root = Path(os.path.expanduser(args.corpus)).resolve()
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _EXTS)
    if not files:
        print(f"未找到 *.bat/*.cmd: {root}", file=sys.stderr)
        return 1

    rows = [classify(p) for p in files]
    summary = {
        "corpus": str(root),
        "files": len(rows),
        "class": {c: sum(1 for r in rows if r["class"] == c) for c in "ABC"},
        "encoding": {},
        "eol": {},
        "hard_categories": {},
        "soft_categories": {},
        "convert_errors": sum(1 for r in rows if "error" in r["convert"]),
        "todo_files": sum(1 for r in rows if r["convert"].get("todo_count", 0) > 0),
    }
    for key, bucket in (("encoding", "encoding"), ("eol", "eol")):
        for r in rows:
            summary[bucket][r[key]] = summary[bucket].get(r[key], 0) + 1
    for r in rows:
        for cat in r["hard"]:
            summary["hard_categories"][cat] = summary["hard_categories"].get(cat, 0) + 1
        for cat in r["soft"]:
            summary["soft_categories"][cat] = summary["soft_categories"].get(cat, 0) + 1

    out = {"summary": summary, "rows": rows}
    if args.out:
        od = Path(os.path.expanduser(args.out))
        od.mkdir(parents=True, exist_ok=True)
        (od / "classify.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("\n--- A 类 ---")
        for r in rows:
            if r["class"] == "A":
                print(f"  {r['name']}  [{r['encoding']}/{r['eol']}] todo={r['convert'].get('todo_count')}")
        print("\n--- B 类 ---")
        for r in rows:
            if r["class"] == "B":
                print(f"  {r['name']}  soft={list(r['soft'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
