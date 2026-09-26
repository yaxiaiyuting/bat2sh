#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W vs L 运行时对比器（bat2sh 转换正确性 oracle）

    W = 真机 cmd.exe 执行原始 .bat      →  tools/collect.py
    L = 产物在 bwrap 沙箱执行            →  tools/collect_linux.py

设计见 `../oracle-design.md`。**核心原则：规则不是一股脑全上，而是先不加、不够再加、
每一加都留痕。** 这样"差异被哪条规则吃掉了"永远可见 —— 这是对抗"假一致"的唯一办法。

    python3 tools/compare.py --w W.json --l L.json [--source X.bat] [--report out.json]

分类：
    一致      所有通道在**严格档**（仅 N1/N5/N7）下即相等
    可归因    需要 D-list 内的规则才能相等，且所需规则逐条有据
    不可归因  施加全部已定义规则后仍不等 ⇒ **报告（潜在缺陷）**

退出码：0 = 一致/可归因；1 = 不可归因；2 = 用法/输入错误
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# 规则表（编号与 oracle-design.md §5 一一对应）
# --------------------------------------------------------------------------

STRICT_RULES = {"N1", "N5", "N6", "N7"}    # 严格档：表示层差异
ATTRIBUTED_RULES = {"N2", "N3", "N8", "N9", "N12", "N10", "N11"}

# ⚠️ **设计修正 A1（相对 oracle-design.md §5 的偏离，必须披露）**
# 原设计把 N6（路径分隔符）放在**归因档**。实测发现：W 的清单键恒用 `\`、
# L 恒用 `/`，于是**任何写文件的样本都不可能判"一致"** —— "一致"类变成空集，
# 报告全部退化为"可归因"，判别力反而下降。
# 理由修正：`\` vs `/` 与 N1（CRLF vs LF）**同性质**（平台表示层约定，
# 不改变"指向哪个文件"这一行为事实），故升入严格档。
# 保留的判别力：N6 **只对 `<WORK>` 前缀内的路径生效**，工作根之外的差异
# （如 `C:\iso-probe\x` vs `<WORK>/C:/iso-probe/x`）**仍然暴露**（见 norm_path）。

RULE_DESC = {
    "N1": "行尾归一 CRLF→LF",
    "N2": "剥离 ANSI 转义",
    "N3": "行尾空白 rstrip",
    "N4": "丢弃空行（默认关闭）",
    "N5": "工作根映射 → <WORK>",
    "N6": "路径分隔符统一",
    "N7": "文本编码解码（W=CP936 / L=UTF-8）",
    "N8": "时间戳形状化（值盲、形敏感）",
    "N9": "随机数归一（默认关闭）",
    "N10": "文件内容：行尾归一后哈希",
    "N11": "文件内容：CP936+行尾归一后哈希",
    "N12": "退出码宽度（32 位 vs 8 位）",
}

# 规则 → 已知差异条目（D-list）。空 = 纯表示层，不对应 D 条目。
RULE_TO_D = {
    "N2": [], "N3": ["D10"], "N6": ["D1", "D8"], "N8": ["D7"], "N9": [],
    "N10": ["D2"], "N11": ["D3"], "N12": ["D6"], "N1": ["D2"],
}

# 规则"掩盖了什么" —— 报告必须显式写出，否则规则变成静默的抹平
RULE_MASKS = {
    "N1": "CRLF vs LF（表示层）",
    "N2": "ANSI 颜色转义的存在与否",
    "N3": "行尾空格差异（可能掩盖定宽/填充缺陷）",
    "N6": "路径分隔符差异",
    "N8": "时间**值**（保留格式形状 ⇒ 格式错误仍会被发现）",
    "N9": "随机**值**（保留其余结构）",
    "N10": "文本产物行尾 CRLF vs LF",
    "N11": "产物**编码** CP936 vs UTF-8（可能掩盖编码缺陷）",
    "N12": "退出码宽度",
}

