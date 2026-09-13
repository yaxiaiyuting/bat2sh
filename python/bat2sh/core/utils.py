"""通用工具：标识符清洗、引号、重定向切分、路径分隔符转换。"""

from __future__ import annotations

import re


def sanitize_identifier(name: str) -> str:
    """把任意名字转换为合法的 bash 标识符。"""
    ident = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if not ident:
        ident = "_"
    if ident[0].isdigit():
        ident = "_" + ident
    return ident


def strip_outer_quotes(text: str) -> tuple[str, str]:
    """去掉最外层成对的引号，返回 (内容, 引号字符或空串)。"""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1], text[0]
    return text, ""


def dq(text: str) -> str:
    """用双引号包裹（允许变量展开），转义内部的双引号、反斜杠和反引号。"""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
    return '"' + escaped + '"'


def sq(text: str) -> str:
    """用单引号包裹（禁止展开）。"""
    return "'" + text.replace("'", "'\\''") + "'"


def is_fully_quoted(text: str) -> bool:
    text = text.strip()
    return len(text) >= 2 and text[0] == '"' and text[-1] == '"'


def find_matching(text: str, open_ch: str, close_ch: str, start: int = 0) -> int:
    """返回与 start 处 open_ch 配对的 close_ch 下标；找不到返回 -1。

    引号内的括号不参与配对。
    """
    depth = 0
    quote = ""
    i = start
    seen = False
    while i < len(text):
        c = text[i]
        if quote:
            if c == quote:
                quote = ""
            i += 1
            continue
        if c in "\"'":
            quote = c
        elif c == open_ch:
            depth += 1
            seen = True
        elif c == close_ch:
            depth -= 1
            if seen and depth == 0:
                return i
        i += 1
    return -1


def split_top_level(text: str, sep: str) -> list[str]:
    """按顶层分隔符切分（忽略引号、括号、花括号内的分隔符）。"""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    quote = ""
    for c in text:
        if quote:
            buf.append(c)
            if c == quote:
                quote = ""
            continue
        if c in "\"'":
            quote = c
            buf.append(c)
            continue
        if c in "([{":
            depth += 1
            buf.append(c)
            continue
        if c in ")]}":
            depth = max(0, depth - 1)
            buf.append(c)
            continue
        if c == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(c)
    parts.append("".join(buf))
    return parts


def tokenize_args(text: str) -> list[str]:
    """按空白切分参数，保留引号与 $(...) 内的空白。"""
    tokens: list[str] = []
    buf: list[str] = []
    quote = ""
    dollar_depth = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = ""
            i += 1
            continue
        if c in "\"'":
            quote = c
            buf.append(c)
            i += 1
            continue
        if c == "$" and i + 1 < n and text[i + 1] == "(":
            dollar_depth += 1
            buf.append("$(")
            i += 2
            continue
        if c == ")" and dollar_depth > 0:
            dollar_depth -= 1
            buf.append(c)
            i += 1
            continue
        if c.isspace() and dollar_depth == 0:
            if buf:
                tokens.append("".join(buf))
                buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    if buf:
        tokens.append("".join(buf))
    return tokens


def convert_backslashes(text: str) -> str:
    """把 Windows 路径中的反斜杠替换为正斜杠。

    仅当反斜杠后面是路径常见字符时才替换，避免破坏转义序列。
    """
    result: list[str] = []
    quote = ""
    i = 0
    n = len(text)
    path_next = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.~%:*?-_")
    while i < n:
        c = text[i]
        if quote:
            if c == quote:
                quote = ""
                result.append(c)
                i += 1
                continue
            if c == "\\":
                nxt = text[i + 1] if i + 1 < n else ""
                if nxt == quote:
                    # Windows 目录写法 "C:\dir\"：反斜杠紧邻引号，转换为 /
                    result.append("/")
                elif nxt and nxt in path_next:
                    result.append("/")
                else:
                    result.append(c)
                i += 1
                continue
            result.append(c)
            i += 1
            continue
        if c in "\"'":
            quote = c
            result.append(c)
            i += 1
            continue
        if c == "\\":
            nxt = text[i + 1] if i + 1 < n else ""
            if not nxt:
                result.append("/")
            elif nxt in path_next:
                result.append("/")
            else:
                result.append(c)
            i += 1
            continue
        result.append(c)
        i += 1
    return "".join(result)


_REDIRECT_TARGET = re.compile(r'\s*("(?:[^"\\]|\\.)*"|\'[^\']*\'|[^\s|&<>]+)')


