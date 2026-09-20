"""只读近似高亮：把 bash 源码切成 Flet TextSpan。

定位（任务书 4.6）：只求一眼看出结构，不追求 QSyntaxHighlighter 等价。
着色维度：注释 / 字符串 / 关键字 / 常用命令 / 变量 / 数字。
"""

from __future__ import annotations

import flet as ft

BACKSLASH = chr(92)
LBRACE = chr(123)
RBRACE = chr(125)

KEYWORDS = frozenset((
    "if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done",
    "case", "esac", "in", "function", "select", "time", "return", "break",
    "continue", "local", "export", "declare", "readonly", "set", "unset",
    "shift", "exit", "source", "trap", "eval", "exec", "alias", "unalias",
))

BUILTINS = frozenset((
    "echo", "printf", "read", "cd", "pwd", "test", "true", "false", "let",
    "type", "command", "builtin", "getopts", "wait", "jobs", "kill", "umask",
    "ulimit", "hash", "help", "history", "dirs", "pushd", "popd",
    "ls", "cat", "cp", "mv", "rm", "mkdir", "rmdir", "touch", "chmod", "chown",
    "find", "xargs", "sort", "uniq", "wc", "tr", "cut", "date", "sleep", "seq",
    "basename", "dirname", "realpath", "which", "env", "id", "uname", "df", "du",
    "head", "tail", "grep", "sed", "awk", "tar", "gzip", "curl", "wget", "tee",
    "mktemp", "stat", "readlink", "ln", "sync", "yes", "expr",
))

COLORS = {
    "plain": ft.Colors.GREY_200,
    "comment": ft.Colors.GREY_500,
    "string": ft.Colors.GREEN_300,
    "keyword": ft.Colors.PURPLE_200,
    "builtin": ft.Colors.BLUE_200,
    "variable": ft.Colors.ORANGE_200,
    "number": ft.Colors.TEAL_200,
}

MAX_LINES = 1500
MAX_SPANS = 8000


def _scan(line: str) -> list[tuple[str, str]]:
    """把一行切成 [(文本, 类别)]。类别见 COLORS。"""
    parts: list[tuple[str, str]] = []
    plain: list[str] = []
    i = 0
    n = len(line)

    def flush() -> None:
        if plain:
            parts.append(("".join(plain), "plain"))
            plain.clear()

    while i < n:
        ch = line[i]

        # 注释：只在词首（行首或前面是空白 / 分隔符）才算
        if ch == "#" and (i == 0 or line[i - 1] in " " + chr(9) + ";|&("):
            flush()
            parts.append((line[i:], "comment"))
            break

        # 引号字符串
        if ch in ("'", '"'):
            quote = ch
            flush()
            seg = [ch]
            j = i + 1
            while j < n:
                c = line[j]
                if c == BACKSLASH and quote == '"':
                    seg.append(line[j:j + 2])
                    j += 2
                    continue
                seg.append(c)
                j += 1
                if c == quote:
                    break
            parts.append(("".join(seg), "string"))
            i = j
            continue

        # 变量：$name 或 $ 加花括号的形式
        if ch == "$":
            j = i + 1
            if j < n and line[j] == LBRACE:
                k = line.find(RBRACE, j)
                end = (k + 1) if k >= 0 else n
                flush()
                parts.append((line[i:end], "variable"))
                i = end
                continue
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            if j > i + 1:
                flush()
                parts.append((line[i:j], "variable"))
                i = j
                continue
            plain.append(ch)
            i += 1
            continue

        # 数字
        if ch.isdigit() and (i == 0 or not (line[i - 1].isalnum() or line[i - 1] == "_")):
            j = i
            while j < n and (line[j].isdigit() or line[j] == "."):
                j += 1
            flush()
            parts.append((line[i:j], "number"))
            i = j
            continue

        # 词
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] in "_-."):
                j += 1
            word = line[i:j]
            if word in KEYWORDS:
                flush()
                parts.append((word, "keyword"))
            elif word in BUILTINS:
                flush()
                parts.append((word, "builtin"))
            else:
                plain.append(word)
            i = j
            continue

        plain.append(ch)
        i += 1

    flush()
    return parts


def build_spans(text: str) -> tuple[list[ft.TextSpan], bool]:
    """把整段 bash 源码变成 spans。返回 (spans, 是否被截断)。"""
    lines = text.splitlines()
    truncated = False
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        truncated = True

    spans: list[ft.TextSpan] = []
    for idx, line in enumerate(lines):
        if idx:
            spans.append(ft.TextSpan(text=chr(10)))
        for chunk, kind in _scan(line):
            if kind == "plain":
                spans.append(ft.TextSpan(text=chunk))
            else:
                spans.append(ft.TextSpan(
                    text=chunk, style=ft.TextStyle(color=COLORS[kind])))
        if len(spans) > MAX_SPANS:
            truncated = True
            break
    return spans, truncated
