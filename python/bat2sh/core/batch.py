"""Windows 批处理 (.bat/.cmd) -> Bash 转换器。

设计为"逐逻辑行转换 + 块结构栈"：
* ``^`` 续行先合并为逻辑行；
* ``if (...)`` / ``for ... do (...)`` 用栈跟踪缩进，行尾 ``)`` 负责闭合；
* 无法自动转换的命令生成 ``# TODO: 手动检查: ...``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import rules
from .settings import ConvertSettings
from .types import ConvertReport, Diagnostic, SourceKind
from .utils import (
    convert_backslashes,
    dq,
    find_matching,
    guard_read,
    is_fully_quoted,
    needs_nullglob,
    sanitize_identifier,
    split_redirects,
    strip_outer_quotes,
    tokenize_args,
)

_DOLLAR_PLACEHOLDER = "\ue000"


#: cmd 的 echo 空行写法：`echo.`、`echo(`、`echo:` 等（分隔符后紧跟的内容仍按字面回显）
_ECHO_BLANK_SEP = re.compile(r"(?i)^(@?\s*echo)([.:/\\\[\]+(,;=])(.*)$", re.S)


def _normalize_echo_blank(text: str) -> str:
    m = _ECHO_BLANK_SEP.match(text)
    if not m:
        return text
    return m.group(1) + " " + m.group(3)


#: `^X` 转义的目标字符 -> 占位符（避免被分词/重定向解析拆开，输出前还原）
_CARET_ESCAPES = {
    "&": "\ue101",
    "|": "\ue102",
    "<": "\ue103",
    ">": "\ue104",
    "^": "\ue105",
    "!": "\ue106",
}
_CARET_RESTORES = {placeholder: char for char, placeholder in _CARET_ESCAPES.items()}
_LITERAL_PERCENT = "\ue200"


def _protect_carets(text: str) -> str:
    """把引号外的 ``^X`` 替换为占位符；引号内的 ``^`` 是字面字符，保持原样。"""
    out: list[str] = []
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            out.append(char)
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            index += 1
            continue
        if char == "^" and index + 1 < len(text):
            placeholder = _CARET_ESCAPES.get(text[index + 1])
            if placeholder:
                out.append(placeholder)
                index += 2
                continue
        out.append(char)
        index += 1
    return "".join(out)


def _restore_placeholders(line: str) -> str:
    for placeholder, char in _CARET_RESTORES.items():
        line = line.replace(placeholder, char)
    return line.replace(_LITERAL_PERCENT, "%")


_VARIABLE_MARKER = re.compile(r"[%!]")


def _is_string_operand(token: str) -> bool:
    """equ/neq 的操作数是否按字符串比较：带引号，或裸的非数字字面量（无变量引用）。"""
    inner, quote = strip_outer_quotes(token)
    if quote:
        return True
    if _VARIABLE_MARKER.search(inner):
        return False
    return re.fullmatch(r"-?\d+", inner) is None


_FOR_F_TOKEN_ITEM = re.compile(r"(\d+)(?:-(\d+))?")


def _expand_tokens_spec(spec: str) -> list[int | None] | None:
    """把 ``tokens=`` 规格展开为字段槽位；``None`` 槽位表示 ``*``（取剩余部分）。"""
    text = spec.strip().lower()
    if not text:
        return None
    rest_marker = text.endswith("*")
    if rest_marker:
        text = text[:-1].strip().rstrip(",")
    slots: list[int | None] = []
    if text:
        for item in text.split(","):
            m = _FOR_F_TOKEN_ITEM.fullmatch(item)
            if not m:
                return None
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else start
            if start < 1 or end < start:
                return None
            slots.extend(range(start, end + 1))
    if rest_marker:
        slots.append(None)
    return slots or None


def _plan_for_f_read(slots: list[int | None], base: str) -> tuple[list[str], list[str]] | None:
    """按 tokens 槽位生成 (read 变量序列, 循环体可见变量列表)。"""
    if slots == [None]:
        return [base], [base]
    letters: list[str] = []
    for index in range(len(slots)):
        letter = chr(ord(base) + index)
        if not ("a" <= letter <= "z"):
            return None
        letters.append(letter)
    positions: dict[int, str] = {}
    for slot, letter in zip(slots, letters):
        if slot is None:
            continue
        if slot in positions:
            return None
        positions[slot] = letter
    read_vars = ["_" for _ in range(max(positions) if positions else 0)]
    for position, letter in positions.items():
        read_vars[position - 1] = letter
    if None in slots:
        read_vars.append(letters[slots.index(None)])
    else:
        read_vars.append("_")
    return read_vars, letters


def _for_f_ifs(slots: list[int | None], delims: str | None) -> str | None:
    """生成 ``while`` 的 IFS 前缀（含尾空格）；``None`` 表示 delims 无法安全引用。"""
    if slots == [None]:
        return "IFS= "
    if delims is None:
        return ""
    if delims == "":
        return "IFS= "
    if "'" in delims or "\\" in delims or "\n" in delims:
        return None
    if all(ch in ",;:|" for ch in delims):
        return f"IFS={delims} "
    return f"IFS='{delims}' "


def _split_sequential(text: str) -> list[str]:
    """按顶层单个 ``&`` 切分命令（保留 &&、||、管道与重定向中的 &）。"""
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    prev = ""
    i = 0
    while i < len(text):
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
        if c == "&":
            if i + 1 < len(text) and text[i + 1] == "&":
                buf.append("&&")
                i += 2
                continue
            if prev in "<>":
                buf.append(c)
                i += 1
                continue
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        if not c.isspace():
            prev = c
        i += 1
    parts.append("".join(buf))
    return [p for p in parts if p.strip()]


def _split_pipeline(text: str) -> list[str]:
    """按顶层单个 ``|`` 切分管道（保留 ||）。"""
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    i = 0
    while i < len(text):
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
        if c == "|":
            if i + 1 < len(text) and text[i + 1] == "|":
                buf.append("||")
                i += 2
                continue
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return [p for p in parts if p.strip()]


@dataclass
class _Block:
    kind: str          # if / else / for / group / comment
    close_word: str = "fi"
    loop_var: str = ""
    paren_depth: int = 1
    loop_vars: list[str] = field(default_factory=list)


@dataclass
class _ForFOptions:
    tokens: str | None = None
    delims: str | None = None
    skip: int = 0
    eol: str | None = None
    usebackq: bool = False


class BatchConverter:
    """把批处理脚本转换为 bash 脚本。"""

    def __init__(self, settings: ConvertSettings, source_name: str = "input.bat"):
        self.settings = settings
        self.source_name = source_name
        self.report = ConvertReport(source=source_name, kind=SourceKind.BATCH)
        self._out: list[str] = []
        self._func_out: list[str] = []
        self._stack: list[_Block] = []
        self._loop_vars: list[str] = []
        self._labels: set[str] = set()
        self._function_mode = False
        self._current_func: str | None = None
        self._needs_script_dir = False
        self._delayed_expansion = False
        self._needs_nullglob = False
        self._bat2sh_status_valid = False
        self._current_command = ""

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    def convert(self, text: str) -> str:
        logical = self._logical_lines(text)
        self.report.total_lines = len(logical)
        self._prescan(logical)
        for start, line in logical:
            produced = self._convert_line(start, line)
            produced = [_restore_placeholders(item) for item in produced]
            bucket = self._func_out if (self._function_mode and self._current_func) else self._out
            bucket.extend(produced)
            self._update_status_validity(line, produced)
            if not line.strip():
                continue
            if produced and any(
                p.strip() and not p.lstrip().startswith("#") for p in produced
            ):
                self.report.converted_lines += 1
            else:
                self.report.unchanged_lines += 1
        self._finish()
        return self._compose()

    # ------------------------------------------------------------------
    # 基础工具
    # ------------------------------------------------------------------
    @property
    def _indent(self) -> str:
        depth = len(self._stack) + (1 if self._current_func else 0)
        return self.settings.indent * depth

    def _c(self, content: str) -> str:
        return self._indent + content if content else ""

    def _warn(
        self, lineno: int, message: str, original: str = "", category: str = ""
    ) -> None:
        self.report.warnings.append(Diagnostic(lineno, message, original, category))

    def _todo(
        self, lineno: int, original: str, hint: str = "", category: str = ""
    ) -> str:
        message = f"手动检查: {original}"
        if hint:
            message += f"（{hint}）"
        self.report.todos.append(Diagnostic(lineno, message, original, category))
        comment = "# TODO: 手动检查: " + original
        return comment

    def _logical_lines(self, text: str) -> list[tuple[int, str]]:
        result: list[tuple[int, str]] = []
        buf = ""
        start = 0
        for number, raw in enumerate(text.split("\n"), start=1):
            line = raw.rstrip("\r")
            if buf:
                line = buf + line
                buf = ""
            else:
                start = number
            stripped = line.rstrip()
            m = re.search(r"(\^+)$", stripped)
            if m and len(m.group(1)) % 2 == 1:
                buf = stripped[:-1]
                continue
            result.append((start, line))
        if buf:
            result.append((start, buf))
        return result

    def _prescan(self, logical: list[tuple[int, str]]) -> None:
        for _, line in logical:
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"^:([A-Za-z_][\w.\-]*)\s*$", stripped):
                self._labels.add(stripped[1:].lower())
            if re.match(r"(?i)^call\s+:", stripped):
                self._function_mode = True
            if re.match(r"(?i)^setlocal\b.*enabledelayedexpansion", stripped):
                self._delayed_expansion = True

    def _compose(self) -> str:
        header = ["#!/usr/bin/env bash"]
        header.append(f"# 由 bat2sh 自动转换生成，源文件: {self.source_name}")
        header.append("# 带有 # TODO 标记的行无法自动转换，请人工检查")
        if self.settings.strict_mode:
            header.append("set -euo pipefail")
        if self._needs_nullglob:
            header.append("# 检测到通配符匹配：已启用 nullglob，无匹配时循环体不执行")
            header.append("shopt -s nullglob")
        if self._needs_script_dir:
            header.append('SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"')
        header.append("")
        chunks = ["\n".join(header)]
        if self._func_out:
            chunks.append("\n".join(self._func_out).rstrip())
        body = "\n".join(self._out).strip("\n")
        if body:
            chunks.append(body)
        return "\n".join(chunks).rstrip() + "\n"

    # ------------------------------------------------------------------
    # 变量展开
    # ------------------------------------------------------------------
    def _expand_vars(self, text: str, lineno: int) -> str:
        # 循环变量 %%i
        def loop_repl(m: re.Match[str]) -> str:
            ch = m.group(1).lower()
            if ch in self._loop_vars:
                return "${%s}" % ch
            self._warn(lineno, f"循环变量 %%{m.group(1)} 出现在 for 循环之外", text, category="control_flow")
            return "%" + m.group(1)

        def indirect_repl(m: re.Match[str]) -> str:
            self._warn(
                lineno,
                "检测到 %% 间接引用语法（call set），请手工处理",
                text,
                category="variables",
            )
            return _LITERAL_PERCENT + m.group(1) + _LITERAL_PERCENT

        def escaped_percent_repl(m: re.Match[str]) -> str:
            self._warn(
                lineno,
                "检测到转义百分号 %% ，已按字面 %% 处理",
                text,
                category="variables",
            )
            return _LITERAL_PERCENT + m.group(1) + _LITERAL_PERCENT

        # %%%VAR%%% 间接引用 / %%NAME%% 转义百分号（单字母留给 for 循环变量处理）
        text = re.sub(r"%%%([A-Za-z_][A-Za-z0-9_]*)%%%", indirect_repl, text)
        text = re.sub(r"%%([A-Za-z_][A-Za-z0-9_]*)%%", escaped_percent_repl, text)
        text = re.sub(r"%%([A-Za-z])", loop_repl, text)
        text = text.replace("%%", "%")

        # %~ 修饰符（%~dp0 / %~f1 / %%~nxF ...）
        text = re.sub(r"%~([dfnpx]*)([0-9*A-Za-z])", lambda m: self._modifier(m, lineno, text), text)
        # %* / %N
        text = text.replace("%*", '"$@"')
        text = re.sub(r"%([0-9])", r"$\1", text)

        # 延迟展开 !var!
        if self._delayed_expansion:
            text = re.sub(r"!([A-Za-z_]\w*)!", r"${\1}", text)

        # %NAME%
        def env_repl(m: re.Match[str]) -> str:
            name = m.group(1)
            upper = name.upper()
            if upper in rules.BATCH_ENV_MAP:
                if upper in rules.BATCH_ENV_WARN:
                    self._warn(lineno, f"%{name}% 的转换可能不完全等价", text, category="variables")
                return rules.BATCH_ENV_MAP[upper]
            return "${%s}" % name

        text = re.sub(r"%([A-Za-z_][A-Za-z0-9_]*)%", env_repl, text)
        return text

    def _modifier(self, m: re.Match[str], lineno: int, original: str) -> str:
        mods = m.group(1)
        target = m.group(2)
        if target == "*":
            return '"$@"'
        if target.isalpha():
            var = target.lower()
            if var in self._loop_vars:
                if "n" in mods and "x" in mods:
                    return f'$(basename "${{{var}}}")'
                if "f" in mods:
                    return f'$(readlink -f "${{{var}}}")'
                return f"${{{var}}}"
            self._warn(lineno, f"循环变量 %~{mods}{target} 不在 for 循环上下文中", original, category="control_flow")
            return "%" + target
        if target == "0":
            if "d" in mods or "p" in mods:
                self._needs_script_dir = True
                return "${SCRIPT_DIR}/"
            if "f" in mods:
                return '$(readlink -f "$0")'
            if "n" in mods and "x" in mods:
                return '$(basename "$0")'
            return '"$0"'
        arg = target
        if not mods:
            return f"${arg}"
        if "f" in mods:
            return f'$(readlink -f "${arg}")'
        if "n" in mods and "x" in mods:
            return f'$(basename "${arg}")'
        self._warn(lineno, f"参数修饰符 %~{mods}{target} 无法自动转换，已按 ${target} 处理", original, category="params")
        return f"${arg}"

    # ------------------------------------------------------------------
    # 分发
    # ------------------------------------------------------------------
    def _convert_line(self, lineno: int, raw: str) -> list[str]:
        # 注释块内：原样注释直到括号配平
        for block in reversed(self._stack):
            if block.kind == "comment":
                if raw.strip().startswith(")"):
                    block.paren_depth -= 1
                    if block.paren_depth <= 0:
                        self._stack.pop()
                    return []
                if raw.strip().endswith("("):
                    block.paren_depth += 1
                return [self._c("# " + raw.strip())]
            break

        text = raw.strip()
        if not text:
            return [""]

        if text.startswith(")"):
            return self._close_block_line(lineno, text)

        if self._stack and self._stack[-1].kind == "group" and self._stack[-1].paren_depth > 0:
            split = self._group_close_split(text)
            if split is not None:
                return self._close_group_inline(lineno, split, text)

        m = re.match(r"^:([A-Za-z_][\w.\-]*)\s*$", text)
        if m:
            return self._label_line(m.group(1))
        if text.startswith("::"):
            body = text[2:].strip()
            return [self._c("# " + body if body else "#")]
        m = re.match(r"(?i)^rem(?:\s+(.*))?$", text)
        if m:
            body = m.group(1) or ""
            return [self._c("# " + body if body else "#")]

        if text.startswith("@"):
            text = text[1:].strip()
            if not text:
                return []

        lower = text.lower()
        if lower in ("echo off", "echo  off"):
            return []
        if lower == "echo on":
            return [self._c("# 注意: echo on 在 bash 中无对应行为，已忽略")]

        if text == "(":
            opener = self._c("{")
            self._stack.append(_Block("group", "}"))
            return [opener]
        if text.startswith("("):
            return self._convert_paren_block(lineno, text)

        if re.match(r"(?i)^if[\s(]", text):
            return self._convert_if(lineno, text)
        if re.match(r"(?i)^for\s", text):
            return self._convert_for(lineno, text)
        if re.match(r"(?i)^goto\b", text):
            return self._convert_goto(lineno, text)
        if re.match(r"(?i)^call\b", text):
            return self._convert_call(lineno, text)
        if re.match(r"(?i)^exit\b", text):
            return self._convert_exit(lineno, text)

        protected = _protect_carets(text)
        return self._convert_simple(lineno, protected)

    # ------------------------------------------------------------------
    # 块闭合
    # ------------------------------------------------------------------
    def _pop_block(self, lineno: int) -> list[str]:
        if not self._stack:
            self._warn(lineno, "多余的 ')'", "", category="misc")
            return [self._c("# 多余的 ')'，已忽略")]
        block = self._stack.pop()
        names = list(block.loop_vars)
        if block.loop_var:
            names.insert(0, block.loop_var)
        for name in names:
            if name in self._loop_vars:
                self._loop_vars.remove(name)
        if block.close_word:
            return [self._c(block.close_word)]
        return []

    def _close_block_line(self, lineno: int, text: str) -> list[str]:
        rest = text[1:].strip()
        if self._stack and self._stack[-1].kind == "group":
            tail_text = self._convert_group_tail(lineno, rest)
            if tail_text is None:
                self._warn(lineno, "括号块结束符后的内容无法自动转换，已忽略", text, category="misc")
                tail_text = ""
            self._pop_group_block()
            suffix = f" {tail_text}" if tail_text else ""
            return [self._c("}" + suffix)]
        if not rest:
            return self._pop_block(lineno)
        low = rest.lower()
        if low.startswith("else"):
            after = rest[4:].strip()
            if after.lower().startswith("if"):
                if self._stack:
                    self._stack.pop()
                else:
                    self._warn(lineno, "多余的 'else'", text, category="misc")
                return self._convert_if(lineno, "if " + after[2:].strip(), is_elif=True)
            # ) else (
            if self._stack:
                self._stack.pop()
            else:
                self._warn(lineno, "多余的 'else'", text, category="misc")
            else_line = self._c("else")
            if after.startswith("("):
                inner = after[1:]
                close = find_matching(after, "(", ")")
                if close > 0:
                    body = after[1:close]
                    tail = after[close + 1:].strip()
                    if tail:
                        self._warn(lineno, f"else 块后的内容被忽略: {tail}", text, category="misc")
                    self._stack.append(_Block("else", "fi"))
                    lines = [else_line]
                    if body.strip():
                        lines.extend(self._convert_line(lineno, body))
                    self._stack.pop()
                    lines.append(self._c("fi"))
                    return lines
                self._stack.append(_Block("else", "fi"))
                lines = [else_line]
                if inner.strip():
                    lines.extend(self._convert_line(lineno, inner))
                return lines
            self._stack.append(_Block("else", "fi"))
            return [else_line]
        return self._pop_block(lineno)

    def _group_close_split(self, text: str) -> tuple[str, str] | None:
        """在组块内容行内查找配对的 ``)``；返回 (块内文本, 块后文本)，未闭合返回 None。"""
        block = self._stack[-1]
        depth = block.paren_depth
        quote = ""
        for index, char in enumerate(text):
            if quote:
                if char == quote:
                    quote = ""
                continue
            if char in "\"'":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    block.paren_depth = 0
                    return text[:index], text[index + 1:]
        block.paren_depth = depth
        return None

    def _close_group_inline(self, lineno: int, split: tuple[str, str], text: str) -> list[str]:
        before, tail = split
        lines: list[str] = []
        if before.strip():
            lines.extend(self._convert_line(lineno, before.strip()))
        tail_text = self._convert_group_tail(lineno, tail.strip())
        if tail_text is None:
            self._warn(lineno, "括号块结束符后的内容无法自动转换，已忽略", text, category="misc")
            tail_text = ""
        self._pop_group_block()
        suffix = f" {tail_text}" if tail_text else ""
        lines.append(self._c("}" + suffix))
        return lines

    def _pop_group_block(self) -> None:
        self._stack.pop()
        if self._stack and self._stack[-1].kind == "group" and self._stack[-1].paren_depth > 0:
            self._stack[-1].paren_depth -= 1

    def _convert_paren_block(self, lineno: int, text: str) -> list[str]:
        close = find_matching(text, "(", ")")
        opener = self._c("{")
        if close < 0:
            # 形如 `(echo a`：块内容与 `(` 同行，等待后续 `)` 行闭合
            self._stack.append(_Block("group", "}"))
            lines = [opener]
            body = text[1:].strip()
            if body:
                lines.extend(self._convert_line(lineno, body))
            return lines
        tail_text = self._convert_group_tail(lineno, text[close + 1:].strip())
        if tail_text is None:
            self._todo(lineno, text, "括号块后的管道/重定向无法自动转换", category="control_flow")
            return [self._c("# TODO: 手动检查: " + text)]
        suffix = f" {tail_text}" if tail_text else ""
        parts = _split_sequential(text[1:close])
        inner: list[str] = []
        for part in parts:
            inner.extend(self._convert_line(lineno, part.strip()))
        commands = [line.strip() for line in inner if line.strip()]
        single_line = len(inner) == len(parts) and all(
            not command.startswith("#") for command in commands
        )
        if single_line:
            joined = "; ".join(commands) if commands else ":"
            return [self._c(f"{{ {joined}; }}" + suffix)]
        lines = [opener]
        for command in commands:
            lines.append(self._indent + self.settings.indent + command)
        lines.append(self._c("}" + suffix))
        return lines

    def _convert_group_tail(self, lineno: int, rest: str) -> str | None:
        """把 `)` 之后的重定向/管道/逻辑连接转成可拼在 `}` 后的文本。"""
        if not rest:
            return ""
        body, redirs = split_redirects(rest)
        redir_text = self._render_redirs(redirs, lineno)
        body = body.strip()
        suffix = ""
        if body.startswith("&&") or body.startswith("||"):
            rhs = self._convert_line(lineno, body[2:].strip())
            if len(rhs) != 1 or rhs[0].lstrip().startswith("#"):
                return None
            suffix = f" {body[:2]} " + rhs[0].strip()
        elif body.startswith("|"):
            rhs = self._convert_simple(lineno, body[1:].strip())
            if len(rhs) != 1 or rhs[0].lstrip().startswith("#"):
                return None
            suffix = " | " + rhs[0].strip()
        elif body:
            return None
        return (suffix + " " + redir_text).strip()

    # ------------------------------------------------------------------
    # 标签 / goto / call / exit
    # ------------------------------------------------------------------
    def _label_line(self, name: str) -> list[str]:
        if not self._function_mode:
            return [self._c(f"# :{name}（标签，未使用，保留为注释）")]
        # 进入函数时 errorlevel 来自调用方，静态不可知，保守作废状态快照。
        self._bat2sh_status_valid = False
        out: list[str] = []
        if self._current_func:
            self._trim_function_tail()
            out.append("}")
            out.append("")
        func = "label_" + sanitize_identifier(name)
        self._current_func = func
        out.append(f"{func}() {{")
        return out

    def _trim_function_tail(self) -> None:
        while self._func_out and not self._func_out[-1].strip():
            self._func_out.pop()

    def _convert_goto(self, lineno: int, text: str) -> list[str]:
        m = re.match(r"(?i)^goto\s+:?([\w.\-]+)\s*$", text)
        if m and m.group(1).lower() == "eof":
            # 批处理的 goto :eof 不修改 errorlevel；函数内用 return 保留上一条命令的退出码，
            # 这样 ``if errorlevel`` 改写出的 ``if ! func; then`` 才能真正捕获失败。
            return [self._c("return" if self._current_func else "exit 0")]
        if self._function_mode:
            self._todo(lineno, text, "goto 跨函数跳转无法自动重构，请手动改为函数调用或循环", category="control_flow")
        else:
            self._todo(lineno, text, "goto 控制流无法自动转换，请手动重构", category="control_flow")
        return [self._c("# TODO: 手动检查: " + text)]

    def _convert_call(self, lineno: int, text: str) -> list[str]:
        m = re.match(r"(?i)^call\s+:([\w.\-]+)\s*(.*)$", text)
        if m:
            func = "label_" + sanitize_identifier(m.group(1))
            args = self._expand_vars(convert_backslashes(m.group(2).strip()), lineno)
            return [self._c((func + " " + args).strip())]
        m = re.match(r"(?i)^call\s+(.+)$", text)
        if not m:
            return []
        parts = tokenize_args(m.group(1))
        if not parts:
            return []
        script, q = strip_outer_quotes(parts[0])
        rest = " ".join(
            tokenize_args(self._expand_vars(convert_backslashes(" ".join(parts[1:])), lineno))
        )
        if script.lower().endswith((".bat", ".cmd")):
            converted = re.sub(r"(?i)\.(bat|cmd)$", ".sh", convert_backslashes(script))
            self._warn(
                lineno,
                f"call 已转换为执行同名 bash 脚本 {converted}，请确认该文件已转换",
                text,
                category="control_flow",
            )
            return [self._c(f'bash "{converted}" {rest}'.rstrip())]
        self._todo(lineno, text, "call 目标不是批处理脚本，请手动处理", category="control_flow")
        return [self._c("# TODO: 手动检查: " + text)]

    def _convert_exit(self, lineno: int, text: str) -> list[str]:
        m = re.match(r"(?i)^exit(?:\s+/b)?(?:\s+(-?\d+))?\s*$", text)
        code = m.group(1) if m else None
        is_b = bool(re.search(r"(?i)/b\b", text))
        in_func = self._current_func is not None
        keyword = "return" if (is_b and in_func) else "exit"
        if code is not None:
            return [self._c(f"{keyword} {code}")]
        return [self._c(f"{keyword} $?")]

    # ------------------------------------------------------------------
    # if
    # ------------------------------------------------------------------
    def _convert_if(self, lineno: int, text: str, is_elif: bool = False) -> list[str]:
        rest = text.strip()[2:].lstrip()
        if rest.lower().startswith("/i"):
            rest = rest[2:].lstrip()
            self._warn(lineno, "if /i（忽略大小写）无法在 [ ] 中实现，已按区分大小写处理", text, category="control_flow")
        negate = False
        m = re.match(r"(?i)^not\s+", rest)
        if m:
            negate = True
            rest = rest[m.end():]
        elif rest.lower().startswith("not("):
            negate = True
            rest = rest[3:].lstrip()

        errorlevel = (
            re.match(r"(?i)^errorlevel\s+(-?\d+)\s*(.*)$", rest) if not is_elif else None
        )
        merged = None
        if errorlevel is not None and errorlevel.group(2).strip():
            merged = self._errorlevel_condition(lineno, int(errorlevel.group(1)), negate, text)
        if merged is not None:
            cond = merged
            remainder = errorlevel.group(2)
        else:
            cond, remainder = self._parse_condition(lineno, rest, negate)
        keyword = "elif" if is_elif else "if"
        remainder = remainder.strip()

        if remainder.startswith("("):
            close = find_matching(remainder, "(", ")")
            if close < 0:
                body = remainder[1:].strip()
                header = self._c(f"{keyword} {cond}; then")
                self._stack.append(_Block("if", "fi"))
                lines = [header]
                if body:
                    lines.extend(self._convert_line(lineno, body))
                return lines
            body = remainder[1:close]
            tail = remainder[close + 1:].strip()
            base = self._indent
            header = base + f"{keyword} {cond}; then"
            self._stack.append(_Block("if", "fi"))
            lines = [header]
            if body.strip():
                lines.extend(self._convert_line(lineno, body))
            if tail.lower().startswith("else"):
                after = tail[4:].strip()
                if after.lower().startswith("if"):
                    self._stack.pop()
                    lines.extend(self._convert_if(lineno, "if " + after[2:].strip(), is_elif=True))
                    return lines
                lines.append(base + "else")
                if after.startswith("("):
                    close2 = find_matching(after, "(", ")")
                    inner2 = after[1:close2] if close2 > 0 else after[1:]
                    if inner2.strip():
                        lines.extend(self._convert_line(lineno, inner2))
                elif after:
                    lines.extend(self._convert_line(lineno, after))
                self._stack.pop()
                lines.append(self._c("fi"))
                return lines
            if tail:
                self._warn(lineno, f"if 块后存在未识别内容: {tail}", text, category="control_flow")
            self._stack.pop()
            lines.append(self._c("fi"))
            return lines

        if not remainder:
            self._warn(lineno, "if 没有可执行的语句", text, category="control_flow")
            return [self._c("# TODO: 手动检查: " + text)]

        header = self._c(f"{keyword} {cond}; then")
        self._stack.append(_Block("if", "fi"))
        inner = self._convert_line(lineno, remainder)
        self._stack.pop()
        lines = [header]
        lines.extend(inner)
        lines.append(self._c("fi"))
        return lines

    def _parse_condition(self, lineno: int, expr: str, negate: bool) -> tuple[str, str]:
        m = re.match(r'(?i)^exist\s+(".*?"|\S+)\s*(.*)$', expr)
        if m:
            token = m.group(1)
            quoted = token.startswith(('"', "'"))
            raw_target, _ = strip_outer_quotes(token)
            converted = convert_backslashes(self._expand_vars(raw_target, lineno))
            target = dq(converted)
            if not quoted and needs_nullglob(converted):
                if self._is_safe_glob_pattern(converted):
                    condition = f"compgen -G {target} > /dev/null"
                    if negate:
                        condition = f"! {condition}"
                    return condition, m.group(2)
                self._warn(
                    lineno,
                    "cmd 的 if exist 支持通配符，但该模式无法安全转换为 compgen -G；"
                    "如需匹配任意文件请手动改为 ls <模式> 2>/dev/null",
                    expr,
                    category="glob",
                )
            test = f"-e {target}"
            if negate:
                test = f"! {test}"
            return f"[ {test} ]", m.group(2)

        m = re.match(r"(?i)^defined\s+([\w.]+)\s*(.*)$", expr)
        if m:
            name = sanitize_identifier(m.group(1))
            test = f'-z "${{{name}:-}}"' if negate else f'-n "${{{name}:-}}"'
            return f"[ {test} ]", m.group(2)

        m = re.match(r"(?i)^errorlevel\s+(-?\d+)\s*(.*)$", expr)
        if m:
            threshold = m.group(1)
            op = "-lt" if negate else "-ge"
            self._warn(lineno, "$? 只能反映紧邻上一条命令的退出码，请检查语句顺序", expr, category="errorlevel")
            return f"[ $? {op} {threshold} ]", m.group(2)

        m = re.match(r"(?i)^cmdextversion\s+\S+\s*(.*)$", expr)
        if m:
            self._warn(lineno, "cmdextversion 在 Linux 无对应检查，恒为假", expr, category="errorlevel")
            return "[ 0 -eq 1 ]", m.group(1)

        m = re.match(
            r'^\s*("(?:[^"]*)"|\S+?)\s*(===|==|equ|neq|lss|leq|gtr|geq)\s*'
            r'("(?:[^"]*)"|\S+)(?:\s+(.*))?$',
            expr,
            re.I | re.S,
        )
        if m:
            op_token = m.group(2).lower()
            left = self._convert_operand(m.group(1), lineno)
            op = rules.BATCH_TEST_OPERATORS.get(op_token, "=")
            if op_token in ("equ", "neq") and (
                _is_string_operand(m.group(1)) or _is_string_operand(m.group(3))
            ):
                op = "=" if op_token == "equ" else "!="
            right = self._convert_operand(m.group(3), lineno)
            test = f"{left} {op} {right}"
            if negate:
                test = f"! {test}"
            return f"[ {test} ]", (m.group(4) or "")

        self._warn(lineno, "无法解析的 if 条件，已生成 TODO", expr, category="control_flow")
        return "[ 0 -eq 1 ]", "( # TODO: 手动检查条件: " + expr + " )"

    def _active_bucket(self) -> list[str]:
        if self._function_mode and self._current_func:
            return self._func_out
        return self._out

    def _take_previous_command(self) -> str | None:
        """取出并移除最近生成的一条可作 if 条件的简单命令。"""
        bucket = self._active_bucket()
        for index in range(len(bucket) - 1, -1, -1):
            line = bucket[index].strip()
            if not line or line.startswith("#"):
                continue
            if line in ("fi", "else", "done", "esac", "}") or line.endswith(
                ("{", "(", "|", "&", "&&", "||", ";")
            ):
                return None
            del bucket[index]
            return line
        return None

    def _restore_command(self, command: str) -> None:
        self._active_bucket().append(self._c(command))

    @staticmethod
    def _is_structural_line(line: str) -> bool:
        if line in ("fi", "else", "done", "esac", "}", ";;", ")"):
            return True
        if line.endswith(("; then", "; do", "() {")):
            return True
        return bool(re.match(r"(?i)^(exit|return)(\s|$)", line))

    def _has_effectful_command(self, produced: list[str]) -> bool:
        for raw in produced:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if self._is_structural_line(line):
                continue
            return True
        return False

    def _update_status_validity(self, raw: str, produced: list[str]) -> None:
        """按生成结果维护 ``__bat2sh_status`` 快照是否仍反映最近一条命令的退出码。"""
        if re.match(
            r"(?i)^\s*@?\s*if\s+(?:/i\s+)?(?:not\s+|not\()?errorlevel\b", raw
        ):
            if self._bat2sh_status_valid and self._has_effectful_command(produced):
                self._bat2sh_status_valid = False
            return
        if self._has_effectful_command(produced):
            self._bat2sh_status_valid = False

    @staticmethod
    def _status_condition(threshold: int, negate: bool) -> str:
        if threshold == 1:
            return '[ "$__bat2sh_status" -eq 0 ]' if negate else '[ "$__bat2sh_status" -ge 1 ]'
        op = "-lt" if negate else "-ge"
        return f'[ "$__bat2sh_status" {op} {threshold} ]'

    def _errorlevel_condition(
        self, lineno: int, threshold: int, negate: bool, original: str
    ) -> str | None:
        """把 ``if errorlevel N`` 改写为直接作用于上一条命令的条件。

        优先复用仍然有效的 ``__bat2sh_status`` 快照（连续 errorlevel 判断）；
        否则上一条是简单命令时生成捕获（N>1）或 ``if ! cmd``（N=1），无法安全
        合并时返回 None，由 :meth:`_parse_condition` 回退为 ``$?`` 比较并告警。
        """
        if self._bat2sh_status_valid:
            if threshold <= 0:
                return "true" if not negate else "false"
            return self._status_condition(threshold, negate)
        previous = self._take_previous_command()
        if previous is None:
            return None
        if threshold <= 0:
            # errorlevel 0 / 负数恒为真（或恒为假），命令仍需执行。
            self._restore_command(previous)
            self._bat2sh_status_valid = False
            return "true" if not negate else "false"
        if threshold > 1:
            self._restore_command("__bat2sh_status=0")
            self._restore_command(f"{previous} || __bat2sh_status=$?")
            self._warn(
                lineno,
                f"if {'not ' if negate else ''}errorlevel {threshold} 已改用 __bat2sh_status "
                "精确捕获上一条命令的退出码，请核对语句顺序",
                original,
                category="errorlevel",
            )
            self._bat2sh_status_valid = True
            return self._status_condition(threshold, negate)
        self._bat2sh_status_valid = False
        return previous if negate else f"! {previous}"

    @staticmethod
    def _is_safe_glob_pattern(pattern: str) -> bool:
        if not pattern or pattern.startswith("-"):
            return False
        return not any(marker in pattern for marker in ("$(", "`", "\n"))

    def _convert_operand(self, token: str, lineno: int) -> str:
        inner, quote = strip_outer_quotes(token)
        expanded = convert_backslashes(self._expand_vars(inner, lineno))
        if re.fullmatch(r"-?\d+", expanded):
            return expanded
        if quote or self.settings.quote_variables or re.search(r"[\s$&|()<>]", expanded):
            return dq(expanded)
        return expanded

    def _convert_path_token(self, token: str, lineno: int) -> str:
        inner, _ = strip_outer_quotes(token)
        return dq(convert_backslashes(self._expand_vars(inner, lineno)))

    # ------------------------------------------------------------------
    # for
    # ------------------------------------------------------------------
    def _convert_for(self, lineno: int, text: str) -> list[str]:
        m = re.match(
            r"(?i)^for\s+(.*?)%%~?([a-z])\s+in\s+\((.*)\)\s+do\s*(.*)$",
            text.strip(),
            re.S,
        )
        if not m:
            self._todo(lineno, text, "无法解析的 for 语句", category="control_flow")
            return [self._c("# TODO: 手动检查: " + text)]
        opts = m.group(1).strip()
        var = m.group(2).lower()
        set_text = m.group(3).strip()
        body = m.group(4).strip()
        opts_lower = opts.lower()

        if "/f" in opts_lower:
            return self._emit_for_f(lineno, text, opts, set_text, var, body)

        if "/r" in opts_lower:
            return self._for_todo_lines(lineno, text, body, "for /r 请改用 find")

        items = self._convert_for_set(set_text, lineno)
        if "/l" in opts_lower:
            nums = [self._expand_vars(p.strip(), lineno) for p in set_text.split(",")]
            if len(nums) == 2:
                nums.append("1")
            if len(nums) == 3:
                items = "$(seq %s %s %s)" % (nums[0], nums[1], nums[2])
            else:
                items = "$(seq %s)" % nums[0]
        elif "/d" in opts_lower:
            if not items.endswith("*"):
                items = items.rstrip(" *") + "/*"
            items += "/"

        self._note_glob(lineno, items, text)
        header = self._indent + f"for {var} in {items}; do"
        if body.startswith("("):
            close = find_matching(body, "(", ")")
            if close < 0:
                self._loop_vars.append(var)
                self._stack.append(_Block("for", "done", var))
                lines = [header]
                inner = body[1:].strip()
                if inner:
                    lines.extend(self._convert_line(lineno, inner))
                return lines
            inner = body[1:close]
            self._loop_vars.append(var)
            self._stack.append(_Block("for", "done", var))
            lines = [header]
            if inner.strip():
                lines.extend(self._convert_line(lineno, inner))
            self._stack.pop()
            self._loop_vars.remove(var)
            lines.append(self._indent + "done")
            return lines

        if not body:
            self._loop_vars.append(var)
            self._stack.append(_Block("for", "done", var))
            return [header]

        self._loop_vars.append(var)
        self._stack.append(_Block("for", "done", var))
        inner_lines = self._convert_line(lineno, body)
        self._stack.pop()
        self._loop_vars.remove(var)
        lines = [header]
        lines.extend(inner_lines)
        lines.append(self._indent + "done")
        return lines

    def _emit_for_f(
        self, lineno: int, text: str, opts: str, set_text: str, var: str, body: str
    ) -> list[str]:
        options = self._parse_for_f_options(opts)
        if options is None:
            return self._for_todo_lines(
                lineno, text, body, "for /f 的选项无法解析（tokens/delims/usebackq）"
            )

        command: str | None = None
        file_target: str | None = None
        source = set_text.strip()
        if (
            len(source) >= 2
            and source.startswith("'")
            and source.endswith("'")
            and not options.usebackq
        ):
            raw = source[1:-1].strip()
            if not raw:
                return self._for_todo_lines(lineno, text, body, "for /f 的 '命令' 为空，请手工转换")
            todo_mark = len(self.report.todos)
            command_lines = self._convert_simple_no_pipe(lineno, raw)
            if (
                len(command_lines) != 1
                or not command_lines[0].strip()
                or command_lines[0].lstrip().startswith("#")
            ):
                del self.report.todos[todo_mark:]
                return self._for_todo_lines(
                    lineno, text, body, "for /f 的命令无法自动转换，请手工改写为 while read"
                )
            command = command_lines[0].strip()
        elif (
            options.usebackq
            and len(source) >= 2
            and source.startswith('"')
            and source.endswith('"')
        ):
            file_target = self._convert_path_token(source[1:-1], lineno)
        elif source and not source.startswith(("'", '"', "`")):
            file_target = self._convert_path_token(source, lineno)
        else:
            return self._for_todo_lines(
                lineno,
                text,
                body,
                "for /f 仅支持 '命令' 与 usebackq 文件形式，字符串/反引号请手工转换",
            )

        if re.search(r"(?i)\bgoto\b", body):
            self._warn(
                lineno,
                "循环体含 goto：无法还原跳出语义，已整行 TODO，请手工改写为 break/函数",
                text,
                category="control_flow",
            )
            return self._for_todo_lines(lineno, text, body, "循环体含 goto，无法保证跳出语义")

        slots = _expand_tokens_spec(options.tokens if options.tokens is not None else "1")
        if slots is None:
            return self._for_todo_lines(lineno, text, body, "for /f 的 tokens 选项无法解析")
        plan = _plan_for_f_read(slots, var)
        if plan is None:
            return self._for_todo_lines(lineno, text, body, "for /f 的 tokens 超出可映射变量范围")
        read_vars, loop_vars = plan
        ifs = _for_f_ifs(slots, options.delims)
        if ifs is None:
            return self._for_todo_lines(lineno, text, body, "for /f 的 delims 无法安全引用")

        declared = set(loop_vars)
        undeclared: list[str] = []
        for match in re.finditer(r"(?<!%)%%(?:~[a-z]*)?([A-Za-z])", body):
            letter = match.group(1).lower()
            if letter not in declared and letter not in undeclared:
                undeclared.append(letter)
        for letter in undeclared:
            self._warn(
                lineno,
                f"循环体引用 %%{letter} 但 tokens 未声明",
                text,
                category="control_flow",
            )

        header = self._indent + f"while {ifs}read -r {' '.join(read_vars)}; do"
        if command is not None:
            body_source = (
                f"{command} | tail -n +{options.skip + 1}" if options.skip else command
            )
            close_word = f"done < <({body_source})"
        elif options.skip:
            close_word = f"done < <(tail -n +{options.skip + 1} < {file_target})"
        else:
            close_word = f"done < {file_target}"
        self._loop_vars.extend(loop_vars)
        block = _Block("for", close_word)
        block.loop_vars = list(loop_vars)
        self._stack.append(block)
        first_var = loop_vars[0]
        if options.eol:
            escaped = options.eol if options.eol.isalnum() else "\\" + options.eol
            guard = self._c(f'[[ -z "${first_var}" || "${first_var}" == {escaped}* ]] && continue')
            self._warn(
                lineno,
                f"eol={options.eol} 仅近似为跳过以 {options.eol} 开头的行；"
                f"Windows 在行中间遇到 {options.eol} 会截断，请核对",
                text,
                category="control_flow",
            )
        else:
            guard = self._c(f'[ -z "${first_var}" ] && continue')
        trim_var = loop_vars[-1]
        trim = self._c(f"{trim_var}=\"${{{trim_var}%$'\\r'}}\"")
        prelude = [header, trim, guard]

        body = body.strip()
        if body.startswith("("):
            close = find_matching(body, "(", ")")
            if close < 0:
                lines = list(prelude)
                inner = body[1:].strip()
                if inner:
                    lines.extend(self._convert_line(lineno, inner))
                return lines
            inner = body[1:close]
            lines = list(prelude)
            if inner.strip():
                lines.extend(self._convert_line(lineno, inner))
            self._stack.pop()
            for name in loop_vars:
                self._loop_vars.remove(name)
            lines.append(self._indent + close_word)
            return lines
        if not body:
            return list(prelude)
        lines = list(prelude)
        lines.extend(self._convert_line(lineno, body))
        self._stack.pop()
        for name in loop_vars:
            self._loop_vars.remove(name)
        lines.append(self._indent + close_word)
        return lines

    @staticmethod
    def _parse_for_f_options(opts: str) -> _ForFOptions | None:
        rest = re.sub(r"(?i)^/f\b\s*", "", opts).strip()
        if not rest:
            return _ForFOptions()
        m = re.match(r'^"(.*)"$', rest, re.S)
        if not m:
            return None
        options = _ForFOptions()
        for part in m.group(1).split():
            low = part.lower()
            if low == "usebackq":
                options.usebackq = True
            elif low.startswith("tokens="):
                options.tokens = part.split("=", 1)[1]
            elif low.startswith("delims="):
                options.delims = part.split("=", 1)[1]
                if '"' in options.delims:
                    return None
            elif low.startswith("skip="):
                value = part.split("=", 1)[1]
                if not value.isdigit():
                    return None
                options.skip = int(value)
            elif low.startswith("eol="):
                value = part.split("=", 1)[1]
                if len(value) > 1:
                    return None
                options.eol = value or None
            else:
                return None
        return options

    def _for_todo_lines(self, lineno: int, text: str, body: str, hint: str) -> list[str]:
        self._todo(lineno, text, hint, category="control_flow")
        lines = [self._c("# TODO: 手动检查: " + text)]
        if body == "(" or (body.startswith("(") and find_matching(body, "(", ")") == -1):
            block = _Block("comment", "")
            block.paren_depth = 1
            self._stack.append(block)
            inner = body[1:].strip()
            if inner:
                block.paren_depth += 1
                lines.append(self._c("# " + inner))
        return lines

    def _convert_for_set(self, set_text: str, lineno: int) -> str:
        expanded = self._expand_vars(set_text, lineno)
        expanded = convert_backslashes(expanded)
        expanded = re.sub(r"\s*[,;]\s*", " ", expanded)
        tokens = tokenize_args(expanded)
        fixed = [
            self._quote_collection_token(self._fix_glob_token(t), lineno)
            for t in tokens
        ]
        return " ".join(fixed).strip()

    _COLLECTION_VAR_RE = re.compile(r"^\$(?:\{[A-Za-z_]\w*\}|[0-9]+|[@*])$")

    def _quote_collection_token(self, token: str, lineno: int) -> str:
        if not self.settings.quote_variables or not self._COLLECTION_VAR_RE.match(token):
            return token
        name = self._collection_token_display(token)
        self._warn(
            lineno,
            f"{name} 变量集合已加引号以避免空格拆分，"
            "如需匹配 cmd 的空白拆词行为请手动去掉引号",
            token,
            category="glob",
        )
        return dq(token)

    def _collection_token_display(self, token: str) -> str:
        if token.startswith("${"):
            inner = token[2:-1]
            if inner in self._loop_vars:
                return f"%%{inner}"
            return f"%{inner}%"
        inner = token.lstrip("$")
        if inner.isdigit():
            return f"%{inner}"
        return "%*"

    def _note_glob(self, lineno: int, snippet: str, original: str) -> None:
        if not needs_nullglob(snippet) or self._needs_nullglob:
            return
        self._needs_nullglob = True
        self._warn(
            lineno,
            "检测到通配符集合，已在脚本头添加 shopt -s nullglob：无匹配时循环体不执行",
            original,
            category="glob",
        )

    @staticmethod
    def _fix_glob_token(token: str) -> str:
        if not (len(token) >= 2 and token.startswith('"') and token.endswith('"')):
            return token
        inner = token[1:-1]
        if not re.search(r"[*?]", inner):
            return token
        index = max(inner.rfind("/"), inner.rfind("\\"))
        if index <= 0:
            return inner
        directory, pattern = inner[:index], inner[index + 1:]
        return dq(directory) + "/" + pattern

    # ------------------------------------------------------------------
    # 简单命令
    # ------------------------------------------------------------------
    def _convert_simple(self, lineno: int, text: str) -> list[str]:
        pipe_parts = _split_pipeline(text)
        if len(pipe_parts) > 1:
            bodies: list[str] = []
            for seg in pipe_parts:
                seg_lines = self._convert_simple_no_pipe(lineno, seg.strip())
                if len(seg_lines) != 1:
                    self._todo(lineno, text, "复杂管道无法自动转换", category="pipeline")
                    return [self._c("# TODO: 手动检查: " + text)]
                bodies.append(seg_lines[0].strip())
            return [self._indent + " | ".join(bodies)]
        return self._convert_simple_no_pipe(lineno, text)

    def _convert_simple_no_pipe(self, lineno: int, text: str) -> list[str]:
        parts = _split_sequential(text)
        if len(parts) > 1:
            out: list[str] = []
            for part in parts:
                out.extend(self._convert_simple_no_pipe(lineno, part.strip()))
            return out
        # rem 注释：整行（含 `&` 分隔出来的片段、for /f 内层命令）都按注释处理，
        # 不再落入“未知命令”。cmd 的 rem 会吞掉行内其余内容，重定向符也不例外。
        m = re.match(r"(?i)^rem(?:\s+(.*))?$", text.strip())
        if m:
            comment = m.group(1) or ""
            return [self._c("# " + comment if comment else "#")]
        text = _normalize_echo_blank(text)
        body, redirs = split_redirects(text)
        redir_text = self._render_redirs(redirs, lineno)
        if not body.strip():
            return [self._c(redir_text)] if redir_text else []
        if re.match(r"(?i)^@?\s*echo(?:\s|$)", body):
            body = body.replace("$", _DOLLAR_PLACEHOLDER)
        expanded = self._expand_vars(body, lineno)
        tokens = tokenize_args(expanded)
        if not tokens:
            return []
        raw_first = tokens[0]
        first = raw_first.strip("\"'").lower()
        rest = expanded[len(raw_first):].strip()
        self._current_command = first

        line: str | None
        if first in rules.BATCH_HANDLER_MAP:
            handler = getattr(self, rules.BATCH_HANDLER_MAP[first])
            line = handler(lineno, rest, expanded)
            if line is None:
                return []
        elif first in rules.BATCH_TODO_COMMANDS:
            hint = rules.BATCH_TODO_COMMANDS[first]
            self._todo(lineno, text, hint, category="command")
            line = None
        elif first in rules.BATCH_SIMPLE_MAP:
            mapped = rules.BATCH_SIMPLE_MAP[first]
            line = (mapped + " " + rest).strip()
        elif first.endswith((".exe", ".com")) or first in rules.BATCH_EXE_MAP:
            mapped = rules.BATCH_EXE_MAP.get(first)
            if mapped:
                self._warn(lineno, f"{raw_first} 已按 {mapped} 处理", text, category="command")
                line = (mapped + " " + rest).strip()
            else:
                self._todo(lineno, text, "Windows 可执行文件在 Linux 无对应物", category="command")
                line = None
        elif first == "more" and re.match(r"^\+\d+", rest):
            plus_n = re.match(r"^(\+\d+)", rest).group(1)
            self._warn(
                lineno,
                f"more {plus_n} 参数语义不同（Linux 版无 {plus_n} 跳过首行），请核对",
                text,
                category="command",
            )
            line = expanded
        elif first in rules.BATCH_POSIX_KEEP:
            line = expanded
        else:
            self._warn(lineno, f"未知命令 {raw_first!r}，请确认 Linux 下可用", text, category="command")
            line = expanded

        if line is None:
            result = [self._c("# TODO: 手动检查: " + text)]
        else:
            full = self._append_redirs(line, redir_text)
            result = [self._c(full)]
        return result

    @staticmethod
    def _append_redirs(command: str, redir_text: str) -> str:
        """把重定向拼到命令上；``guard_read`` 的 ``|| true`` 守卫始终保留在末尾。"""
        stripped = command.rstrip()
        if not redir_text:
            return stripped
        guard = "|| true"
        if stripped.endswith(guard):
            base = stripped[: -len(guard)].rstrip()
            return f"{base} {redir_text} {guard}"
        return f"{stripped} {redir_text}".strip()

    def _render_redirs(self, redirs: list[tuple[str, str]], lineno: int) -> str:
        parts: list[str] = []
        for op, target in redirs:
            if target.startswith("&"):
                parts.append(f"{op}{target}")
                continue
            inner, quote = strip_outer_quotes(target)
            low = inner.lower()
            if low in ("nul", "prn", "con", "aux", "com1", "lpt1"):
                if low != "nul":
                    self._warn(lineno, f"设备 {inner} 已替换为 /dev/null", target, category="path")
                converted = "/dev/null"
            else:
                converted = convert_backslashes(self._expand_vars(inner, lineno))
            if quote or re.search(r"\s", converted):
                converted = dq(converted)
            parts.append(f"{op}{converted}")
        return " ".join(parts)

    @staticmethod
    def _split_switches(args: str) -> tuple[set[str], list[str]]:
        flags: set[str] = set()
        rest: list[str] = []
        for token in tokenize_args(args):
            if re.fullmatch(r"/[a-z]{1,3}", token, re.I):
                flags.add(token.lower())
            else:
                rest.append(token)
        return flags, rest

    # ------------------------------------------------------------------
    # 具体命令处理器
    # ------------------------------------------------------------------
    def cmd_noop(self, lineno: int, args: str, original: str) -> None:
        return None

    def cmd_todo_hint(self, lineno: int, args: str, original: str) -> None:
        hint = rules.BATCH_TODO_COMMANDS.get(self._current_command, "")
        self._todo(lineno, original, hint, category="command")
        return None

    def cmd_echo(self, lineno: int, args: str, original: str) -> str:
        text = convert_backslashes(self._expand_vars(args, lineno))
        if not text or text in (".", "(", ")"):
            command = "echo"
        elif is_fully_quoted(text):
            command = f"echo {text}"
        elif "$(" in text:
            command = f'echo "{text}"'
        else:
            command = f"echo {dq(text)}"
        return command.replace(_DOLLAR_PLACEHOLDER, "\\$")

    def cmd_pause(self, lineno: int, args: str, original: str) -> str:
        return guard_read('read -rp "Press Enter to continue..."', self.settings.strict_mode)

    def cmd_cls(self, lineno: int, args: str, original: str) -> str:
        return "clear"

    def cmd_cd(self, lineno: int, args: str, original: str) -> str:
        args = re.sub(r"(?i)^/d\s*", "", args.strip())
        if not args:
            return "pwd"
        return "cd " + self._convert_path_token(args, lineno)

    def cmd_dir(self, lineno: int, args: str, original: str) -> str:
        flags, paths = self._split_switches(args)
        known = {"/b", "/s"}
        for flag in sorted(flags - known):
            self._warn(lineno, f"dir 开关 {flag} 已忽略", original, category="command")
        if "/b" in flags:
            base = "ls -1"
        elif "/s" in flags:
            base = "ls -laR"
        else:
            base = "ls -la"
        path = " ".join(self._convert_path_token(p, lineno) for p in paths)
        return (base + " " + path).strip()

    def cmd_del(self, lineno: int, args: str, original: str) -> str:
        flags, targets = self._split_switches(args)
        for flag in sorted(flags - {"/q", "/f", "/s"}):
            self._warn(lineno, f"del 开关 {flag} 未处理", original, category="command")
        command = "rm -rf" if "/s" in flags else "rm -f"
        paths = " ".join(self._convert_path_token(t, lineno) for t in targets)
        return (command + " " + paths).strip()

    def cmd_rmdir(self, lineno: int, args: str, original: str) -> str:
        flags, targets = self._split_switches(args)
        command = "rm -rf" if "/s" in flags else "rmdir"
        for flag in sorted(flags - {"/s", "/q"}):
            self._warn(lineno, f"rmdir 开关 {flag} 未处理", original, category="command")
        paths = " ".join(self._convert_path_token(t, lineno) for t in targets)
        return (command + " " + paths).strip()

    def cmd_copy(self, lineno: int, args: str, original: str) -> str:
        flags, targets = self._split_switches(args)
        command = "cp -f" if "/y" in flags else "cp"
        for flag in sorted(flags - {"/y", "/v"}):
            self._warn(lineno, f"copy 开关 {flag} 未处理", original, category="command")
        paths = " ".join(self._convert_path_token(t, lineno) for t in targets)
        return (command + " " + paths).strip()

    def cmd_move(self, lineno: int, args: str, original: str) -> str:
        flags, targets = self._split_switches(args)
        command = "mv -f" if "/y" in flags else "mv"
        paths = " ".join(self._convert_path_token(t, lineno) for t in targets)
        return (command + " " + paths).strip()

    def cmd_xcopy(self, lineno: int, args: str, original: str) -> str:
        flags, targets = self._split_switches(args)
        if flags - {"/e", "/i", "/y", "/s", "/q", "/h", "/r", "/c", "/k"}:
            self._warn(lineno, "xcopy 的部分开关已忽略，请检查复制行为", original, category="command")
        paths = " ".join(self._convert_path_token(t, lineno) for t in targets)
        return ("cp -r " + paths).strip()

    def cmd_robocopy(self, lineno: int, args: str, original: str) -> str:
        self._warn(lineno, "robocopy 已转换为 rsync -a，请检查选项语义", original, category="command")
        expanded = self._expand_vars(convert_backslashes(args), lineno)
        return ("rsync -a " + expanded).strip()

    def cmd_start(self, lineno: int, args: str, original: str) -> str | None:
        tokens = tokenize_args(args)
        wait = False
        while tokens and tokens[0].lower().startswith("/"):
            flag = tokens.pop(0).lower()
            if flag == "/wait":
                wait = True
        if tokens and tokens[0].strip("\"'") == "":
            tokens.pop(0)
        if not tokens:
            self._warn(lineno, "start 没有可启动的目标", original, category="command")
            return None
        target_inner, _ = strip_outer_quotes(tokens[0])
        target = convert_backslashes(self._expand_vars(target_inner, lineno))
        rest = " ".join(
            tokenize_args(self._expand_vars(convert_backslashes(" ".join(tokens[1:])), lineno))
        )
        is_path = (
            "\\" in tokens[0]
            or "/" in target_inner
            or "%" in tokens[0]
            or ":" in target_inner
            or target_inner.startswith(("$", "~", "./", "../"))
            or target_inner.endswith((".txt", ".pdf", ".html", ".url", ".lnk"))
        )
        self._warn(lineno, "start 的语义与 xdg-open/后台执行不完全一致，请检查", original, category="command")
        if is_path:
            command = f"xdg-open {dq(target)}"
            if not wait:
                command += " &"
            return command
        command = (target + " " + rest).strip()
        if wait:
            return command
        return f"nohup {command} >/dev/null 2>&1 &"

    def cmd_timeout(self, lineno: int, args: str, original: str) -> str:
        m = re.search(r"(?i)/t\s+(\d+)", args)
        seconds = m.group(1) if m else "5"
        if "/nobreak" not in args.lower():
            self._warn(lineno, "timeout 在等待期间可按键跳过，sleep 不能，请确认", original, category="command")
        return f"sleep {seconds}"

    def cmd_ping(self, lineno: int, args: str, original: str) -> str:
        tokens = tokenize_args(args)
        out: list[str] = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            low = token.lower()
            if low == "-n" and i + 1 < len(tokens):
                out.append("-c")
                out.append(tokens[i + 1])
                i += 2
                continue
            if low == "-w" and i + 1 < len(tokens):
                try:
                    seconds = max(1, round(int(tokens[i + 1]) / 1000))
                except ValueError:
                    seconds = 1
                self._warn(lineno, "ping -w（毫秒）已转换为 -W（秒，向上取整）", original, category="command")
                out.append("-W")
                out.append(str(seconds))
                i += 2
                continue
            if low == "-l" and i + 1 < len(tokens):
                out.append("-s")
                out.append(tokens[i + 1])
                i += 2
                continue
            if low == "-t":
                self._warn(lineno, "ping -t 无限 ping 在 Linux 中为默认行为", original, category="command")
                i += 1
                continue
            out.append(convert_backslashes(self._expand_vars(token, lineno)))
            i += 1
        return ("ping " + " ".join(out)).strip()

    def cmd_ipconfig(self, lineno: int, args: str, original: str) -> str:
        self._warn(lineno, "ipconfig 已转换为 ip addr，输出格式不同", original, category="command")
        return "ip addr show" if "/all" in args.lower() else "ip addr"

    def cmd_netstat(self, lineno: int, args: str, original: str) -> str:
        self._warn(lineno, "netstat 已转换为 ss，输出格式不同", original, category="command")
        return "ss -tuln"

    def cmd_tasklist(self, lineno: int, args: str, original: str) -> str:
        self._warn(lineno, "tasklist 已转换为 ps aux，输出格式不同", original, category="command")
        return "ps aux"

    def cmd_taskkill(self, lineno: int, args: str, original: str) -> str:
        tokens = tokenize_args(args)
        name = None
        pid = None
        i = 0
        while i < len(tokens):
            low = tokens[i].lower()
            if low == "/im" and i + 1 < len(tokens):
                name = tokens[i + 1].strip("\"'")
                i += 2
                continue
            if low == "/pid" and i + 1 < len(tokens):
                pid = tokens[i + 1]
                i += 2
                continue
            i += 1
        if pid:
            return f"kill {pid}"
        if name:
            name = re.sub(r"(?i)\.exe$", "", name)
            return f'pkill -f {dq(name)}'
        self._warn(lineno, "无法解析 taskkill 参数", original, category="command")
        return "pkill"

    def cmd_find(self, lineno: int, args: str, original: str) -> str:
        flags, rest = self._split_switches(args)
        opts = ""
        if "/i" in flags:
            opts += "i"
        if "/v" in flags:
            opts += "v"
        if "/c" in flags:
            opts += "c"
        if "/n" in flags:
            opts += "n"
        pattern = rest[0] if rest else '""'
        files = " ".join(self._convert_path_token(t, lineno) for t in rest[1:])
        self._warn(lineno, "find 已转换为 grep -F（字面量匹配）", original, category="command")
        opt_text = f"-{opts} " if opts else ""
        return (f"grep -F {opt_text}".rstrip() + " " + pattern + " " + files).strip()

    def cmd_findstr(self, lineno: int, args: str, original: str) -> str:
        tokens = tokenize_args(args)
        opts = ""
        pattern = None
        files: list[str] = []
        fixed = False
        for token in tokens:
            low = token.lower()
            if low == "/i":
                opts += "i"
            elif low == "/v":
                opts += "v"
            elif low == "/n":
                opts += "n"
            elif low == "/s":
                opts += "r"
                self._warn(lineno, "findstr /s（递归）已转换为 grep -r", original, category="command")
            elif low == "/r":
                pass
            elif low.startswith("/c:"):
                fixed = True
                pattern = token[3:]
            elif low in ("/b", "/e", "/m", "/o", "/p", "/f:"):
                self._warn(lineno, f"findstr 开关 {token} 未处理", original, category="command")
            elif pattern is None:
                pattern = token
            else:
                files.append(token)
        opt_text = f"-{opts} " if opts else ""
        fixed_text = "-F " if fixed else ""
        files_text = " ".join(self._convert_path_token(t, lineno) for t in files)
        self._warn(lineno, "findstr 已转换为 grep，正则语法可能存在差异", original, category="command")
        pattern = pattern or '""'
        return (f"grep {fixed_text}{opt_text}".rstrip() + f" {pattern} {files_text}").strip()

    def cmd_set(self, lineno: int, args: str, original: str) -> str | None:
        m = re.match(r"(?i)^/a\s+(.*)$", args, re.S)
        if m:
            spec, _quote = strip_outer_quotes(m.group(1).strip())
            assign = re.match(r"^([\w.]+)\s*([+\-*/%]?=)\s*(.*)$", spec, re.S)
            if assign:
                return self._set_arithmetic(lineno, assign, original)
            # 无赋值：cmd 会显示表达式/变量的当前数值
            expr = self._expand_vars(spec, lineno)
            return f"echo $(( {expr} ))"
        m = re.match(r"(?i)^/p\s+(.*)$", args)
        if m:
            spec = m.group(1).strip()
            var, _, prompt = spec.partition("=")
            name = sanitize_identifier(var.strip().strip('"'))
            prompt_text = convert_backslashes(self._expand_vars(prompt.strip().strip('"'), lineno))
            return guard_read(f"read -rp {dq(prompt_text)} {name}", self.settings.strict_mode)
        m = re.match(r'^"([^"=]+)=(.*)"\s*$', args)
        if m:
            var, value = m.group(1), m.group(2)
        else:
            m = re.match(r"^([^=]+)=(.*)$", args, re.S)
            if m:
                var, value = m.group(1).strip(), m.group(2)
            else:
                if not args.strip():
                    return "env"
                return "env | grep -E " + dq("^" + re.escape(args.strip()))
        raw_var = var.strip()
        name = sanitize_identifier(raw_var)
        if name != raw_var:
            self._warn(lineno, f"变量名 {raw_var!r} 已重命名为 {name}", original, category="variables")
        value = convert_backslashes(self._expand_vars(value.rstrip(), lineno))
        if self.settings.quote_variables or value == "" or re.search(r"[\s$&|()<>]", value):
            return f"{name}={dq(value)}"
        return f"{name}={value}"

    def _set_arithmetic(self, lineno: int, m: re.Match[str], original: str) -> str:
        name = sanitize_identifier(m.group(1))
        op = m.group(2)
        expr = m.group(3).strip()
        expr = self._expand_vars(expr, lineno)
        if "!" in expr:
            expr = expr.replace("!", "~")
            self._warn(lineno, "set /a 的按位取反 ! 已转换为 ~", original, category="variables")
        if "," in expr:
            self._warn(lineno, "set /a 多表达式（逗号）仅转换了第一部分", original, category="variables")
            expr = expr.split(",")[0]
        if op == "=":
            return f"{name}=$(( {expr} ))"
        return f"{name}=$(( {name} {op[0]} ({expr}) ))"

    def cmd_setx(self, lineno: int, args: str, original: str) -> str:
        m = re.match(r'^"?([^"\s]+)"?\s+(.*)$', args.strip())
        if not m:
            self._todo(lineno, original, "setx 语法无法解析", category="variables")
            return ""
        name = sanitize_identifier(m.group(1))
        value = convert_backslashes(self._expand_vars(m.group(2).strip().strip('"'), lineno))
        self._warn(lineno, "setx 写入的是持久环境变量，bash 中 export 仅对当前会话生效", original, category="variables")
        return f"export {name}={dq(value)}"

    def cmd_shutdown(self, lineno: int, args: str, original: str) -> str:
        low = args.lower()
        if "/s" in low:
            self._warn(lineno, "关机命令已转换为 systemctl poweroff", original, category="command")
            return "systemctl poweroff"
        if "/r" in low:
            self._warn(lineno, "重启命令已转换为 systemctl reboot", original, category="command")
            return "systemctl reboot"
        if "/l" in low:
            self._warn(lineno, "注销命令已转换为 loginctl terminate-session", original, category="command")
            return "loginctl terminate-user \"$USER\""
        self._warn(lineno, "无法解析 shutdown 参数", original, category="command")
        return "systemctl poweroff"

    def cmd_powershell(self, lineno: int, args: str, original: str) -> str:
        self._warn(lineno, "已转换为 pwsh，请确认已安装 PowerShell 且参数引用正确", original, category="command")
        return ("pwsh " + args).strip()

    def cmd_cmd(self, lineno: int, args: str, original: str) -> str:
        m = re.match(r"(?i)^/c\s+(.*)$", args)
        if m:
            inner = self._expand_vars(m.group(1), lineno)
            self._warn(lineno, "cmd /c 已转换为 bash -c，请检查引号嵌套", original, category="command")
            return f"bash -c {dq(inner)}"
        self._warn(lineno, "cmd /k 交互式命令无法自动转换", original, category="command")
        return "bash"

    def cmd_runas(self, lineno: int, args: str, original: str) -> str:
        self._warn(lineno, "runas 已转换为 sudo，请确认权限配置", original, category="command")
        return ("sudo " + self._expand_vars(convert_backslashes(args), lineno)).strip()

    def cmd_ver(self, lineno: int, args: str, original: str) -> str:
        self._warn(lineno, "ver 已转换为 uname -a", original, category="command")
        return "uname -a"

    def cmd_systeminfo(self, lineno: int, args: str, original: str) -> str:
        self._warn(lineno, "systeminfo 已转换为 uname -a，信息量不同", original, category="command")
        return "uname -a"

    def cmd_certutil(self, lineno: int, args: str, original: str) -> str | None:
        tokens = tokenize_args(args)
        if len(tokens) < 3 or tokens[0].lower() != "-hashfile":
            return self._todo(
                lineno,
                original,
                "certutil 仅支持 -hashfile <文件> MD5/SHA256 形式",
                category="command",
            )
        algorithm = tokens[2].lower()
        mapped = {"md5": "md5sum", "sha256": "sha256sum"}.get(algorithm)
        if mapped is None:
            return self._todo(
                lineno,
                original,
                f"certutil 哈希算法 {tokens[2]} 无法映射（仅支持 MD5/SHA256）",
                category="command",
            )
        self._warn(
            lineno,
            f"certutil -hashfile 已转换为 {mapped}，输出格式不同（无 CertUtil 头部与指纹格式）",
            original,
            category="command",
        )
        return f"{mapped} {self._convert_path_token(tokens[1], lineno)}"

    def cmd_driverquery(self, lineno: int, args: str, original: str) -> str:
        if args.strip():
            self._warn(
                lineno,
                f"driverquery 参数 {args.strip()} 已忽略（Linux 无对应过滤）",
                original,
                category="command",
            )
        self._warn(
            lineno,
            "driverquery 已转换为 lsmod，语义不同（仅内核模块，无驱动服务详情）",
            original,
            category="command",
        )
        return "lsmod"

    def cmd_assoc(self, lineno: int, args: str, original: str) -> str | None:
        token = args.strip()
        if not token or "=" in token:
            return self._todo(
                lineno, original, "assoc 仅支持查询单个扩展名（assoc .ext）", category="command"
            )
        mime = rules.BATCH_EXT_MIME.get(token.lower())
        if mime is None:
            return self._todo(
                lineno, original, f"扩展名 {token} 无 MIME 映射", category="command"
            )
        self._warn(
            lineno,
            "assoc 已转换为 xdg-mime query default，输出为 .desktop 名称而非命令",
            original,
            category="command",
        )
        return f"xdg-mime query default {mime}"

    def cmd_ftype(self, lineno: int, args: str, original: str) -> str | None:
        token = args.strip().strip('"')
        if not token or "=" in token:
            return self._todo(
                lineno, original, "ftype 仅支持查询单个文件类型名（ftype name）", category="command"
            )
        mime = rules.BATCH_FTYPE_MIME.get(token.lower())
        if mime is None:
            return self._todo(
                lineno, original, f"文件类型 {token} 无 MIME 映射", category="command"
            )
        self._warn(
            lineno,
            "ftype 已转换为 xdg-mime query default，输出为 .desktop 名称而非命令",
            original,
            category="command",
        )
        return f"xdg-mime query default {mime}"

    def cmd_choice(self, lineno: int, args: str, original: str) -> str:
        self._todo(lineno, original, "choice 请改用 read -r -n 1 或 zenity", category="command")
        return ""

    def cmd_if_unsupported(self, lineno: int, args: str, original: str) -> None:  # pragma: no cover
        return None

    # ------------------------------------------------------------------
    # 收尾
    # ------------------------------------------------------------------
    def _finish(self) -> None:
        while self._stack:
            block = self._stack.pop()
            if block.kind == "comment":
                continue
            self._warn(0, f"{block.kind} 块未正常闭合，已自动补全", category="misc")
            if block.close_word:
                self._out.append(block.close_word)
        if self._current_func:
            self._trim_function_tail()
            self._func_out.append("}")
            self._current_func = None