def split_redirects(text: str) -> tuple[str, list[tuple[str, str]]]:
    """切分命令和重定向，返回 (命令部分, [(操作符, 目标)])。

    操作符形如 >、>>、<、2>、2>>、2>&1（此时目标为 &1）。
    """
    body: list[str] = []
    redirs: list[tuple[str, str]] = []
    i = 0
    n = len(text)
    quote = ""
    while i < n:
        c = text[i]
        if quote:
            body.append(c)
            if c == quote:
                quote = ""
            i += 1
            continue
        if c in "\"'":
            quote = c
            body.append(c)
            i += 1
            continue
        op = ""
        rest_index = i
        if c.isdigit() and i + 1 < n and text[i + 1] in "><":
            op = c + text[i + 1]
            if i + 2 < n and text[i + 2] == ">":
                op += ">"
            rest_index = i + len(op)
        elif c in "<>":
            op = c
            if c == ">" and i + 1 < n and text[i + 1] == ">":
                op = ">>"
            rest_index = i + len(op)
        if op:
            remainder = text[rest_index:]
            if remainder.lstrip().startswith("&"):
                stripped = remainder.lstrip()
                m = re.match(r"&(\d+|-)", stripped)
                if m:
                    target = "&" + m.group(1)
                    redirs.append((op, target))
                    consumed = len(remainder) - len(stripped) + m.end()
                    i = rest_index + consumed
                    continue
            m = _REDIRECT_TARGET.match(remainder)
            if m:
                target = m.group(1)
                redirs.append((op, target))
                i = rest_index + m.end()
                continue
            redirs.append((op, ""))
            i = rest_index
            continue
        body.append(c)
        i += 1
    return "".join(body).strip(), redirs


def simple_glob_to_regex(pattern: str) -> str:
    """把简单的 * ? 通配符转换为正则（用于 -like）。"""
    out = []
    for c in pattern:
        if c == "*":
            out.append(".*")
        elif c == "?":
            out.append(".")
        else:
            out.append(re.escape(c))
    return "".join(out)


def has_set_e(strict: bool) -> bool:
    """转换后的脚本是否会启用 ``set -e``。"""
    return bool(strict)


def guard_read(command: str, strict: bool) -> str:
    """``set -e`` 下的 ``read`` 遇到 EOF/Ctrl+D 会返回非零并终止脚本，补 ``|| true``。"""
    if not has_set_e(strict):
        return command
    if command.rstrip().endswith("|| true"):
        return command
    return command + " || true"


_NAMED_ARG_RE = re.compile(r"^-[A-Za-z][\w-]*(?::.*)?$")


def is_named_arg(token: str) -> bool:
    """判断 token 是否形如 PowerShell 命名参数 ``-Name`` / ``-Name:value``。"""
    return bool(_NAMED_ARG_RE.match(token))


def resolve_named_args(args: list[str], param_names: list[str]) -> list[str] | None:
    """把命名参数调用按 ``param_names`` 的顺序重排为位置参数。

    未提供的中间参数用空字符串占位，末尾未提供的参数直接省略。
    无法解析（参数名不匹配、位置参数过多）时返回 None，调用方应保留 TODO。
    """
    if not param_names:
        return None
    slots: list[str | None] = [None] * len(param_names)
    index_by_name = {name.lower(): index for index, name in enumerate(param_names)}
    positional_next = 0
    i = 0
    while i < len(args):
        token = args[i]
        if is_named_arg(token):
            name, sep, inline = token[1:].partition(":")
            value: str | None = inline if sep else None
            if value is None:
                if i + 1 < len(args) and not is_named_arg(args[i + 1]):
                    value = args[i + 1]
                    i += 1
                else:
                    value = "true"
            key = name.lower()
            if key not in index_by_name:
                return None
            slots[index_by_name[key]] = value
        else:
            while positional_next < len(slots) and slots[positional_next] is not None:
                positional_next += 1
            if positional_next >= len(slots):
                return None
            slots[positional_next] = token
            positional_next += 1
        i += 1
    while slots and slots[-1] is None:
        slots.pop()
    return [slot if slot is not None else "" for slot in slots]


def needs_nullglob(text: str) -> bool:
    """判断代码片段中是否存在引号外的 ``*`` / ``?`` 通配符。"""
    quote = ""
    for char in text:
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            continue
        if char in "*?":
            return True
    return False


def strip_leading_attributes(text: str) -> tuple[str, str]:
    """剥离开头的 PowerShell attribute 块，返回 ``(属性文本, 剩余声明)``。

    支持 ``[Parameter(Mandatory=$true)]``、``[ValidateSet("a","b")]`` 这类
    含嵌套括号、引号与 ``$`` 的属性；连续多个属性会被全部剥离。
    """
    attrs: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n or text[i] != "[":
            break
        close = find_matching(text, "[", "]", i)
        if close < 0:
            break
        attrs.append(text[i + 1:close])
        i = close + 1
    return " ".join(attrs), text[i:].strip()