D_DESC = {
    "D1": "路径分隔符", "D2": "行尾", "D3": "控制台代码页 vs UTF-8",
    "D4": "目录列举顺序", "D5": "set -euo pipefail 早退 vs cmd 继续",
    "D6": "退出码宽度", "D7": "时钟（W 固定 / L 宿主实时）",
    "D8": "%~dp0 结尾分隔符", "D9": "自读产物", "D10": "目录列举格式",
    "D11": "不存在的外部命令", "D12": "大小写敏感性", "D13": "不存在的设备/伪文件",
    "D14": "ping 作延时惯用法",
}

WORK = "<WORK>"
W_WORKROOT = r"C:\poc\samples"
L_WORKROOT = "samples"          # collect_linux.py --run-name 的默认值

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_TS_RES = [
    (re.compile(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?"), "<DATE>"),
    (re.compile(r"\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?"), "<TIME>"),
    (re.compile(r"\d{1,2}:\d{2}"), "<TIME>"),
    (re.compile(r"周[一二三四五六日天]"), "<DOW>"),
    (re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b"), "<DOW>"),
]
_RAND_RE = re.compile(r"\b\d{1,5}\b")


# --------------------------------------------------------------------------
# 归一化原语
# --------------------------------------------------------------------------


def norm_text(text: str, rules: set[str], *, side: str, work_root: str = "") -> str:
    """文本通道归一化。N7 在采集期已完成（W 按 CP936、L 按 UTF-8 解码为 Unicode）。

    ⚠️ N5 也必须作用于**文本**：L 的 stderr 会带**每次运行都不同的**沙箱绝对路径
    （实测 `cat: '/tmp/bat2sh-oracle/copy-1790434237842/run/work\\c.txt': …`）。
    不映射它，任何含路径的错误信息都会**恒定假报不一致**。
    """
    t = text
    if "N5" in rules and work_root:
        t = re.sub(re.escape(work_root), WORK, t, flags=re.IGNORECASE)
    if "N1" in rules:
        t = t.replace("\r\n", "\n").replace("\r", "\n")
    if "N2" in rules:
        t = _ANSI_RE.sub("", t)
    if "N8" in rules:
        for rx, rep in _TS_RES:
            t = rx.sub(rep, t)
    if "N9" in rules:
        t = _RAND_RE.sub("<N>", t)
    if "N3" in rules:
        t = "\n".join(ln.rstrip() for ln in t.split("\n"))
    return t


def norm_path(p: str, rules: set[str], *, side: str) -> str:
    """路径归一化。

    N5 **只映射 `<WORK>` 前缀**（设计 §5 N5）：落在工作根之外的写入**故意不映射**，
    让"写错位置"暴露出来。W 的盘符绝对路径（`C:\\iso-probe\\x`）因而**不会**与
    L 的 cwd 相对路径（`<WORK>/C:/iso-probe/x`）相等 —— 这是**有意保留**的差异。
    """
    q = p
    if side == "W":
        # W 清单键是 `C:\poc\samples\work\a.txt`（绝对）；剥掉工作根前缀
        if q.lower().startswith(W_WORKROOT.lower()):
            rest = q[len(W_WORKROOT):].lstrip("\\/")
            q = f"{WORK}/{rest}" if rest else WORK
        if "N6" in rules:
            q = q.replace("\\", "/")
    else:
        # L 清单键本就是相对工作根的 POSIX 路径
        q = f"{WORK}/{q}"
        if "N6" in rules:
            q = q.replace("\\", "/")
    return q


def work_root_of(fp: dict, *, side: str) -> str:
    """取该侧的工作根**绝对路径字面量**（用于文本通道里的路径映射）。"""
    if side == "W":
        return fp.get("execution_workdir") or W_WORKROOT
    rd = (fp.get("rollback") or {}).get("run_dir") or ""
    return rd


def cmp_text(w: str, l: str, rules: set[str], *, wroot="", lroot="") -> bool:
    return (norm_text(w, rules, side="W", work_root=wroot)
            == norm_text(l, rules, side="L", work_root=lroot))


def lines_multiset(t: str) -> list[str]:
    return sorted(ln for ln in t.replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln)


# --------------------------------------------------------------------------
# 指纹投影
# --------------------------------------------------------------------------


def load(p: str) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def fs_sets(fp: dict, rules: set[str], *, side: str) -> dict:
    fs = fp.get("filesystem", {})
    g = lambda key: sorted({norm_path(x, rules, side=side) for x in fs.get(key, [])})  # noqa: E731
    return {
        "created": g("created"),
        "modified": g("modified"),
        "deleted": g("deleted"),
        "created_dirs": g("created_dirs"),
        "deleted_dirs": g("deleted_dirs"),
    }


def content_map(fp: dict, rules: set[str], *, side: str) -> dict:
    fs = fp.get("filesystem", {})
    return {norm_path(k, rules, side=side): v
            for k, v in (fs.get("after_manifest") or {}).items()}


# --------------------------------------------------------------------------
# 通道比较
# --------------------------------------------------------------------------


def known_paths(fp: dict, rules: set[str], *, side: str) -> set[str]:
    """采集器自己放进沙箱的文件（W: 上传的 .bat；L: 转换产物）。

    **必须从内容比较里排除**：两者按构造就不同（一个是 bat，一个是 bash 产物），
    比较它只会产生恒定噪声（对应已知差异 D9 的邻域）。
    """
    return {norm_path(a["path"], rules, side=side)
            for a in (fp.get("filesystem", {}).get("known_artifacts") or [])}


def cmp_fs_content(W: dict, L: dict, rules: set[str]) -> dict:
    """文件内容比较：按 N10 → N11 逐级放宽，**每一级留痕**。"""
    wm = content_map(W, rules, side="W")
    lm = content_map(L, rules, side="L")
    skip = known_paths(W, rules, side="W") | known_paths(L, rules, side="L")
    wm = {k: v for k, v in wm.items() if k not in skip}
    lm = {k: v for k, v in lm.items() if k not in skip}
    common = sorted(set(wm) & set(lm))
    only_w = sorted(set(wm) - set(lm))
    only_l = sorted(set(lm) - set(wm))

    used: set[str] = set()
    diffs: list[dict] = []
    for p in common:
        wh = wm[p].get("Hash")
        lh = lm[p].get("Hash")
        if wh is None or lh is None:
            continue
        if wh == lh:
            continue                                    # 逐字节相同
        if wh == lm[p].get("hash_lf_to_crlf"):
            used.add("N10")                             # 仅行尾不同
            continue
        if wh == lm[p].get("hash_cp936_crlf"):
            used.add("N11")                             # 编码 + 行尾不同
            continue
        diffs.append({"path": p, "w_hash": wh, "l_hash": lh,
                      "w_len": wm[p].get("Length"), "l_len": lm[p].get("Length")})
    return {"equal": not diffs and not only_w and not only_l,
            "rules_used": used, "differs": diffs,
            "only_in_w": only_w, "only_in_l": only_l, "compared": len(common)}


# --------------------------------------------------------------------------
# 主判定
# --------------------------------------------------------------------------


def compare(W: dict, L: dict, *, source_text: str | None = None,
            enable_n8: bool | None = None, enable_n9: bool | None = None) -> dict:
    # N8/N9 只在**源样本确实读时间/随机数**时才可用（证据驱动，不是默认放宽）
    if enable_n8 is None:
        enable_n8 = bool(source_text and re.search(r"(?i)%date%|%time%|%date:~|%time:~", source_text))
    if enable_n9 is None:
        enable_n9 = bool(source_text and re.search(r"(?i)%random%", source_text))

    attr = set(ATTRIBUTED_RULES)
    if not enable_n8:
        attr.discard("N8")
    if not enable_n9:
        attr.discard("N9")

    wroot, lroot = work_root_of(W, side="W"), work_root_of(L, side="L")
    channels: dict[str, dict] = {}
    unattributed: list[dict] = []

    # ---- rc ----
    wrc, lrc = W["execution"]["exit_code"], L["execution"]["exit_code"]
    rc_strict = (wrc == lrc)
    rc_rules: set[str] = set()
    if not rc_strict:
        if isinstance(wrc, int) and isinstance(lrc, int) and not (0 <= wrc <= 255) \
                and (wrc & 0xFF) == (lrc & 0xFF):
            rc_rules.add("N12")
    channels["rc"] = {"strict": rc_strict, "attributed": rc_strict or bool(rc_rules),
                      "w": wrc, "l": lrc, "rules": sorted(rc_rules)}
    if not channels["rc"]["attributed"]:
        unattributed.append({"channel": "rc", "w": wrc, "l": lrc})

    # ---- text 通道 ----
    for ch in ("stdout", "stderr"):
        wtx, ltx = W[ch]["text"], L[ch]["text"]
        st = cmp_text(wtx, ltx, STRICT_RULES, wroot=wroot, lroot=lroot)
        at = st or cmp_text(wtx, ltx, STRICT_RULES | attr, wroot=wroot, lroot=lroot)
        rules: set[str] = set()
        if not st and at:
            for r in sorted(attr):
                if cmp_text(wtx, ltx, STRICT_RULES | rules | {r}, wroot=wroot, lroot=lroot):
                    rules.add(r)
        full = STRICT_RULES | attr
        entry = {"strict": st, "attributed": at, "rules": sorted(rules),
                 "w_repr": repr(wtx)[:400], "l_repr": repr(ltx)[:400],
                 # 归一化后的视图：**光看原始值会误以为映射没生效**
                 "w_norm": repr(norm_text(wtx, full, side="W", work_root=wroot))[:400],
                 "l_norm": repr(norm_text(ltx, full, side="L", work_root=lroot))[:400]}
        # 顺序子分类（D4）：严格不等、归因也不等，但**多重集相等**
        if not at and lines_multiset(wtx) == lines_multiset(ltx):
            entry["order_only"] = True
            entry["d_items"] = ["D4"]
            entry["note"] = "多重集相等但顺序不同 ⇒ 疑似目录列举排序（D4），**需人工确认**"
            at = True
        if not at:
            unattributed.append({"channel": ch, "w": repr(wtx)[:400], "l": repr(ltx)[:400]})
        channels[ch] = entry

    # ---- fs 名称集 ----
    name_rules: set[str] = set()
    ws, ls = fs_sets(W, STRICT_RULES, side="W"), fs_sets(L, STRICT_RULES, side="L")
    names_strict = ws == ls
    names_attr = names_strict
    if not names_strict:
        ws6, ls6 = fs_sets(W, STRICT_RULES | {"N6"}, side="W"), fs_sets(L, STRICT_RULES | {"N6"}, side="L")
        if ws6 == ls6:
            name_rules.add("N6")
            names_attr = True
            ws, ls = ws6, ls6
    channels["fs_names"] = {"strict": names_strict, "attributed": names_attr,
                            "rules": sorted(name_rules),
                            "w": ws, "l": ls}
    if not names_attr:
        unattributed.append({"channel": "fs_names",
                             "only_in_w": sorted({x for k in ws for x in ws[k]} -
                                                 {x for k in ls for x in ls[k]}),
                             "only_in_l": sorted({x for k in ls for x in ls[k]} -
                                                 {x for k in ws for x in ws[k]})})

    # ---- fs 内容 ----
    cr = cmp_fs_content(W, L, STRICT_RULES)
    channels["fs_content"] = {
        "strict": cr["equal"] and not cr["rules_used"],
        "attributed": cr["equal"],
        "rules": sorted(cr["rules_used"]),
        "compared": cr["compared"], "differs": cr["differs"],
        "only_in_w": cr["only_in_w"], "only_in_l": cr["only_in_l"],
    }
    if not cr["equal"]:
        unattributed.append({"channel": "fs_content", "differs": cr["differs"],
                             "only_in_w": cr["only_in_w"], "only_in_l": cr["only_in_l"]})

    # ---- 分类 ----
    all_strict = all(c["strict"] for c in channels.values())
    all_attr = all(c["attributed"] for c in channels.values())
    if all_strict:
        cls = "一致"
    elif all_attr:
        cls = "可归因"
    else:
        cls = "不可归因"

    applied = []
    for ch, c in channels.items():
        for r in c.get("rules", []):
            applied.append({"rule": r, "channel": ch, "desc": RULE_DESC.get(r, r),
                            "masked": RULE_MASKS.get(r, ""),
                            "d_items": RULE_TO_D.get(r, [])})
    # 去重（同规则可能命中多个通道）
    seen, applied_dedup = set(), []
    for a in applied:
        k = (a["rule"], a["channel"])
        if k not in seen:
            seen.add(k)
            applied_dedup.append(a)

    d_items = sorted({d for a in applied_dedup for d in a["d_items"]}
                     | {d for c in channels.values() for d in c.get("d_items", [])})

    return {
        "sample": W.get("script", {}).get("name"),
        "w_head": W.get("harness", {}).get("git_head", "")[:8],
        "l_head": L.get("harness", {}).get("git_head", "")[:8],
        "class": cls,
        "channels": channels,
        "normalization_applied": applied_dedup,
        "d_items": d_items,
        "d_desc": {d: D_DESC.get(d, "") for d in d_items},
        "unattributed": unattributed,
        "n8_eligible": bool(enable_n8), "n9_eligible": bool(enable_n9),
    }


# --------------------------------------------------------------------------


def render(rep: dict) -> str:
    out = []
    mark = {"一致": "✅", "可归因": "🟡", "不可归因": "❌"}[rep["class"]]
    out.append(f"{mark} 分类 = {rep['class']}   （样本 {rep['sample']}）")
    out.append("")
    out.append(f"  {'通道':<12} {'严格':<6} {'归因':<6} 规则")
    for ch, c in rep["channels"].items():
        out.append(f"  {ch:<12} {str(c['strict']):<6} {str(c['attributed']):<6} "
                   f"{','.join(c.get('rules', [])) or '-'}")
    if rep["normalization_applied"]:
        out.append("")
        out.append("  归一化留痕（**每条都写明它掩盖了什么**）：")
        for a in rep["normalization_applied"]:
            out.append(f"    {a['rule']} @{a['channel']}: {a['desc']}")
            if a["masked"]:
                out.append(f"        掩盖: {a['masked']}")
            if a["d_items"]:
                out.append(f"        → {', '.join(a['d_items'])}")
    if rep["d_items"]:
        out.append("")
        out.append("  已知差异条目: " + "; ".join(f"{d}={rep['d_desc'][d]}" for d in rep["d_items"]))
    if rep["unattributed"]:
        out.append("")
        out.append("  ❌ **不可归因差异**（潜在缺陷）：")
        for u in rep["unattributed"]:
            out.append(f"    [{u['channel']}] " + json.dumps(
                {k: v for k, v in u.items() if k != "channel"}, ensure_ascii=False)[:600])
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="W vs L 运行时对比")
    ap.add_argument("--w", required=True)
    ap.add_argument("--l", required=True)
    ap.add_argument("--source", help="原始 .bat（用于判断 N8/N9 是否可用）")
    ap.add_argument("--report", help="把 JSON 报告写到该路径")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--enable-n8", action="store_true")
    ap.add_argument("--enable-n9", action="store_true")
    args = ap.parse_args()

    for p in (args.w, args.l):
        if not Path(p).is_file():
            print(f"指纹不存在: {p}", file=sys.stderr)
            return 2
    src = Path(args.source).read_text(encoding="utf-8", errors="replace") if args.source else None

    rep = compare(load(args.w), load(args.l), source_text=src,
                  enable_n8=True if args.enable_n8 else None,
                  enable_n9=True if args.enable_n9 else None)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else render(rep))
    return 0 if rep["class"] in ("一致", "可归因") else 1


if __name__ == "__main__":
    raise SystemExit(main())
