"""PowerShell (.ps1) -> Bash 转换器。

同样采用"逐逻辑行 + 花括号块栈"的方式：
* 反引号续行、here-string、块注释先归一化处理；
* ``if/elseif/else``、``foreach``、``while``、``for``、``function``、
  ``try/catch/finally`` 通过花括号栈转换为 bash 结构；
* 变量名大小写不敏感：预扫描收集变量，统一为首次出现的写法；
* 无法自动转换的语句生成 ``# TODO: 手动检查: ...``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import rules
from .settings import ConvertSettings
from .syntax import bash_syntax_error, degraded_script, record_syntax_error
from .types import ConvertReport, Diagnostic, SourceKind
from .utils import (
    convert_backslashes,
    dq,
    find_matching,
    guard_read,
    has_set_e,
    is_named_arg,
    needs_nullglob,
    resolve_named_args,
    sanitize_identifier,
    simple_glob_to_regex,
    split_top_level,
    sq,
    strip_leading_attributes,
    strip_outer_quotes,
    tokenize_args,
)

_PS_VAR_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_COMPARE_OP_RE = re.compile(r"(?<![\w-])(-eq|-ne|-gt|-lt|-ge|-le|-ceq|-cne|-ieq|-ine)(?![\w-])", re.I)
_LIKE_OP_RE = re.compile(r"(?<![\w-])(-like|-notlike|-clike|-ilike)(?![\w-])", re.I)
_MATCH_OP_RE = re.compile(r"(?<![\w-])(-match|-notmatch|-cmatch|-imatch)(?![\w-])", re.I)
_LOGIC_OP_RE = re.compile(r"(?<![\w-])(-and|-or|-not|-xor)(?![\w-])", re.I)
_LASTEXITCODE_RE = re.compile(r"(?i)\$\{LASTEXITCODE\}|\$LASTEXITCODE\b")
_PS_ATTRIBUTE_NAMES = frozenset({"cmdletbinding", "parameter", "alias", "outputtype"})
_PS_TYPE_NAMES = frozenset({
    "string", "int", "int32", "int64", "bool", "double", "float", "decimal",
    "array", "hashtable", "datetime", "guid", "char", "byte",
})
_ATTR_BUFFER_LIMIT = 40


@dataclass
class _Block:
    kind: str          # if / else / for / while / function / try / catch / finally / do / group / comment
    close_word: str = "fi"
    brace_depth: int = 1
    body_mark: int = -1


class PowerShellConverter:
    """把 PowerShell 脚本转换为 bash 脚本。"""

    def __init__(self, settings: ConvertSettings, source_name: str = "input.ps1"):
        self.settings = settings
        self.source_name = source_name
        self.report = ConvertReport(source=source_name, kind=SourceKind.POWERSHELL)
        self._out: list[str] = []
        self._stack: list[_Block] = []
        self._var_map: dict[str, str] = {}
        self._function_map: dict[str, str] = {}
        self._function_params: dict[str, list[str]] = {}
        self._needs_script_dir = False
        self._needs_nullglob = False
        self._needs_join_path = False
        self._here_end: str | None = None
        self._here_lines: list[str] = []
        self._here_lineno = 0
        self._here_interpolate = False
        self._here_mode = "standalone"
        self._here_target = ""
        self._block_comment = False
        self._param_buffer: list[str] | None = None
        self._attr_buffer: list[str] | None = None
        self._pipe_buffer: list[str] | None = None
        self._array_vars: set[str] = set()
        self._todo_reason = ""
        self._condition_fallback = ""
        self._current_cmdlet = ""
        self._pipe_comments: list[str] = []
        self._try_buffer: list[str] | None = None
        self._try_lineno = 0
        self._try_depth = 0
        self._try_inline_pending = False
        self._rc_captured = False
        self._rc_scope: _Block | None = None

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    def convert(self, text: str) -> str:
        logical = self._logical_lines(text)
        self.report.total_lines = len(logical)
        self._prescan(logical)
        for start, line in logical:
            produced = self._dispatch_line(start, line)
            self._out.extend(produced)
            if not line.strip():
                continue
            if produced and any(
                p.strip() and not p.lstrip().startswith("#") for p in produced
            ):
                self.report.converted_lines += 1
            else:
                self.report.unchanged_lines += 1
        self._finish()
        output = self._compose()
        if self.settings.bash_check:
            syntax_error = bash_syntax_error(output)
            if syntax_error is not None:
                record_syntax_error(self.report, syntax_error)
                return degraded_script(text, self.source_name, syntax_error)
        return output

    # ------------------------------------------------------------------
    # 基础工具
    # ------------------------------------------------------------------
    @property
    def _indent(self) -> str:
        return self.settings.indent * len(self._stack)

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
        return "# TODO: 手动检查: " + original

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
            if stripped.endswith("`") and not stripped.endswith("``"):
                buf = stripped[:-1]
                continue
            result.append((start, line))
        if buf:
            result.append((start, buf))
        return result

    def _prescan(self, logical: list[tuple[int, str]]) -> None:
        joined = "\n".join(line for _, line in logical)
        for m in _PS_VAR_RE.finditer(joined):
            name = m.group(1)
            low = name.lower()
            if low in rules.PS_AUTOMATIC_VARS or low in rules.PS_TODO_VARS:
                continue
            if low not in self._var_map:
                self._var_map[low] = name
        for m in re.finditer(r"(?i)\bfunction\s+([\w:.-]+)", joined):
            raw = m.group(1)
            low = raw.lower()
            if low not in self._function_map:
                self._function_map[low] = sanitize_identifier(raw)
        self._scan_function_params(joined)
        if re.search(r"\$PSScriptRoot|\$PSCommandPath", joined, re.I):
            self._needs_script_dir = True

    def _scan_function_params(self, joined: str) -> None:
        """记录每个函数的参数声明顺序，用于把命名参数调用改写为位置参数。"""
        for m in re.finditer(r"(?i)\bfunction\s+([\w:.-]+)", joined):
            low = m.group(1).lower()
            if low in self._function_params:
                continue
            window = joined[m.end():]
            following = re.search(r"(?i)\bfunction\s+[\w:.-]+", window)
            body = window[: following.start()] if following else window
            names: list[str] = []
            if body.lstrip().startswith("("):
                start = body.find("(")
                close = find_matching(body, "(", ")", start)
                if close > start:
                    names = self._param_names(body[start + 1:close])
            else:
                param = re.search(r"(?i)\bparam\s*\(", body)
                if param:
                    start = param.end() - 1
                    close = find_matching(body, "(", ")", start)
                    if close > start:
                        names = self._param_names(body[start + 1:close])
            if names:
                self._function_params[low] = names

    @staticmethod
    def _param_names(interior: str) -> list[str]:
        names: list[str] = []
        for raw in split_top_level(interior, ","):
            raw = raw.strip()
            if not raw:
                continue
            _, decl = strip_leading_attributes(raw)
            found = re.search(r"\$(\w+)", decl)
            if found:
                names.append(found.group(1))
        return names

    def _compose(self) -> str:
        header = ["#!/usr/bin/env bash"]
        header.append(f"# 由 bat2sh 自动转换生成，源文件: {self.source_name}")
        header.append("# 带有 # TODO 标记的行无法自动转换，请人工检查")
        if self.settings.strict_mode:
            header.append("set -euo pipefail")
        if self._needs_nullglob:
            header.append("# 检测到通配符匹配：已启用 nullglob，无匹配时数组为空、循环体不执行")
            header.append("shopt -s nullglob")
        if self._needs_script_dir:
            header.append('SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"')
        if self._needs_join_path:
            header.append("")
            header.append("# Join-Path 辅助函数：子路径为绝对路径时重置（对齐 PowerShell/.NET Path.Combine 语义）")
            header.append("__bat2sh_join_path() {")
            header.append('    local __result="" __part')
            header.append('    for __part in "$@"; do')
            header.append(
                '        if [[ "${__part}" == /* || "${__part}" == [A-Za-z]:/*'
                ' || "${__part}" == [A-Za-z]:\\\\* ]]; then'
            )
            header.append('            __result="${__part}"')
            header.append('        elif [[ -z "${__result}" || "${__result}" == */ ]]; then')
            header.append('            __result="${__result}${__part}"')
            header.append("        else")
            header.append('            __result="${__result}/${__part}"')
            header.append("        fi")
            header.append("    done")
            header.append("    printf '%s' \"${__result}\"")
            header.append("}")
        header.append("")
        body = "\n".join(self._out).rstrip()
        return "\n".join(header) + body + "\n"

    # ------------------------------------------------------------------
    # 变量处理
    # ------------------------------------------------------------------
    def _canonical(self, name: str) -> str:
        low = name.lower()
        if low in rules.PS_AUTOMATIC_VARS:
            return rules.PS_AUTOMATIC_VARS[low]
        if low in rules.PS_TODO_VARS:
            return "${%s}" % name
        return "${%s}" % self._var_map.get(low, name)

    def _replace_vars(self, text: str, lineno: int) -> str:
        """替换变量，单引号内的内容不做替换。"""
        result: list[str] = []
        i = 0
        n = len(text)
        quote = ""
        while i < n:
            c = text[i]
            if quote == "'":
                if c == "'" and not text.startswith("''", i):
                    quote = ""
                result.append(c)
                i += 1
                continue
            if quote == '"':
                if c == "`" and i + 1 < n:
                    result.append(c)
                    result.append(text[i + 1])
                    i += 2
                    continue
                if c == '"':
                    quote = ""
                    result.append(c)
                    i += 1
                    continue
                if c == "$":
                    consumed = self._replace_var_at(text, i, result, lineno)
                    i += consumed
                    continue
                result.append(c)
                i += 1
                continue
            if c in "\"'":
                quote = c
                result.append(c)
                i += 1
                continue
            if c == "$":
                consumed = self._replace_var_at(text, i, result, lineno)
                i += consumed
                continue
            if c == "`" and i + 1 < n:
                result.append(c)
                result.append(text[i + 1])
                i += 2
                continue
            result.append(c)
            i += 1
        return "".join(result)

    def _replace_var_at(self, text: str, i: int, result: list[str], lineno: int) -> int:
        """处理 text[i] == '$'，返回消费的字符数。"""
        n = len(text)
        # $(
        if i + 1 < n and text[i + 1] == "(":
            close = find_matching(text, "(", ")", i + 1)
            if close < 0:
                result.append("$(")
                return 2
            inner = text[i + 2:close]
            converted = self._convert_subexpression(inner, lineno)
            result.append("$(" + converted + ")")
            return close - i + 1
        # $env:NAME / $global:x 等
        m = re.match(r"\$(env|global|script|local|private|using):([A-Za-z_][\w]*)", text[i:], re.I)
        if m:
            self._append_scoped_var(
                m.group(1).lower(), m.group(2), text[i:i + m.end()], result, lineno
            )
            return m.end()
        # ${env:NAME} / ${global:x} 等花括号形式
        m = re.match(
            r"\$\{(env|global|script|local|private|using):([A-Za-z_][\w]*)\}",
            text[i:],
            re.I,
        )
        if m:
            self._append_scoped_var(
                m.group(1).lower(), m.group(2), text[i:i + m.end()], result, lineno
            )
            return m.end()
        # ${name}
        m = re.match(r"\$\{([A-Za-z_][\w]*)\}", text[i:])
        if m:
            name = m.group(1)
            low = name.lower()
            if low == "lastexitcode":
                self._last_exit_code_safe_ref(name, result, lineno)
                return m.end()
            if low in rules.PS_AUTOMATIC_VARS or low in rules.PS_TODO_VARS:
                self._automatic_var(name, result, lineno)
                return m.end()
            result.append(self._canonical(name))
            return m.end()
        # $arr[0]
        m = re.match(r"\$([A-Za-z_][\w]*)\[", text[i:])
        if m:
            name = m.group(1)
            result.append("${%s}[" % self._var_map.get(name.lower(), name))
            return m.end() - 1
        # $name
        m = re.match(r"\$([A-Za-z_][\w]*)", text[i:])
        if m:
            name = m.group(1)
            return self._automatic_var(name, result, lineno)
        # $? / $$ / $_ 等
        if i + 1 < n and text[i + 1] == "?":
            self._warn(
                lineno,
                "bash 的 $? 只反映紧邻上一条命令的退出码，"
                "与 PowerShell 的 $? 语义不同，请人工确认",
                "$?",
                category="errorlevel",
            )
            result.append("$?")
            return 2
        if i + 1 < n and text[i + 1] in "$!":
            result.append("$" + text[i + 1])
            return 2
        if i + 1 < n and text[i + 1] == "_":
            result.append("$_")
            self._todo_reason = "$_（管道当前对象）在 bash 中无直接对应物"
            return 2
        result.append("$")
        return 1

    def _append_scoped_var(
        self,
        scope: str,
        name: str,
        raw: str,
        result: list[str],
        lineno: int,
    ) -> None:
        if scope == "env":
            key = name.lower()
            if key in rules.PS_ENV_MAP:
                mapped = rules.PS_ENV_MAP[key]
                result.append(mapped)
                if key in rules.PS_ENV_WARN:
                    self._warn(
                        lineno,
                        f"$env:{name} 已近似映射为 {mapped}，"
                        "Windows 与 Linux 的默认位置不同，请确认路径",
                        raw,
                        category="variables",
                    )
            else:
                result.append("${%s}" % name)
                self._warn(
                    lineno,
                    f"$env:{name} 未收录映射，已原样保留为 ${{{name}}}；"
                    "严格模式（set -u）下变量未设置会直接报错，请显式给默认值或改为脚本变量",
                    raw,
                    category="variables",
                )
        elif scope == "using":
            result.append("${%s}" % name)
            self._warn(
                lineno,
                "$using: 跨会话变量在 bash 中无对应物",
                raw,
                category="variables",
            )
        else:
            result.append("${%s}" % self._var_map.get(name.lower(), name))
            self._warn(
                lineno,
                f"${scope}: 作用域限定符已省略（bash 无对应作用域）",
                raw,
                category="variables",
            )

    def _automatic_var(self, name: str, result: list[str], lineno: int) -> int:
        low = name.lower()
        if low == "lastexitcode":
            self._last_exit_code_safe_ref(name, result, lineno)
            return 1 + len(name)
        if low in rules.PS_AUTOMATIC_VARS:
            mapped = rules.PS_AUTOMATIC_VARS[low]
            result.append(mapped)
            if low == "psscriptroot":
                self._needs_script_dir = True
            return 1 + len(name)
        if low in rules.PS_TODO_VARS:
            result.append("${%s}" % name)
            self._todo_reason = rules.PS_TODO_VARS[low]
            return 1 + len(name)
        result.append(self._canonical(name))
        return 1 + len(name)

    def _replace_last_exit_code(self, text: str, replacement: str) -> tuple[str, bool]:
        """替换单引号外的 $LASTEXITCODE / ${LASTEXITCODE}；返回 (文本, 是否命中)。"""
        result: list[str] = []
        i = 0
        n = len(text)
        quote = ""
        found = False
        while i < n:
            c = text[i]
            if quote == "'":
                if c == "'" and not text.startswith("''", i):
                    quote = ""
                result.append(c)
                i += 1
                continue
            if quote == '"':
                if c == "`" and i + 1 < n:
                    result.append(c)
                    result.append(text[i + 1])
                    i += 2
                    continue
                if c == '"':
                    quote = ""
                    result.append(c)
                    i += 1
                    continue
                if c == "$":
                    m = _LASTEXITCODE_RE.match(text, i)
                    if m:
                        result.append(replacement)
                        found = True
                        i = m.end()
                        continue
                result.append(c)
                i += 1
                continue
            if c in "\"'":
                quote = c
                result.append(c)
                i += 1
                continue
            if c == "$":
                m = _LASTEXITCODE_RE.match(text, i)
                if m:
                    result.append(replacement)
                    found = True
                    i = m.end()
                    continue
            result.append(c)
            i += 1
        return "".join(result), found

    def _enclosing_function_block(self) -> "_Block | None":
        for block in reversed(self._stack):
            if block.kind == "function":
                return block
        return None

    def _emit_last_exit_code_warn(self, lineno: int, text: str) -> list[str]:
        header = self._match_condition_header(text)
        if header is not None:
            keyword, _cond, inline, block_open = header
            self._todo(
                lineno,
                text,
                "$LASTEXITCODE 条件已置为 false（warn 策略，语义与 bash $? 不同）",
                category="errorlevel",
            )
            lines = self._emit_condition_block(
                lineno, text, keyword, "false", inline, block_open
            )
            if lines:
                lines[0] += "  # TODO: 手动检查 $LASTEXITCODE 条件"
            return lines
        return [
            self._c(
                self._todo(
                    lineno,
                    text,
                    "warn 策略：$LASTEXITCODE 无法安全映射，请人工处理",
                    category="errorlevel",
                )
            )
        ]

    def _emit_last_exit_code_map(self, lineno: int, text: str) -> list[str]:
        replaced, _ = self._replace_last_exit_code(text, "${__bat2sh_rc}")
        scope = self._enclosing_function_block()
        prefix: list[str] = []
        if not self._rc_captured:
            self._rc_captured = True
            self._rc_scope = scope
            prefix = [
                self._c("# 近似: $LASTEXITCODE 在首次引用处捕获为 __bat2sh_rc（$? 语义相近）"),
                self._c("__bat2sh_rc=$?"),
            ]
            self._warn(
                lineno,
                "map 策略：$LASTEXITCODE 已近似映射为 __bat2sh_rc（首次引用处捕获 $?），请人工复核",
                text,
                category="errorlevel",
            )
        elif scope is not self._rc_scope:
            self._warn(
                lineno,
                "map 策略：跨函数/跨作用域的 $LASTEXITCODE 无法确定捕获点，已退回 warn",
                text,
                category="errorlevel",
            )
            return [
                self._c(
                    self._todo(
                        lineno,
                        text,
                        "跨作用域，已退回 warn",
                        category="errorlevel",
                    )
                )
            ]
        return prefix + self._convert_statement(lineno, replaced)

    def _last_exit_code_safe_ref(self, name: str, result: list[str], lineno: int) -> None:
        """语句级拦截之外的兜底（如 here-string 插值）：安全引用 + 告警。"""
        if self.settings.last_exit_code == "map":
            result.append("${__bat2sh_rc:-}")
            self._warn(
                lineno,
                "map 策略：此处（如 here-string 插值）无法插入 __bat2sh_rc 捕获，"
                "已用安全引用 ${__bat2sh_rc:-}，请人工确认",
                f"${name}",
                category="errorlevel",
            )
        else:
            result.append("${LASTEXITCODE:-}")
            self._warn(
                lineno,
                "warn 策略：此处（如 here-string 插值）无法整行替换为 TODO，"
                "已用安全空值 ${LASTEXITCODE:-}，请人工确认",
                f"${name}",
                category="errorlevel",
            )

    def _convert_subexpression(self, inner: str, lineno: int) -> str:
        inner = inner.strip()
        if inner.startswith("$") and _PS_VAR_RE.fullmatch(inner) and "." not in inner:
            return inner[1:]
        m = re.match(r"(?i)^(Get-Date)\b(.*)$", inner)
        if m:
            return self._get_date(lineno, m.group(2)).lstrip("$()")
        m = re.match(r"(?i)^(Join-Path|Split-Path|Resolve-Path)\b(.*)$", inner)
        if m:
            return self._path_expr(m.group(1).lower(), m.group(2), lineno).strip("$()")
        return self._replace_vars(inner, lineno)

    def _path_expr(self, name: str, args: str, lineno: int) -> str:
        tokens = tokenize_args(args)
        positional = [t for t in tokens if not t.startswith("-")]
        if name == "join-path":
            parts = [strip_outer_quotes(self._replace_vars(t, lineno))[0] for t in positional]
            parts = [convert_backslashes(p) for p in parts]
            self._needs_join_path = True
            for child in parts[1:]:
                self._warn_join_path_child(lineno, ("Join-Path" + args).strip(), child)
            return "__bat2sh_join_path " + " ".join(dq(p) for p in parts)
        target = positional[0] if positional else '""'
        converted = self._convert_arg(target, lineno)
        if name == "split-path":
            if any(t.lower() == "-leaf" for t in tokens):
                return f"basename {converted}"
            if any(t.lower() == "-parent" for t in tokens):
                return f"dirname {converted}"
            return converted
        return f"realpath {converted}"

    # ------------------------------------------------------------------
    # 表达式
    # ------------------------------------------------------------------
    def _convert_expression(self, expr: str, lineno: int) -> str:
        expr = expr.strip()
        out = self._replace_vars(expr, lineno)
        out = self._expand_inline_cmdlets(out, lineno)
        return out

    def _expand_inline_cmdlets(self, expr: str, lineno: int) -> str:
        changed = True
        guard = 0
        while changed and guard < 20:
            changed = False
            guard += 1
            m = re.search(r"(?i)\bJoin-Path\s+(\S+)\s+(\S+)", expr)
            if m and not m.group(1).startswith("-") and not m.group(2).startswith("-"):
                parts = [self._strip_quotes_for_path(p) for p in (m.group(1), m.group(2))]
                self._needs_join_path = True
                self._warn_join_path_child(lineno, m.group(0), parts[1])
                replacement = "$(__bat2sh_join_path " + " ".join(dq(p) for p in parts) + ")"
                expr = expr[:m.start()] + replacement + expr[m.end():]
                changed = True
                continue
            m = re.search(r"(?i)\bSplit-Path\s+(\S+)\s+-Leaf\b", expr)
            if m:
                target = self._strip_quotes_for_path(m.group(1))
                expr = expr[:m.start()] + f'$(basename {dq(target)})' + expr[m.end():]
                changed = True
                continue
            m = re.search(r"(?i)\bSplit-Path\s+(\S+)\s+-Parent\b", expr)
            if m:
                target = self._strip_quotes_for_path(m.group(1))
                expr = expr[:m.start()] + f'$(dirname {dq(target)})' + expr[m.end():]
                changed = True
                continue
            m = re.search(r"(?i)\bResolve-Path\s+(\S+)", expr)
            if m:
                target = self._strip_quotes_for_path(m.group(1))
                expr = expr[:m.start()] + f'$(realpath {dq(target)})' + expr[m.end():]
                changed = True
                continue
            m = re.search(
                r"(?i)\bGet-Date\b(?:\s+-Format\s+(\"[^\"]*\"|'[^']*'|\S+))?", expr
            )
            if m:
                replacement = self._get_date(lineno, m.group(0))
                expr = expr[:m.start()] + replacement + expr[m.end():]
                changed = True
                continue
        return expr

    def _strip_quotes_for_path(self, token: str) -> str:
        inner, _ = strip_outer_quotes(token)
        return convert_backslashes(self._replace_vars(inner, 0))

    def _get_date(self, lineno: int, args: str) -> str:
        if "-format" not in args.lower():
            return "$(date)"
        m = re.search(r'(?i)-Format\s+("[^"]*"|\'[^\']*\'|\S+)', args)
        if not m:
            return "$(date)"
        raw = m.group(1)
        if raw[:1] not in "\"'":
            self._warn(
                lineno,
                f"无法解析日期格式 {raw!r}（建议加引号），已退化为 $(date)",
                args,
                category="strings",
            )
            return "$(date)"
        fmt = raw[1:-1]
        if not fmt:
            return "$(date)"
        converted = self._ps_date_format(fmt)
        rest = re.sub(r"%[-0-9:]*[A-Za-z%]", "", converted)
        if re.search(r"[A-Za-z]", rest):
            self._warn(
                lineno,
                f"日期格式 {fmt!r} 含不支持的 token，已退化为 $(date)，请人工处理",
                f"Get-Date -Format {fmt}",
                category="strings",
            )
            return "$(date)"
        self._warn(
            lineno,
            f"日期格式 {fmt!r} 已近似转换为 {converted!r}",
            f"Get-Date -Format {fmt}",
            category="strings",
        )
        return f"$(date +{converted})"

    @staticmethod
    def _ps_date_format(fmt: str) -> str:
        result = fmt
        for token, repl in rules.PS_DATE_TOKENS:
            result = result.replace(token, repl)
        return result

    # ------------------------------------------------------------------
    # 分发
    # ------------------------------------------------------------------
    def _dispatch_line(self, lineno: int, raw: str) -> list[str]:
        """try 体缓冲：非边界行只累积，catch/finally/结束花括号才落盘。"""
        if self._try_buffer is None:
            return self._convert_line(lineno, raw)
        stripped = raw.strip()
        boundary = len(self._stack) == self._try_depth and (
            stripped.startswith("}") or bool(re.match(r"(?i)^(catch|finally)\b", stripped))
        )
        if boundary:
            return self._convert_line(lineno, raw)
        if self._try_inline_pending:
            finalized = self._finalize_bare_try()
            return finalized + self._convert_line(lineno, raw)
        self._try_buffer.extend(self._convert_line(lineno, raw))
        return []

    def _finalize_bare_try(self) -> list[str]:
        buffer = self._try_buffer or []
        self._try_buffer = None
        self._try_inline_pending = False
        if self._stack and self._stack[-1].kind == "try":
            self._stack.pop()
        return list(buffer)

    def _convert_line(self, lineno: int, raw: str) -> list[str]:
        if self._here_end is not None:
            return self._collect_here_line(lineno, raw)
        text = raw.strip()
        m = re.match(r'^(?:\$([A-Za-z_]\w*)\s*=\s*)?@(["\'])\s*$', text)
        if m:
            self._here_lineno = lineno
            self._here_end = m.group(2) + "@"
            self._here_interpolate = m.group(2) == '"'
            self._here_lines = []
            if m.group(1):
                self._here_mode = "assign"
                self._here_target = self._var_map.get(m.group(1).lower(), m.group(1))
            else:
                self._here_mode = "standalone"
                self._here_target = ""
            return []
        # 块注释
        if self._block_comment:
            if "#>" in text:
                self._block_comment = False
            return [self._c("# " + text)]
        if text.startswith("<#"):
            self._block_comment = "#>" not in text
            self._warn(lineno, "PowerShell 块注释已转换为行注释", text, category="strings")
            body = text[2:].replace("#>", "").strip()
            return [self._c("# " + body if body else "#")]

        if not text:
            return [""]

        if self._param_buffer is not None:
            self._param_buffer.append(text)
            joined = " ".join(self._param_buffer)
            open_index = joined.find("(")
            if open_index >= 0 and find_matching(joined, "(", ")", open_index) >= 0:
                self._param_buffer = None
                return self._emit_param(lineno, joined)
            return []

        # 注释块内（switch 等）：只做花括号配平
        for block in reversed(self._stack):
            if block.kind == "comment":
                if text.endswith("{"):
                    block.brace_depth += 1
                if text.startswith("}"):
                    block.brace_depth -= 1
                    if block.brace_depth <= 0:
                        self._stack.pop()
                return [self._c("# " + text)]
            break

        if text.startswith("}"):
            return self._close_block_line(lineno, text)
        if text.startswith("#"):
            return [self._c(text)]

        if self._pipe_buffer is not None:
            self._pipe_buffer.append(text)
            joined = " ".join(self._pipe_buffer)
            if joined.rstrip().endswith("|") and not joined.rstrip().endswith("||"):
                return []
            self._pipe_buffer = None
            text = joined
        elif text.endswith("|") and not text.endswith("||"):
            self._pipe_buffer = [text]
            return []

        # 顶层分号拆分为多条语句
        statements = self._split_statements(text)
        if len(statements) > 1:
            out: list[str] = []
            for statement in statements:
                out.extend(self._convert_line(lineno, statement))
            return out
        text = statements[0]

        return self._convert_statement(lineno, text)

    def _collect_here_line(self, lineno: int, raw: str) -> list[str]:
        if raw.strip() != self._here_end:
            self._here_lines.append(raw)
            return []
        marker = '@"' if self._here_interpolate else "@'"
        content = self._here_lines
        self._here_end = None
        self._here_lines = []
        lines = self._emit_here_string(content, marker)
        self._here_mode = "standalone"
        self._here_target = ""
        return lines

    def _emit_here_string(self, content: list[str], marker: str) -> list[str]:
        delimiter = "__BAT2SH_EOF__"
        while any(line == delimiter for line in content):
            delimiter += "_"
        if self._here_interpolate:
            open_token = f"<<{delimiter}"
        else:
            open_token = f"<<'{delimiter}'"
        body: list[str]
        if self._here_interpolate:
            body = []
            for line in content:
                converted = self._replace_vars(line, self._here_lineno)
                converted = converted.replace("`", "\\`")
                converted = re.sub(r"\$(?![{(])", r"\\$", converted)
                body.append(converted)
            self._warn(
                self._here_lineno,
                "here-string 的反斜杠/反引号转义语义与 PowerShell 不同，请核对",
                marker + "（here-string）",
                category="strings",
            )
        else:
            body = list(content)
        lines: list[str] = []
        if self._here_mode == "assign":
            lines.append(self._c(f"{self._here_target}=$(cat {open_token}"))
            self._warn(
                self._here_lineno,
                "赋值形式的 here-string 使用命令替换，会去掉结尾换行，请核对",
                marker + "（here-string）",
                category="strings",
            )
        else:
            lines.append(self._c(f"cat {open_token}"))
        lines.extend(body)
        lines.append(delimiter)
        if self._here_mode == "assign":
            lines.append(self._c(")"))
        return lines

    @staticmethod
    def _split_statements(text: str) -> list[str]:
        parts = split_top_level(text, ";")
        return [p.strip() for p in parts if p.strip()] or [text]

    def _attribute_statement(self, lineno: int, text: str) -> list[str] | None:
        stripped = text.strip()
        if self._attr_buffer is not None:
            self._attr_buffer.append(stripped)
            joined = " ".join(self._attr_buffer)
            if find_matching(joined, "[", "]", 0) >= 0:
                self._attr_buffer = None
                result = self._classify_annotated_statement(lineno, joined)
                if result is not None:
                    return result
                return [self._c(self._todo(lineno, joined, "多行注解无法解析，未转换", category="misc"))]
            if len(self._attr_buffer) >= _ATTR_BUFFER_LIMIT:
                self._attr_buffer = None
                return [self._c(self._todo(lineno, joined, "attribute 块未闭合，无法解析", category="misc"))]
            return []
        if not stripped.startswith("["):
            return None
        m = re.match(r"^\[([A-Za-z_]\w*)\s*\(\s*$", stripped)
        if m and self._is_attribute_name(m.group(1)):
            self._attr_buffer = [stripped]
            return []
        return self._classify_annotated_statement(lineno, stripped)

    @staticmethod
    def _is_attribute_name(name: str) -> bool:
        low = name.lower()
        return low in _PS_ATTRIBUTE_NAMES or low.startswith("validate")

    def _annotation_kind(self, name: str) -> str:
        base = name[:-2] if name.endswith("[]") else name
        low = base.lower()
        if low in _PS_TYPE_NAMES:
            return "type"
        if self._is_attribute_name(low):
            return "attribute"
        return ""

    def _classify_annotated_statement(self, lineno: int, stripped: str) -> list[str] | None:
        groups: list[str] = []
        i = 0
        n = len(stripped)
        while i < n:
            while i < n and stripped[i].isspace():
                i += 1
            if i >= n or stripped[i] != "[":
                break
            close = find_matching(stripped, "[", "]", i)
            if close < 0:
                break
            groups.append(stripped[i + 1:close].strip())
            i = close + 1
        if not groups:
            return None
        rest = stripped[i:].strip()
        if rest.startswith("::"):
            return None
        names: list[str] = []
        for group in groups:
            name_match = re.match(r"^([A-Za-z_][\w.\[\]]*)", group)
            names.append(name_match.group(1) if name_match else group)
        kinds = [self._annotation_kind(name) for name in names]
        if kinds and kinds[-1] == "type":
            if not rest:
                return []
            if re.match(r"^\$[\w]+\s*[+\-*/%]?=", rest):
                return self._convert_statement(lineno, rest)
            return [self._c(self._todo(lineno, stripped, "类型转换在 bash 中无对应物（未做转换）", category="objects"))]
        if all(kind == "attribute" for kind in kinds):
            if not rest:
                return []
            return [self._c(self._todo(lineno, stripped, "语句级属性后的内容无法可靠转换", category="misc"))]
        if rest:
            return [self._c(self._todo(lineno, stripped, f"类型注解 [{names[-1]}] 不在支持列表，未转换", category="objects"))]
        return None

    def _convert_statement(self, lineno: int, text: str) -> list[str]:
        attr_lines = self._attribute_statement(lineno, text)
        if attr_lines is not None:
            return attr_lines
        self._todo_reason = ""

        if self._try_buffer is not None and re.match(r"(?i)^(catch|finally)\b", text):
            return self._close_block_line(lineno, text)

        if self._try_buffer is not None and re.match(r"(?i)^try\b", text):
            self._todo(lineno, text, "嵌套 try 无法自动转换，块内代码已注释", category="control_flow")
            block = _Block("comment", "")
            block.brace_depth = text.count("{") - text.count("}")
            if block.brace_depth <= 0:
                block.brace_depth = 1
            todo_line = self._c("# TODO: 手动检查: " + text)
            self._stack.append(block)
            return [todo_line]

        # 注释
        if text.startswith("#"):
            return [self._c(text)]

        _, has_last_exit = self._replace_last_exit_code(text, "")
        if has_last_exit:
            if self.settings.last_exit_code == "map":
                return self._emit_last_exit_code_map(lineno, text)
            return self._emit_last_exit_code_warn(lineno, text)

        # 块头
        header = self._match_condition_header(text)
        if header is not None:
            keyword, cond, inline, block_open = header
            return self._emit_condition_block(lineno, text, keyword, cond, inline, block_open)

        m = re.match(r"(?i)^foreach\s*\((.*)\)\s*(\{?)(.*)$", text, re.S)
        if m:
            return self._emit_foreach(lineno, text, m)

        m = re.match(r"(?i)^for\s*\((.*)\)\s*(\{?)(.*)$", text, re.S)
        if m:
            return self._emit_for(lineno, text, m)

        if re.match(r"(?i)^switch\b", text):
            self._todo(lineno, text, "switch 无法自动转换，块内代码已注释", category="control_flow")
            block = _Block("comment", "")
            block.brace_depth = text.count("{") - text.count("}")
            if block.brace_depth <= 0:
                block.brace_depth = 1
            todo_line = self._c("# TODO: 手动检查: " + text)
            self._stack.append(block)
            return [todo_line]

        if re.match(r"(?i)^try\s*\{?", text) and self._try_buffer is None:
            self._try_lineno = lineno
            self._try_buffer = []
            self._try_inline_pending = False
            self._stack.append(_Block("try", ""))
            self._try_depth = len(self._stack)
            open_index = text.find("{")
            if open_index < 0:
                self._warn(lineno, "try 缺少花括号，已忽略", text, category="control_flow")
                self._stack.pop()
                self._try_buffer = None
                return []
            close_index = find_matching(text, "{", "}", open_index)
            if close_index > open_index:
                body_text = text[open_index + 1:close_index].strip()
                tail = text[close_index + 1:].strip()
                if body_text:
                    self._try_buffer.extend(self._convert_line(lineno, body_text))
                if re.match(r"(?i)^catch\b", tail):
                    return self._handle_catch(lineno, tail, tail)
                if re.match(r"(?i)^finally\b", tail):
                    return self._handle_finally(lineno, tail, tail)
                if tail:
                    self._warn(lineno, f"try 之后的 {tail!r} 无法解析", text, category="control_flow")
                else:
                    self._try_inline_pending = True
                return []
            body_text = text[open_index + 1:].strip()
            if body_text:
                self._try_buffer.extend(self._convert_line(lineno, body_text))
            return []

        if text.lower() == "do {":
            header = self._c("while true; do")
            self._stack.append(_Block("do", "done"))
            return [header]

        m = re.match(r"(?i)^function\s+([\w:.-]+)\s*(?:\(([^)]*)\))?\s*(\{?)\s*(.*)$", text, re.S)
        if m:
            return self._emit_function(lineno, text, m)

        if re.match(r"(?i)^param\s*\(", text):
            return self._emit_param(lineno, text)

        # 单独出现的 "{"
        if text == "{":
            self._stack.append(_Block("group", "}"))
            return []

        if re.match(r"(?i)^(return|exit|throw|break|continue)\b", text):
            return [self._c(self._convert_flow(text, lineno))]

        if re.match(r"(?i)^\.\s+\S", text) or re.match(r"(?i)^\.\s*['\"]", text):
            target = re.sub(r"^(?i)\.\s*", "", text).strip().strip("\"'")
            converted = re.sub(r"(?i)\.ps1$", ".sh", convert_backslashes(target))
            self._warn(lineno, f"点源调用已转换为 source {converted}，请确认已转换", text, category="command")
            return [self._c(f'source {dq(converted)}')]

        # 函数调用重写
        tokens = tokenize_args(text)
        if tokens:
            first = tokens[0].strip("\"'")
            low = first.lower()
            if low in self._function_map:
                rest_tokens = tokenize_args(text[len(tokens[0]):].strip())
                if any(is_named_arg(t) for t in rest_tokens):
                    return self._emit_named_function_call(lineno, text, low, rest_tokens)
                # 全位置参数：交给普通语句处理
            elif self._looks_like_undefined_function(first) and any(
                is_named_arg(t) for t in tokenize_args(text[len(tokens[0]):].strip())
            ):
                self._todo(lineno, text, "未在本文件定义函数，命名参数无法解析，请确认目标命令", category="params")
                return [self._c("# TODO: 手动检查: " + text)]

        # 赋值
        assignment = self._match_assignment(text)
        if assignment is not None:
            var, op, rhs = assignment
            return self._emit_assignment(lineno, text, var, op, rhs)

        # 管道
        if len(split_top_level(text, "|")) > 1:
            return self._emit_pipeline(lineno, text)

        # & 调用运算符
        if text.startswith("&"):
            inner = text[1:].strip()
            self._warn(lineno, "&（调用运算符）已移除", text, category="command")
            return self._convert_statement(lineno, inner)

        # 普通 cmdlet / 命令
        line = self._convert_cmdlet_line(lineno, text)
        if line is None:
            if self.report.todos and self.report.todos[-1].message.startswith(
                "手动检查: Where-Object"
            ):
                return [self._c("# TODO: 手动检查: " + text)]
            return [self._c(self._todo(lineno, text, category="misc"))]
        return [self._c(line)]

    def _emit_named_function_call(
        self, lineno: int, original: str, func_low: str, arg_tokens: list[str]
    ) -> list[str]:
        name = self._function_map[func_low]
        rewritten = self._rewrite_named_args(func_low, arg_tokens, lineno)
        if rewritten is None:
            self._todo(lineno, original, "命名参数无法解析：函数未声明 param 或参数名不匹配", category="params")
            return [self._c("# TODO: 手动检查: " + original)]
        self._warn(lineno, "函数命名参数已改写为位置参数，请核对顺序", original, category="params")
        return [self._c((name + " " + " ".join(rewritten)).strip())]

    def _rewrite_named_args(
        self, func_low: str, arg_tokens: list[str], lineno: int
    ) -> list[str] | None:
        resolved = resolve_named_args(arg_tokens, self._function_params.get(func_low, []))
        if resolved is None:
            return None
        return [self._convert_arg(token, lineno) if token else "''" for token in resolved]

    @staticmethod
    def _looks_like_undefined_function(name: str) -> bool:
        low = name.lower()
        if name.startswith(("$", "/", "./", "../", "-")):
            return False
        if low in rules.PS_HANDLER_MAP or low in rules.PS_SIMPLE_CMDLETS or low in rules.PS_TODO_CMDLETS:
            return False
        if low in rules.PS_POSIX_KEEP or low.endswith(".exe"):
            return False
        if re.match(r"^[A-Z][a-z]+-[A-Z]", name):
            return False
        if "_" in name or re.match(r"^[A-Za-z]+-[A-Za-z]", name):
            return True
        return name[:1].isupper()

    # ------------------------------------------------------------------
    # 条件块
    # ------------------------------------------------------------------
    def _match_condition_header(self, text: str):
        m = re.match(r"(?i)^(if|elseif|while|until)\b", text)
        if not m:
            return None
        keyword = m.group(1).lower()
        rest = text[m.end():].lstrip()
        if not rest.startswith("("):
            return None
        close = find_matching(rest, "(", ")")
        if close < 0:
            return None
        cond = rest[1:close]
        after = rest[close + 1:].strip()
        inline = ""
        block_open = False
        if after.startswith("{"):
            brace_close = find_matching(after, "{", "}")
            if brace_close < 0:
                block_open = True
                inline = after[1:].strip()
            else:
                inline = after[1:brace_close].strip()
        elif after:
            self._warn(0, f"无法解析的语句尾部: {after}", text, category="misc")
        return keyword, cond, inline, block_open

    def _emit_condition_block(
        self, lineno: int, text: str, keyword: str, cond: str, inline: str, block_open: bool
    ) -> list[str]:
        if self._todo_reason:
            reason, self._todo_reason = self._todo_reason, ""
            return [self._c(self._todo(lineno, text, reason, category="misc"))]
        test = self._convert_condition(cond, lineno)
        prelude: list[str] = []
        if self._condition_fallback:
            reason, self._condition_fallback = self._condition_fallback, ""
            prelude = [self._c(self._todo(lineno, text, reason, category="control_flow"))]
            # 占位条件：if/elif/while 恒假（分支不执行）；until 经下方取反后同样恒假
            test = "true" if keyword == "until" else "false"
        bash_kw = {"if": "if", "elseif": "elif", "while": "while", "until": "while"}.get(keyword, "if")
        if keyword == "until":
            test = f"! {test}" if not test.startswith("[[") else "[[ ! " + test[3:]
        if keyword == "elseif":
            if self._stack:
                self._stack.pop()
        base = self._indent
        if bash_kw == "while":
            header = f"{base}while {test}; do"
            close_word = "done"
            kind = "while"
        else:
            header = f"{base}{bash_kw} {test}; then"
            close_word = "fi"
            kind = "if"
        if block_open:
            self._stack.append(_Block(kind, close_word))
            lines = prelude + [header]
            if inline:
                lines.extend(self._convert_line(lineno, inline))
            return lines
        self._stack.append(_Block("tmp", close_word))
        lines = prelude + [header]
        if inline:
            lines.extend(self._convert_line(lineno, inline))
        self._stack.pop()
        lines.append(base + close_word)
        return lines

    @staticmethod
    def _strip_condition_strings(text: str) -> str:
        return re.sub(r'"[^"]*"|\'[^\']*\'', '""', text)

    def _command_condition(self, expr: str, lineno: int) -> tuple[bool, str, str]:
        stripped = expr.strip()
        negated = False
        body = stripped
        m = re.match(r"(?is)^(-not|!)\s*\(", stripped)
        if m:
            negated = True
            body = stripped[m.end() - 1:]
            close = find_matching(body, "(", ")", 0)
            if close != len(body) - 1:
                return False, "", ""
            body = body[1:close].strip()
        elif stripped.startswith("("):
            if find_matching(stripped, "(", ")", 0) != len(stripped) - 1:
                return False, "", ""
            body = stripped[1:-1].strip()
        probe = self._strip_condition_strings(body)
        if "::" in probe:
            return True, "", "条件中的 .NET 静态调用无法自动转换"
        tokens = tokenize_args(body)
        if not tokens:
            return False, "", ""
        first = tokens[0].strip("\"'")
        if first.lower() == "test-path":
            return False, "", ""
        cmdlet_shaped = re.match(r"^[A-Za-z][\w-]*-\w+$", first)
        if _LOGIC_OP_RE.search(probe) or _COMPARE_OP_RE.search(probe):
            if cmdlet_shaped:
                return True, "", f"条件中的复合表达式（含 {first}）无法自动转换"
            return False, "", ""
        if not cmdlet_shaped:
            return False, "", ""
        low = first.lower()
        if low in self._function_map:
            return True, "", f"本文件函数 {first} 在条件中的调用无法可靠转换"
        if low != "test-connection":
            return True, "", f"条件中的命令 {first} 无对应映射"
        self._current_cmdlet = low
        converted = self._convert_cmdlet_line(lineno, body)
        if converted is None:
            return True, "", f"条件中的命令 {first} 无法转换"
        return True, (f"! {converted}" if negated else converted), ""

    def _convert_condition(self, expr: str, lineno: int) -> str:
        expr = expr.strip()
        if "$_" in expr or re.search(r"\$\w+\.\w+", expr):
            self._condition_fallback = "复杂条件（含 $_ 或对象属性访问）无法自动转换，已用占位条件"
            return "false"
        handled, test, reason = self._command_condition(expr, lineno)
        if handled:
            if reason:
                self._condition_fallback = reason
                return "false"
            return test
        # $null 比较
        expr = re.sub(r"(?i)\$null\s*-eq\s*(\$\w+)", r'-z "$\1"', expr)
        expr = re.sub(r"(?i)(\$\w+)\s*-ne\s*\$null", r'-n "$\1"', expr)
        expr = re.sub(r"(?i)\$null\s*-ne\s*(\$\w+)", r'-n "$\1"', expr)
        # -like 通配（右侧模式去掉引号以便通配）
        like_negated = bool(re.search(r"(?i)-notlike", expr))
        expr = _LIKE_OP_RE.sub("==", expr)
        expr = re.sub(
            r"(\$\{?[\w.]+\}?|\([^()]*\)|\"[^\"]*\")\s*==\s*(\"[^\"]*\"|\S+)",
            lambda m: self._like_operands(m),
            expr,
        )
        if like_negated:
            expr = f"! ( {expr} )"
        # -match 正则（bash 中引号会让 =~ 退化为字面量，需去掉引号）
        match_negated = bool(re.search(r"(?i)-notmatch", expr))
        expr = _MATCH_OP_RE.sub("=~", expr)

        def _unquote_regex(m: re.Match[str]) -> str:
            pattern = m.group(3) if m.group(3) is not None else m.group(4)
            if re.search(r"\s", pattern):
                self._warn(lineno, "包含空格的正则需改为变量后再用 =~ 匹配", m.group(0), category="control_flow")
                return m.group(0)
            return m.group(1) + pattern

        expr = re.sub(r"(=~\s*)(\"([^\"]*)\"|'([^']*)')", _unquote_regex, expr)
        if match_negated:
            expr = f"! ( {expr} )"
        # 比较运算符
        expr = _COMPARE_OP_RE.sub(lambda m: rules.PS_TEST_OPERATORS.get(m.group(1).lower(), "="), expr)
        # 逻辑运算符
        expr = _LOGIC_OP_RE.sub(lambda m: rules.PS_LOGIC_OPERATORS.get(m.group(1).lower(), "&&"), expr)
        # Test-Path
        expr = self._replace_test_path(expr)
        # 自动变量 / 普通变量
        expr = self._replace_vars(expr, lineno)
        expr = re.sub(r"\$\{(\w+)\}", r"${\1:-}", expr)
        # 布尔与 $?
        expr = re.sub(r"(?i)\$true\b", "true", expr)
        expr = re.sub(r"(?i)\$false\b", "false", expr)
        if not expr.strip():
            expr = "0 -eq 1"
        return f"[[ {expr.strip()} ]]"

    @staticmethod
    def _like_operands(m: re.Match[str]) -> str:
        left, right = m.group(1), m.group(2)
        right = right.strip("\"'")
        return f"{left} == {right}"

    def _replace_test_path(self, expr: str) -> str:
        def repl(m: re.Match[str]) -> str:
            body = m.group(1) if m.group(1) is not None else (m.group(2) or "")
            return self._test_path_expr(body)

        pattern = r"(?i)Test-Path\s*\(([^()]*)\)|Test-Path\s+([^()&|]+)"
        return re.sub(pattern, repl, expr)

    def _test_path_expr(self, body: str) -> str:
        tokens = tokenize_args(body)
        path = None
        path_type = None
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            low = tok.lower()
            if low == "-pathtype" and i + 1 < len(tokens):
                path_type = tokens[i + 1].lower().strip("\"'")
                i += 2
                continue
            if low in ("-path", "-literalpath") and i + 1 < len(tokens):
                path = tokens[i + 1]
                i += 2
                continue
            if not tok.startswith("-") and path is None:
                path = tok
            i += 1
        target = self._convert_arg(path, 0) if path else '""'
        test = "-e " + target
        if path_type == "leaf":
            test = "-f " + target
        elif path_type == "container":
            test = "-d " + target
        return test

    # ------------------------------------------------------------------
    # foreach / for
    # ------------------------------------------------------------------
    def _emit_foreach(self, lineno: int, text: str, m: re.Match[str]) -> list[str]:
        interior = m.group(1)
        inline = m.group(3).strip()
        opened = bool(m.group(2))
        closed_inline = inline.endswith("}") and inline.count("{") < inline.count("}")
        if closed_inline:
            inline = inline[:-1].strip()
        block_open = opened and not closed_inline
        parts = re.split(r"(?i)\sin\s", interior, maxsplit=1)
        if len(parts) != 2:
            self._todo(lineno, text, "无法解析 foreach 语法", category="control_flow")
            return [self._c("# TODO: 手动检查: " + text)]
        var = sanitize_identifier(parts[0].strip().lstrip("$"))
        collection = self._convert_collection(parts[1].strip(), lineno)
        header = self._c(f"for {var} in {collection}; do")
        if block_open:
            self._stack.append(_Block("for", "done"))
            lines = [header]
            if inline:
                lines.extend(self._convert_line(lineno, inline))
            return lines
        self._stack.append(_Block("tmp", "done"))
        lines = [header]
        if inline:
            lines.extend(self._convert_line(lineno, inline))
        self._stack.pop()
        lines.append(self._c("done"))
        return lines

    def _convert_collection(self, expr: str, lineno: int) -> str:
        collection = self._convert_collection_raw(expr, lineno)
        self._note_glob(lineno, collection, expr)
        return collection

    def _note_glob(self, lineno: int, snippet: str, original: str) -> None:
        if not needs_nullglob(snippet) or self._needs_nullglob:
            return
        self._needs_nullglob = True
        self._warn(
            lineno,
            "检测到通配符集合，已在脚本头添加 shopt -s nullglob：无匹配时数组为空、循环体不执行",
            original,
            category="glob",
        )

    def _convert_collection_raw(self, expr: str, lineno: int) -> str:
        expr = expr.strip()
        m = re.match(r"^(-?\d+)\s*\.\.\s*(-?\d+)$", expr)
        if m:
            return f"$(seq {m.group(1)} {m.group(2)})"
        m = re.match(r"(?i)^Get-ChildItem\s+(.*)$", expr)
        if m:
            base, pattern, recursive = self._parse_childitem(m.group(1))
            if recursive:
                self._warn(lineno, "Get-ChildItem -Recurse 已转换为 find，请检查", expr, category="path")
                return f"$(find {base or '.'} -name {pattern})"
            if base is None:
                return pattern
            base_quoted = self._convert_arg(base, lineno)
            if "*" in base_quoted or "?" in base_quoted:
                return self._fix_glob_value(base_quoted)
            return f"{base_quoted}/{pattern}"
        if expr.startswith("$"):
            var_name = expr.lstrip("$").split(".")[0].lower()
            if ".Keys" in expr or ".Values" in expr:
                return ""
            if var_name in {v.lower() for v in self._array_vars}:
                canonical = self._var_map.get(var_name, var_name)
                return f'"${{{canonical}[@]}}"'
            self._warn(lineno, "变量集合在 bash 中按空白切分，若元素含空格请改用数组", expr, category="glob")
            return self._convert_expression(expr, lineno)
        if "," in expr:
            items = [t.strip().strip("\"'") for t in split_top_level(expr, ",")]
            return " ".join(items)
        return self._convert_expression(expr, lineno)

    def _emit_for(self, lineno: int, text: str, m: re.Match[str]) -> list[str]:
        interior = m.group(1)
        inline = m.group(3).strip()
        block_open = not inline
        if inline.startswith("{"):
            inline = inline[1:].strip()
            if inline.endswith("}"):
                inline = inline[:-1].strip()
        parts = split_top_level(interior, ";")
        if len(parts) != 3:
            self._todo(lineno, text, "无法解析 for 循环", category="control_flow")
            return [self._c("# TODO: 手动检查: " + text)]
        init, cond, step = (p.strip() for p in parts)
        init = re.sub(r"\$\{(\w+)\}", r"\1", self._replace_vars(init, lineno)).strip()
        cond = re.sub(r"\$\{(\w+)\}", r"\1", self._replace_vars(cond, lineno))
        for ps_op, bash_op in (("-lt", "<"), ("-le", "<="), ("-gt", ">"), ("-ge", ">="),
                               ("-eq", "=="), ("-ne", "!=")):
            cond = re.sub(rf"(?i){re.escape(ps_op)}\b", bash_op, cond)
        step = re.sub(r"\$\{(\w+)\}", r"\1", self._replace_vars(step, lineno)).strip()
        header = self._c(f"for (( {init}; {cond}; {step} )); do")
        if block_open:
            self._stack.append(_Block("for", "done"))
            lines = [header]
            tail = m.group(3).strip()
            if tail.startswith("{") and len(tail) > 1:
                lines.extend(self._convert_line(lineno, tail[1:].strip()))
            return lines
        self._stack.append(_Block("tmp", "done"))
        lines = [header]
        if inline:
            lines.extend(self._convert_line(lineno, inline))
        self._stack.pop()
        lines.append(self._c("done"))
        return lines

    # ------------------------------------------------------------------
    # 函数 / param
    # ------------------------------------------------------------------
    def _emit_function(self, lineno: int, text: str, m: re.Match[str]) -> list[str]:
        raw_name = m.group(1)
        after = text[m.end(1):]
        open_index = after.find("(")
        close = find_matching(after, "(", ")", open_index) if open_index >= 0 else -1
        if close > open_index:
            params = after[open_index + 1:close]
            tail = after[close + 1:].strip()
        else:
            params = ""
            tail = after.strip()
        name = self._function_map.get(raw_name.lower(), sanitize_identifier(raw_name))
        lines = [self._c(f"{name}() {{")]
        self._stack.append(_Block("function", "}"))
        local_lines = self._convert_params(params, lineno, as_local=True, start_index=1)
        lines.extend(self._indent + line if line else "" for line in local_lines)
        if tail.startswith("{") and tail.endswith("}"):
            body = tail[1:-1].strip()
            body_lines = self._convert_line(lineno, body) if body else []
            self._stack.pop()
            lines.extend(body_lines)
            lines.append(self._c("}"))
        elif tail and tail != "{":
            lines.extend(self._convert_line(lineno, tail))
        return lines

    def _emit_param(self, lineno: int, text: str) -> list[str]:
        if ")" not in text:
            self._param_buffer = [text]
            return []
        open_index = text.find("(")
        close = find_matching(text, "(", ")", open_index) if open_index >= 0 else -1
        interior = text[open_index + 1:close] if close > open_index else ""
        inside_function = any(b.kind == "function" for b in self._stack)
        if not inside_function:
            self._warn(lineno, "脚本级 param() 已转换为位置参数，命名参数需手动处理", text, category="params")
        raw_lines = self._convert_params(interior, lineno, as_local=inside_function, start_index=1)
        return [self._c(line) if line else "" for line in raw_lines]

    def _convert_params(self, interior: str, lineno: int, as_local: bool, start_index: int) -> list[str]:
        if not interior.strip():
            return []
        prefix = "local " if as_local else ""
        lines: list[str] = []
        index = start_index
        for raw in split_top_level(interior, ","):
            raw = raw.strip().rstrip(",")
            if not raw:
                continue
            attrs, decl = strip_leading_attributes(raw)
            if attrs:
                self._warn_param_attributes(lineno, attrs, raw)
            m = re.match(r"\$(\w+)\s*(?:=\s*(.+))?$", decl, re.S)
            if not m:
                self._warn(lineno, f"无法解析的参数声明: {raw}", raw, category="params")
                continue
            name = m.group(1)
            default = (m.group(2) or "").strip().rstrip(",")
            if default:
                default = self._convert_expression(default, lineno)
                inner, quote = strip_outer_quotes(default)
                if quote:
                    default = inner
                if re.match(r"^[A-Za-z]:[\\/]", default) or default.startswith("\\\\"):
                    self._warn(
                        lineno,
                        f"参数默认值 {default!r} 是 Windows 路径，已按原样保留，请在 Linux 下改为实际路径",
                        raw,
                        category="path",
                    )
                    lines.append("# 注意: Windows 路径，请改为 Linux 路径，例如 ${HOME}/data")
                    default = convert_backslashes(default)
                elif not re.search(r"\\\\|\\[dwsbSAZDW](?![A-Za-z0-9])", default):
                    default = convert_backslashes(default)
                default = default.replace('"', '\\"')
                lines.append(f'{prefix}{name}="${{{index}:-{default}}}"')
            else:
                lines.append(f'{prefix}{name}="${index}"')
            index += 1
        return lines

    def _warn_param_attributes(self, lineno: int, attrs: str, raw: str) -> None:
        """参数 attribute 仅在生成 ``local`` 时被剥离，需提醒被丢弃的绑定语义。"""
        low = attrs.lower()
        unsupported: list[str] = []
        if "parameter" in low:
            unsupported.append("Mandatory/Position/管道绑定校验")
        if "validate" in low:
            unsupported.append("Validate* 参数校验")
        if "alias" in low:
            unsupported.append("Alias 别名")
        if "allownull" in low or "allowempty" in low:
            unsupported.append("AllowNull/AllowEmpty")
        if unsupported:
            self._warn(
                lineno,
                "参数 attribute 已剥离（" + "、".join(unsupported) + "），在 bash 中无对应物，请人工核对",
                raw,
                category="params",
            )

    # ------------------------------------------------------------------
    # 赋值
    # ------------------------------------------------------------------
    def _match_assignment(self, text: str):
        m = re.match(r"^\[[\w\.\[\]]+\]\s*(\$[\w]+)\s*([+\-*/%]?=)\s*(.+)$", text, re.S)
        if m:
            return m.group(1), m.group(2), m.group(3)
        m = re.match(r"^(\$[\w]+)\s*([+\-*/%]?=)\s*(.+)$", text, re.S)
        if m:
            return m.group(1), m.group(2), m.group(3)
        return None

    def _emit_assignment(self, lineno: int, original: str, var: str, op: str, rhs: str) -> list[str]:
        name = self._var_map.get(var[1:].lower(), var[1:])
        rhs = rhs.strip()
        low = rhs.lower()

        if low.startswith("$erroractionpreference"):
            self._warn(lineno, "无法解析的赋值", original, category="misc")
        if var[1:].lower() == "erroractionpreference":
            value = rhs.strip().strip("\"'").lower()
            if value == "stop":
                if has_set_e(self.settings.strict_mode):
                    self._warn(
                        lineno,
                        "$ErrorActionPreference = 'Stop'：脚本头已启用严格模式，已跳过重复的 set -e",
                        original,
                        category="control_flow",
                    )
                    return [self._c('# $ErrorActionPreference = "Stop"（脚本头已启用严格模式）')]
                self._warn(lineno, "$ErrorActionPreference = 'Stop' 已转换为 set -e", original, category="control_flow")
                return [self._c("set -e")]
            if value == "continue":
                self._warn(lineno, "$ErrorActionPreference = 'Continue' 已转换为 set +e", original, category="control_flow")
                return [self._c("set +e")]
            self._warn(lineno, "$ErrorActionPreference 的值无法映射到 bash", original, category="control_flow")
            return [self._c("# " + original)]
        if var[1:].lower() in ("debugpreference", "verbosepreference", "progresspreference",
                               "warningpreference", "informationpreference"):
            return [self._c("# " + original)]

        # Read-Host
        m = re.match(r"(?i)^Read-Host\b(.*)$", rhs)
        if m:
            return self._read_host(lineno, original, name, m.group(1))

        if re.search(r"\$\{?\w+\}?\.[A-Z]\w*", rhs):
            return [self._c(self._todo(lineno, original, "对象属性访问（如 $obj.Prop）无法自动转换", category="objects"))]
        if re.search(r"\]\s*::", rhs):
            return [self._c(self._todo(lineno, original, ".NET 类型静态调用在 bash 中无对应物", category="objects"))]

        # 数组
        if rhs.startswith("@(") and rhs.endswith(")"):
            inner = rhs[2:-1].strip()
            items = [self._convert_arg(x, lineno) for x in split_top_level(inner, ",") if x.strip()]
            self._array_vars.add(name)
            joined = " ".join(items)
            self._note_glob(lineno, joined, original)
            if op == "+=":
                return [self._c(f"{name}+=({joined})")]
            return [self._c(f"{name}=({joined})")]

        # Get-ChildItem 数组
        m = re.match(r"(?i)^Get-ChildItem\s*(.*)$", rhs)
        if m:
            self._array_vars.add(name)
            base, pattern, recursive = self._parse_childitem(m.group(1))
            if recursive:
                self._warn(lineno, "Get-ChildItem -Recurse 已转换为 find，请检查", original, category="path")
                find_cmd = f"find {base} -name {pattern}"
                return [self._c(f"{name}=$({find_cmd})")]
            if base is None:
                expression = "*"
            else:
                base_quoted = self._convert_arg(base, lineno)
                if "*" in base_quoted or "?" in base_quoted:
                    expression = self._fix_glob_value(base_quoted)
                else:
                    expression = f"{base_quoted}/{pattern}"
            self._note_glob(lineno, expression, original)
            if op == "+=":
                return [self._c(f"{name}+=({expression})")]
            return [self._c(f"{name}=({expression})")]

        if low == "$null":
            return [self._c(f'{name}=""')]
        if low == "$true":
            return [self._c(f"{name}=true")]
        if low == "$false":
            return [self._c(f"{name}=false")]

        if re.match(r"(?i)^(Get-Date|Join-Path|Split-Path|Resolve-Path|Test-Path|Test-Connection|Get-Content|Get-Item|Get-Process|Get-ChildItem)\b", rhs):
            if re.match(r"(?i)^Test-Path\b", rhs):
                test = self._replace_test_path(rhs)
                return [self._c(f"{name}=$({test} && echo true || echo false)")]
            self._current_cmdlet = ""
            converted = self._convert_cmdlet_line(lineno, rhs)
            if converted is None:
                return [self._c(self._todo(lineno, original, "cmdlet 结果无法自动赋值", category="objects"))]
            converted = converted.strip()
            if re.match(r"(?i)^Test-Connection\b", rhs) and re.search(r"(?i)-quiet\b", rhs):
                return [self._c(f"{name}=$({converted} && echo true || echo false)")]
            if converted.startswith(("$(", '"', "'", "${", "$@")):
                return [self._c(f"{name}={converted}")]
            return [self._c(f"{name}=$({converted})")]

        # 算术
        arith = self._try_arithmetic(rhs, lineno)
        if arith is not None:
            if op == "=":
                return [self._c(f"{name}=$(( {arith} ))")]
            return [self._c(f"{name}=$(( {name} {op[0]} ({arith}) ))")]

        # 字符串拼接
        concat = self._try_concat(rhs, lineno)
        if concat is not None:
            if op == "+=":
                return [self._c(f'{name}+={concat}')]
            return [self._c(f"{name}={concat}")]

        expression = self._convert_expression(rhs, lineno)
        if self._todo_reason:
            reason, self._todo_reason = self._todo_reason, ""
            return [self._c(self._todo(lineno, original, reason, category="misc"))]
        if expression.startswith("$(") and expression.endswith(")"):
            return [self._c(f"{name}={expression}")]
        if expression.startswith("'") or expression.startswith('"'):
            return [self._c(f"{name}={expression}")]
        if re.fullmatch(r"-?\d+(\.\d+)?", expression):
            return [self._c(f"{name}={expression}")]
        if expression.startswith("${") and re.fullmatch(r"\$\{[\w]+\}", expression):
            return [self._c(f"{name}={expression}")]
        self._warn(lineno, "无法确定右值类型，已按字符串处理，请检查", original, category="misc")
        return [self._c(f"{name}={dq(expression)}")]

    def _parse_childitem(self, args: str) -> tuple[str | None, str, bool]:
        tokens = tokenize_args(args)
        path = None
        pattern = "*"
        recursive = False
        i = 0
        while i < len(tokens):
            low = tokens[i].lower()
            if low == "-recurse":
                recursive = True
                i += 1
                continue
            if low in ("-filter", "-include") and i + 1 < len(tokens):
                value, _ = strip_outer_quotes(tokens[i + 1])
                pattern = value
                i += 2
                continue
            if low == "-exclude" and i + 1 < len(tokens):
                i += 2
                continue
            if low in ("-force", "-file", "-directory", "-name", "-hidden"):
                i += 1
                continue
            if not tokens[i].startswith("-") and path is None:
                path = tokens[i]
            i += 1
        return path, pattern, recursive

    @staticmethod
    def _fix_glob_value(value: str) -> str:
        if not (len(value) >= 2 and value.startswith('"') and value.endswith('"')):
            return value
        inner = value[1:-1]
        index = max(inner.rfind("/"), inner.rfind("\\"))
        if index <= 0:
            return inner
        return '"' + inner[:index] + '"/' + inner[index + 1:]

    def _read_host(self, lineno: int, original: str, name: str, args: str) -> list[str]:
        secure = bool(re.search(r"(?i)-AsSecureString", args))
        args = re.sub(r"(?i)-AsSecureString", "", args)
        args = re.sub(r"(?i)-Prompt\s+", "", args)
        args = re.sub(r"(?i)-MaskInput\b", "", args)
        prompt, _ = strip_outer_quotes(args.strip())
        prompt = self._replace_vars(prompt, lineno)
        if not prompt:
            prompt = "请输入"
        if secure:
            self._warn(lineno, "Read-Host -AsSecureString 已转换为 read -s（输入不回显）", original, category="command")
            return [self._c(guard_read(f'read -rsp {dq(prompt)} {name}', self.settings.strict_mode))]
        return [self._c(guard_read(f'read -rp {dq(prompt)} {name}', self.settings.strict_mode))]

    def _try_arithmetic(self, rhs: str, lineno: int) -> str | None:
        if re.search(r"[+\-*/%]|--|\+\+", rhs) and re.search(r"\d", rhs):
            if "|" in rhs or re.match(r"^[A-Za-z][A-Za-z0-9_]*-\w", rhs):
                return None
            converted = self._replace_vars(rhs, lineno)
            converted = re.sub(r"\$\{(\w+)\}", r"${\1:-0}", converted)
            if re.search(r"\$\(|\$\{[\w]+\}\s*[a-z]", converted):
                return None
            if '"' in converted or "'" in converted:
                return None
            converted = re.sub(r"(?i)Get-Date\b", "$(date)", converted)
            converted = converted.lstrip("+")
            return converted.strip()
        return None

    def _try_concat(self, rhs: str, lineno: int) -> str | None:
        if "+" not in rhs:
            return None
        parts = split_top_level(rhs, "+")
        if len(parts) < 2:
            return None
        chunks: list[str] = []
        for part in parts:
            part = part.strip()
            if part.startswith(("'", '"')) and part.endswith(("'", '"')):
                body = part[1:-1]
                chunks.append(self._replace_vars(body, lineno))
            elif part.startswith("$") and re.fullmatch(r"\$[\w.]+", part):
                value = self._convert_expression(part, lineno)
                chunks.append(value[2:-1] if value.startswith("${") else value)
            else:
                return None
        return '"' + "".join(chunks) + '"'

    # ------------------------------------------------------------------
    # 管道
    # ------------------------------------------------------------------
    def _emit_pipeline(self, lineno: int, text: str) -> list[str]:
        segments = [s.strip() for s in split_top_level(text, "|")]
        self._pipe_comments = []
        pieces: list[str] = []
        redirect = ""
        for index, segment in enumerate(segments):
            if index == 0:
                head = self._convert_cmdlet_line(lineno, segment)
                if head is None:
                    self._todo(lineno, text, "管道首段无法转换", category="pipeline")
                    return [self._c("# TODO: 手动检查: " + text)]
                pieces.append(head)
                continue
            converted, is_redirect = self._convert_pipe_filter(lineno, segment)
            if converted is None:
                self._todo(lineno, text, f"管道段 {segment!r} 无法转换", category="pipeline")
                return [self._c("# TODO: 手动检查: " + text)]
            if is_redirect:
                if index != len(segments) - 1:
                    self._todo(lineno, text, "重定向出现在管道中间", category="pipeline")
                    return [self._c("# TODO: 手动检查: " + text)]
                redirect = converted
            else:
                pieces.append(converted)
        line = " | ".join(pieces)
        if redirect:
            line += " " + redirect
        if self._pipe_comments:
            line += "  # " + "；".join(self._pipe_comments)
        return [self._c(line)]

    def _convert_pipe_filter(self, lineno: int, segment: str) -> tuple[str | None, bool]:
        tokens = tokenize_args(segment)
        if not tokens:
            return None, False
        name = tokens[0].strip("\"'")
        low = name.lower()
        args = tokens[1:]
        if low in ("out-file", "set-content", "add-content", "out-null"):
            append = any(a.lower() in ("-append", "-addcontent") for a in args)
            if low == "out-null":
                return "> /dev/null", True
            path = None
            i = 0
            while i < len(args):
                a = args[i]
                if a.lower() in ("-path", "-filepath", "-literalpath") and i + 1 < len(args):
                    path = args[i + 1]
                    i += 2
                    continue
                if not a.startswith("-") and path is None:
                    path = a
                i += 1
            if path is None:
                return None, False
            path = self._replace_vars(strip_outer_quotes(path)[0], lineno)
            op = ">>" if append or low == "add-content" else ">"
            return f"{op} {dq(convert_backslashes(path))}", True
        if low == "select-string":
            opts = ""
            if "-simplematch" in (a.lower() for a in args):
                opts += "F"
            if "-notmatch" in (a.lower() for a in args):
                opts += "v"
            if "-casesensitive" in (a.lower() for a in args):
                pass
            pattern = None
            i = 0
            while i < len(args):
                a = args[i]
                if a.lower() in ("-pattern", "-simplematch") and i + 1 < len(args) and a.lower() == "-pattern":
                    pattern = args[i + 1]
                    i += 2
                    continue
                if not a.startswith("-"):
                    pattern = a
                i += 1
            pattern = pattern or '""'
            self._warn(lineno, "Select-String 已转换为 grep，正则语法可能不同", segment, category="pipeline")
            return f"grep -{opts} {pattern}".replace("- ", " "), False
        if low == "sort-object":
            reverse = "-descending" in (a.lower() for a in args)
            self._warn(lineno, "Sort-Object 已转换为 sort（对象排序语义不同）", segment, category="pipeline")
            return "sort -r" if reverse else "sort", False
        if low == "measure-object":
            self._warn(lineno, "Measure-Object 已转换为 wc -l", segment, category="pipeline")
            if any(a.lower() in ("-character",) for a in args):
                return "wc -c", False
            if any(a.lower() in ("-word",) for a in args):
                return "wc -w", False
            return "wc -l", False
        if low == "tee-object":
            append = "-append" in (a.lower() for a in args)
            path = next((a for a in args if not a.startswith("-")), None)
            if path:
                path, _ = strip_outer_quotes(path)
                return f"tee {'-a ' if append else ''}{dq(convert_backslashes(path))}", False
            return None, False
        if low == "select-object":
            for i, a in enumerate(args):
                if a.lower() == "-first" and i + 1 < len(args):
                    return f"head -n {args[i + 1]}", False
                if a.lower() == "-last" and i + 1 < len(args):
                    return f"tail -n {args[i + 1]}", False
            return None, False
        if low == "where-object":
            return self._convert_where_object(lineno, segment), False
        if low in ("foreach-object", "convertto-json", "convertfrom-json",
                   "get-member", "format-table", "format-list", "out-string", "get-unique"):
            return None, False
        converted = self._convert_cmdlet_line(lineno, segment)
        return converted, False

    _WHERE_BLOCK_RE = re.compile(
        r"(?i)^\{\s*\$_(?:\.([A-Za-z_]\w*))?\s*"
        r"(-(?:eq|ne|like|notlike|match|notmatch))\s+"
        r"(\"[^\"]*\"|'[^']*'|\S+?)\s*\}$"
    )
    _WHERE_PLAIN_RE = re.compile(
        r"(?i)^(?:-Property\s+)?([A-Za-z_]\w*)\s*"
        r"(-(?:eq|ne|like|notlike|match|notmatch))\s+"
        r"(\"[^\"]*\"|'[^']*'|\S+)$"
    )

    def _convert_where_object(self, lineno: int, segment: str) -> str | None:
        tokens = tokenize_args(segment)
        if not tokens:
            return None
        args = segment[len(tokens[0]):].strip()
        whole_line = True
        m = self._WHERE_BLOCK_RE.match(args)
        if m:
            property_name = m.group(1) or ""
            whole_line = not property_name
            op = m.group(2).lower()
            raw_value = m.group(3)
        else:
            m = self._WHERE_PLAIN_RE.match(args)
            if not m:
                return None
            whole_line = False
            property_name = m.group(1)
            op = m.group(2).lower()
            raw_value = m.group(3)
        if raw_value.startswith("$"):
            return None
        value, _ = strip_outer_quotes(raw_value)
        if not value:
            return None
        if op in ("-eq", "-ne"):
            command = "grep -Fv" if op == "-ne" else "grep -F"
            pattern = sq(value)
        elif op in ("-like", "-notlike"):
            regex = simple_glob_to_regex(value)
            if whole_line:
                regex = "^" + regex + "$"
            command = "grep -Ev" if op == "-notlike" else "grep -E"
            pattern = sq(regex)
        else:
            command = "grep -Ev" if op == "-notmatch" else "grep -E"
            pattern = sq(value)
        scope = "整行" if whole_line else f"属性 {property_name} "
        source = "$_" if whole_line else "$_." + property_name
        self._pipe_comments.append(
            f"近似: 按整行文本匹配，无法还原 {source} 属性语义"
        )
        self._warn(
            lineno,
            f"Where-Object 的{scope}条件已近似转换为 {command}，无法还原对象/类型语义，请核对",
            segment,
            category="pipeline",
        )
        return f"{command} -- {pattern}"

    # ------------------------------------------------------------------
    # cmdlet 语句
    # ------------------------------------------------------------------
    def _convert_cmdlet_line(self, lineno: int, text: str) -> str | None:
        text = self._expand_inline_cmdlets(text, lineno)
        if text.lstrip().startswith("$("):
            # Join-Path/Split-Path 等内联改写后整条语句已是命令替换，无命令名可映射。
            return self._convert_expression(text, lineno)
        tokens = tokenize_args(text)
        if not tokens:
            return None
        name = tokens[0].strip("\"'")
        low = name.lower()
        args = tokens[1:]
        self._current_cmdlet = low
        if low != "where-object" and (
            re.search(r"\$\{?\w+\}?\.[A-Z]\w*", text) or re.search(r"\]\s*::", text)
        ):
            self._todo(lineno, text, "对象属性 / .NET 静态调用无法自动转换", category="objects")
            return None
        if low in rules.PS_HANDLER_MAP:
            return getattr(self, rules.PS_HANDLER_MAP[low])(lineno, args, text)
        if low in rules.PS_TODO_CMDLETS:
            self._todo(lineno, text, rules.PS_TODO_CMDLETS[low], category="command")
            return None
        if low in self._function_map:
            rest_tokens = tokenize_args(text[len(tokens[0]):].strip())
            if any(is_named_arg(t) for t in rest_tokens):
                rewritten = self._rewrite_named_args(low, rest_tokens, lineno)
                if rewritten is None:
                    return None
                self._warn(lineno, "函数命名参数已改写为位置参数，请核对顺序", text, category="params")
                return (self._function_map[low] + " " + " ".join(rewritten)).strip()
            rest = self._convert_args_join(rest_tokens, lineno)
            return (self._function_map[low] + " " + rest).strip() or self._function_map[low]
        if low in rules.PS_SIMPLE_CMDLETS:
            mapped = rules.PS_SIMPLE_CMDLETS[low]
            if low in rules.PS_WARN_CMDLETS:
                self._warn(lineno, f"{name} 已转换为 {mapped}，语义可能不完全相同", text, category="command")
            rest = self._convert_args_join(args, lineno)
            return (mapped + (" " + rest if rest else "")).strip()
        if low.endswith(".exe"):
            base = low[:-4]
            return (base + " " + self._convert_args_join(args, lineno)).strip()
        if re.match(r"^[A-Z][a-z]+-[A-Z]", name):
            self._todo(lineno, text, "未支持的 PowerShell cmdlet", category="command")
            return None
        if low in rules.PS_POSIX_KEEP:
            return self._convert_expression(text, lineno)
        self._warn(lineno, f"未知命令 {name!r}，请确认 Linux 下可用", text, category="command")
        return self._convert_expression(text, lineno)

    def _convert_args_join(self, args: list[str], lineno: int) -> str:
        return " ".join(self._convert_arg(a, lineno) for a in args)

    def _convert_arg(self, token: str, lineno: int) -> str:
        if token.startswith("(") and token.endswith(")") and find_matching(token, "(", ")") == len(token) - 1:
            return self._convert_arg(token[1:-1].strip(), lineno)
        if token.startswith(('"', "'")):
            quote = token[0]
            inner = token[1:-1] if token.endswith(quote) else token[1:]
            converted = convert_backslashes(self._replace_vars(inner, lineno))
            return dq(converted) if quote == '"' else "'" + converted + "'"
        converted = convert_backslashes(self._replace_vars(token, lineno))
        if re.fullmatch(r"\$\{\w+\}|\[\[.*\]\]", converted):
            if self.settings.quote_variables:
                return dq(converted)
            return converted
        return converted

    # ------------------------------------------------------------------
    # 具体 cmdlet 处理器
    # ------------------------------------------------------------------
    def cmd_write_host(self, lineno: int, args: list[str], original: str) -> str | None:
        no_newline = False
        separator = None
        body: list[str] = []
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low == "-nonewline":
                no_newline = True
                i += 1
                continue
            if low in ("-foregroundcolor", "-backgroundcolor") and i + 1 < len(args):
                self._warn(lineno, f"Write-Host 的 {args[i]} 颜色参数已忽略", original, category="command")
                i += 2
                continue
            if low == "-separator" and i + 1 < len(args):
                separator = self._convert_arg(args[i + 1], lineno)
                i += 2
                continue
            body.append(self._convert_arg(args[i], lineno))
            i += 1
        if separator:
            joined = separator.join(body)
        else:
            joined = " ".join(body)
        if no_newline:
            return f"printf '%s' {joined}".strip()
        return f"echo {joined}".strip()

    def cmd_write_warning(self, lineno: int, args: list[str], original: str) -> str:
        message = self._convert_args_join([a for a in args if not a.startswith("-")], lineno)
        return f"echo {message} >&2".strip()

    def cmd_write_error(self, lineno: int, args: list[str], original: str) -> str:
        message = self._convert_args_join([a for a in args if not a.startswith("-")], lineno)
        return f"echo {message} >&2".strip()

    def cmd_write_verbose(self, lineno: int, args: list[str], original: str) -> str:
        return "# Write-Verbose: " + " ".join(args)

    def cmd_write_debug(self, lineno: int, args: list[str], original: str) -> str:
        return "# Write-Debug: " + " ".join(args)

    def cmd_get_date(self, lineno: int, args: list[str], original: str) -> str:
        result = self._get_date(lineno, " ".join(args))
        if result.startswith("$(") and result.endswith(")"):
            result = result[2:-1]
        return result

    def cmd_read_host(self, lineno: int, args: list[str], original: str) -> str | None:
        prompt = next((a for a in args if not a.startswith("-")), None)
        prompt_text = self._convert_arg(prompt, lineno).strip("\"'") if prompt else "请输入"
        if any(a.lower() == "-assecurestring" for a in args):
            self._warn(lineno, "Read-Host -AsSecureString 已转换为 read -s", original, category="command")
            return guard_read(f'read -rsp {dq(prompt_text)} REPLY', self.settings.strict_mode)
        self._warn(lineno, "Read-Host 结果被丢弃（未赋值给变量）", original, category="command")
        return guard_read(f'read -rp {dq(prompt_text)} REPLY', self.settings.strict_mode)

    def cmd_get_childitem(self, lineno: int, args: list[str], original: str) -> str:
        recursive = False
        path = None
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low == "-recurse":
                recursive = True
                i += 1
                continue
            if low in ("-path", "-literalpath") and i + 1 < len(args):
                path = args[i + 1]
                i += 2
                continue
            if low in ("-filter", "-include", "-exclude") and i + 1 < len(args):
                self._warn(lineno, f"Get-ChildItem 的 {args[i]} 已转换为位置参数，请检查", original, category="command")
                path = args[i + 1]
                i += 2
                continue
            if low in ("-force", "-name"):
                i += 1
                continue
            if low in ("-file", "-directory"):
                self._warn(lineno, f"Get-ChildItem {args[i]} 已忽略，请改用 find", original, category="command")
                i += 1
                continue
            if not args[i].startswith("-") and path is None:
                path = args[i]
            i += 1
        flags = "-laR" if recursive else "-la"
        if path:
            return f"ls {flags} {self._convert_arg(path, lineno)}"
        return f"ls {flags}"

    def cmd_get_content(self, lineno: int, args: list[str], original: str) -> str:
        path = None
        tail_n = None
        head_n = None
        follow = False
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low == "-tail" and i + 1 < len(args):
                tail_n = args[i + 1]
                i += 2
                continue
            if low in ("-totalcount", "-head") and i + 1 < len(args):
                head_n = args[i + 1]
                i += 2
                continue
            if low == "-wait":
                follow = True
                i += 1
                continue
            if low in ("-raw", "-force", "-encoding"):
                if low == "-encoding" and i + 1 < len(args):
                    i += 2
                    continue
                i += 1
                continue
            if low in ("-path", "-literalpath") and i + 1 < len(args):
                path = args[i + 1]
                i += 2
                continue
            if not args[i].startswith("-") and path is None:
                path = args[i]
            i += 1
        target = self._convert_arg(path, lineno) if path else None
        if follow:
            return f"tail -f {target}".strip()
        if tail_n:
            return f"tail -n {tail_n} {target}".strip()
        if head_n:
            return f"head -n {head_n} {target}".strip()
        return f"cat {target}".strip()

    def _content_redirect(self, lineno: int, args: list[str], original: str, append: bool) -> str | None:
        path = None
        value: list[str] = []
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low in ("-path", "-filepath", "-literalpath") and i + 1 < len(args):
                path = args[i + 1]
                i += 2
                continue
            if low == "-value" and i + 1 < len(args):
                value.append(self._convert_arg(args[i + 1], lineno))
                i += 2
                continue
            if low in ("-append", "-force", "-encoding", "-nonewline") :
                if low == "-encoding" and i + 1 < len(args):
                    i += 2
                    continue
                i += 1
                continue
            if not args[i].startswith("-"):
                if path is None:
                    path = args[i]
                else:
                    value.append(self._convert_arg(args[i], lineno))
            i += 1
        if path is None:
            if value:
                self._warn(lineno, "缺少输出文件参数", original, category="command")
            return None
        op = ">>" if append else ">"
        target = dq(convert_backslashes(strip_outer_quotes(path)[0]))
        payload = " ".join(value)
        return f"echo {payload} {op} {target}".strip()

    def cmd_set_content(self, lineno: int, args: list[str], original: str) -> str | None:
        return self._content_redirect(lineno, args, original, append=False)

    def cmd_add_content(self, lineno: int, args: list[str], original: str) -> str | None:
        return self._content_redirect(lineno, args, original, append=True)

    def cmd_out_file(self, lineno: int, args: list[str], original: str) -> str | None:
        append = any(a.lower() == "-append" for a in args)
        return self._content_redirect(lineno, args, original, append=append)

    def cmd_copy_item(self, lineno: int, args: list[str], original: str) -> str:
        flags = []
        paths: list[str] = []
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low == "-recurse":
                flags.append("-r")
                i += 1
                continue
            if low == "-force":
                flags.append("-f")
                i += 1
                continue
            if low in ("-destination", "-path", "-literalpath") and i + 1 < len(args):
                paths.append(args[i + 1])
                i += 2
                continue
            if low == "-filter" and i + 1 < len(args):
                i += 2
                continue
            if not args[i].startswith("-"):
                paths.append(args[i])
            i += 1
        flag_text = " ".join(sorted(set(flags)))
        path_text = " ".join(self._convert_arg(p, lineno) for p in paths)
        return (f"cp {flag_text} {path_text}").replace("  ", " ").strip()

    def cmd_move_item(self, lineno: int, args: list[str], original: str) -> str:
        paths = self._positional_paths(args, ("-destination", "-path", "-literalpath"))
        path_text = " ".join(self._convert_arg(p, lineno) for p in paths)
        return f"mv {path_text}".strip()

    def cmd_remove_item(self, lineno: int, args: list[str], original: str) -> str | None:
        if any(a.lower() == "-whatif" for a in args):
            self._todo(lineno, original, "Remove-Item -WhatIf（预演）在 bash 中无对应物", category="command")
            return None
        recursive = any(a.lower() == "-recurse" for a in args)
        force = any(a.lower() == "-force" for a in args)
        flags = "-rf" if (recursive and force) else ("-r" if recursive else "-f")
        paths = [a for a in args if not a.startswith("-")]
        path_text = " ".join(self._convert_arg(p, lineno) for p in paths)
        return f"rm {flags} {path_text}".strip()

    def cmd_rename_item(self, lineno: int, args: list[str], original: str) -> str | None:
        target = None
        new_name = None
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low == "-newname" and i + 1 < len(args):
                new_name = args[i + 1]
                i += 2
                continue
            if not args[i].startswith("-") and target is None:
                target = args[i]
            i += 1
        if target and new_name:
            return f"mv {self._convert_arg(target, lineno)} {self._convert_arg(new_name, lineno)}"
        self._todo(lineno, original, "Rename-Item 参数无法解析", category="command")
        return None

    def cmd_new_item(self, lineno: int, args: list[str], original: str) -> str | None:
        item_type = "file"
        path = None
        target = None
        force = False
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low == "-itemtype" and i + 1 < len(args):
                item_type = args[i + 1].strip("\"'").lower()
                i += 2
                continue
            if low in ("-path", "-name") and i + 1 < len(args):
                path = args[i + 1]
                i += 2
                continue
            if low == "-target" and i + 1 < len(args):
                target = args[i + 1]
                i += 2
                continue
            if low == "-force":
                force = True
                i += 1
                continue
            if not args[i].startswith("-") and path is None:
                path = args[i]
            i += 1
        if item_type == "directory":
            return f"mkdir -p {self._convert_arg(path, lineno)}" if path else None
        if item_type == "symboliclink" and target:
            return f"ln -s {self._convert_arg(target, lineno)} {self._convert_arg(path, lineno)}"
        if path:
            if force:
                return f"touch {self._convert_arg(path, lineno)}"
            return f"[ -e {self._convert_arg(path, lineno)} ] || touch {self._convert_arg(path, lineno)}"
        self._todo(lineno, original, "New-Item 参数无法解析", category="command")
        return None

    def cmd_test_path(self, lineno: int, args: list[str], original: str) -> str:
        paths = [a for a in args if not a.startswith("-")]
        path = paths[0] if paths else '""'
        return f"[ -e {self._convert_arg(path, lineno)} ]"

    def cmd_test_connection(self, lineno: int, args: list[str], original: str) -> str | None:
        host: str | None = None
        count: str | None = None
        redirect = ""
        extra: list[str] = []
        i = 0
        while i < len(args):
            token = args[i]
            low = token.lower()
            if low == "-computername" and i + 1 < len(args):
                host = args[i + 1]
                i += 2
                continue
            if low.startswith("-computername:"):
                host = token.split(":", 1)[1]
                i += 1
                continue
            if low == "-count" and i + 1 < len(args):
                count = args[i + 1]
                i += 2
                continue
            if low.startswith("-count:"):
                count = token.split(":", 1)[1]
                i += 1
                continue
            if low == "-quiet":
                i += 1
                continue
            error_action = None
            if low == "-erroraction" and i + 1 < len(args):
                error_action = args[i + 1]
                consumed = 2
            elif low.startswith("-erroraction:"):
                error_action = token.split(":", 1)[1]
                consumed = 1
            if error_action is not None:
                value = error_action.strip("\"'").lower()
                if value == "silentlycontinue":
                    redirect = "2>/dev/null"
                    i += consumed
                    continue
                if value == "stop":
                    i += consumed
                    continue
                self._todo(lineno, original, f"-ErrorAction {value} 无法映射，已原样保留", category="command")
                extra.extend(args[i:i + consumed])
                i += consumed
                continue
            self._todo(lineno, original, f"参数 {token} 无法映射，已原样保留", category="command")
            extra.append(token)
            i += 1
        if host is None:
            return None
        parts = ["ping", "-c", self._convert_arg(count if count is not None else "1", lineno)]
        parts.append(self._convert_arg(host, lineno))
        parts.extend(extra)
        if redirect:
            parts.append(redirect)
        return " ".join(parts)

    def _warn_join_path_child(self, lineno: int, original: str, child: str) -> None:
        """子路径可能包含目录时提醒：bash 的 ``cp/mv`` 不会自动创建父目录。"""
        if not child:
            return
        looks_like_path = (
            "$" in child
            or "/" in child
            or "\\" in child
            or child.startswith("..")
            or bool(re.match(r"^[A-Za-z]:", child))
        )
        if looks_like_path:
            self._warn(
                lineno,
                "Join-Path 的子路径可能包含子目录，bash 不会自动创建父目录，"
                "请确认目标目录存在或先 mkdir -p",
                original,
                category="path",
            )

    def cmd_join_path(self, lineno: int, args: list[str], original: str) -> str:
        paths = [a for a in args if not a.startswith("-")]
        options = [a for a in args if a.startswith("-") and a.lower() not in ("-path", "-childpath")]
        if options:
            self._warn(
                lineno,
                "Join-Path 选项 " + "、".join(options) + " 无法等价转换，请人工核对",
                original,
                category="path",
            )
        parts = [
            convert_backslashes(strip_outer_quotes(self._replace_vars(p.strip('"'), lineno))[0])
            for p in paths
        ]
        self._needs_join_path = True
        for child in parts[1:]:
            self._warn_join_path_child(lineno, original, child)
        return "$(__bat2sh_join_path " + " ".join(dq(p) for p in parts) + ")"

    def cmd_split_path(self, lineno: int, args: list[str], original: str) -> str | None:
        path = next((a for a in args if not a.startswith("-")), None)
        if path is None:
            return None
        target = self._convert_arg(path, lineno)
        if any(a.lower() == "-leaf" for a in args):
            return f"$(basename {target})"
        if any(a.lower() == "-parent" for a in args):
            return f"$(dirname {target})"
        self._todo(lineno, original, "Split-Path 仅支持 -Leaf / -Parent", category="path")
        return None

    def cmd_resolve_path(self, lineno: int, args: list[str], original: str) -> str:
        path = next((a for a in args if not a.startswith("-")), '""')
        return f"$(realpath {self._convert_arg(path, lineno)})"

    def cmd_invoke_webrequest(self, lineno: int, args: list[str], original: str) -> str | None:
        uri = None
        out_file = None
        method = None
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low == "-uri" and i + 1 < len(args):
                uri = args[i + 1]
                i += 2
                continue
            if low == "-outfile" and i + 1 < len(args):
                out_file = args[i + 1]
                i += 2
                continue
            if low == "-method" and i + 1 < len(args):
                method = args[i + 1]
                i += 2
                continue
            if low in ("-useBasicParsing", "-usebasicparsing") or low in ("-headers", "-body") and i + 1 < len(args):
                self._warn(lineno, f"Invoke-WebRequest 的 {args[i]} 未处理", original, category="command")
                i += 2
                continue
            if low.startswith("-"):
                i += 1
                continue
            if uri is None:
                uri = args[i]
            i += 1
        if uri is None:
            return None
        target = self._convert_arg(uri, lineno)
        command = f"curl -L {target}"
        if out_file:
            command = f"curl -L -o {self._convert_arg(out_file, lineno)} {target}"
        if method and method.strip("\"'").upper() != "GET":
            self._warn(lineno, "非 GET 请求请手动补充 curl 参数（-X/-d）", original, category="command")
        return command

    def cmd_expand_archive(self, lineno: int, args: list[str], original: str) -> str | None:
        paths: list[str] = []
        dest = None
        force = False
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low in ("-destinationpath", "-destination") and i + 1 < len(args):
                dest = args[i + 1]
                i += 2
                continue
            if low == "-force":
                force = True
                i += 1
                continue
            if not args[i].startswith("-"):
                paths.append(args[i])
            i += 1
        if not paths:
            return None
        command = f"unzip {'-o ' if force else ''}{self._convert_arg(paths[0], lineno)}"
        if dest:
            command += f" -d {self._convert_arg(dest, lineno)}"
        return command

    def cmd_compress_archive(self, lineno: int, args: list[str], original: str) -> str | None:
        dest = None
        sources: list[str] = []
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low in ("-destinationpath", "-path") and i + 1 < len(args):
                dest = args[i + 1]
                i += 2
                continue
            if low == "-update":
                i += 1
                continue
            if not args[i].startswith("-"):
                sources.append(args[i])
            i += 1
        if dest is None:
            return None
        src_text = " ".join(self._convert_arg(s, lineno) for s in sources)
        return f"zip -r {self._convert_arg(dest, lineno)} {src_text}".strip()

    def cmd_start_sleep(self, lineno: int, args: list[str], original: str) -> str:
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low == "-seconds" and i + 1 < len(args):
                return f"sleep {args[i + 1]}"
            if low == "-milliseconds" and i + 1 < len(args):
                try:
                    return f"sleep {int(args[i + 1]) / 1000:.3f}".rstrip("0").rstrip(".")
                except ValueError:
                    return "sleep 1"
            i += 1
        if args and not args[0].startswith("-"):
            return f"sleep {args[0]}"
        return "sleep 1"

    def cmd_stop_process(self, lineno: int, args: list[str], original: str) -> str | None:
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low in ("-name", "-processname") and i + 1 < len(args):
                name = args[i + 1].strip("\"'")
                name = re.sub(r"(?i)\.exe$", "", name)
                return f"pkill -f {dq(name)}"
            if low in ("-id", "-pid") and i + 1 < len(args):
                return f"kill {args[i + 1]}"
            i += 1
        self._todo(lineno, original, "Stop-Process 参数无法解析", category="command")
        return None

    def cmd_start_process(self, lineno: int, args: list[str], original: str) -> str | None:
        target = None
        wait = False
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low in ("-filepath", "-path") and i + 1 < len(args):
                target = args[i + 1]
                i += 2
                continue
            if low == "-wait":
                wait = True
                i += 1
                continue
            if not args[i].startswith("-") and target is None:
                target = args[i]
            i += 1
        if target is None:
            return None
        converted = self._convert_arg(target, lineno)
        self._warn(lineno, "Start-Process 已转换为 xdg-open/后台执行", original, category="command")
        if wait:
            return f"xdg-open {converted}"
        return f"xdg-open {converted} &"

    def cmd_tee_object(self, lineno: int, args: list[str], original: str) -> str | None:
        append = any(a.lower() == "-append" for a in args)
        path = next((a for a in args if not a.startswith("-")), None)
        if not path:
            return None
        target = self._convert_arg(path, lineno)
        return f"tee {'-a ' if append else ''}{target}".strip()

    def cmd_measure_object(self, lineno: int, args: list[str], original: str) -> str:
        self._warn(lineno, "Measure-Object 已转换为 wc -l", original, category="pipeline")
        if any(a.lower() == "-character" for a in args):
            return "wc -c"
        if any(a.lower() == "-word" for a in args):
            return "wc -w"
        return "wc -l"

    def cmd_select_object(self, lineno: int, args: list[str], original: str) -> str | None:
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low == "-first" and i + 1 < len(args):
                return f"head -n {args[i + 1]}"
            if low == "-last" and i + 1 < len(args):
                return f"tail -n {args[i + 1]}"
            i += 1
        self._todo(lineno, original, "Select-Object 仅支持 -First / -Last", category="pipeline")
        return None

    def cmd_where_object(self, lineno: int, args: list[str], original: str) -> str | None:
        self._todo(
            lineno,
            original,
            "Where-Object 需要管道输入，无法单独转换；"
            "简单条件可写成 Get-ChildItem ... | Where-Object { $_.X -eq \"v\" }",
            category="pipeline",
        )
        return None

    def cmd_foreach_object(self, lineno: int, args: list[str], original: str) -> str | None:
        self._todo(lineno, original, "ForEach-Object（脚本块）无法自动转换，请改用 while read 循环", category="pipeline")
        return None

    def cmd_todo_cmdlet(self, lineno: int, args: list[str], original: str) -> str | None:
        hint = rules.PS_TODO_CMDLETS.get(self._current_cmdlet, "")
        self._todo(lineno, original, hint, category="command")
        return None

    def cmd_service(self, lineno: int, args: list[str], original: str) -> str | None:
        name = next((a for a in args if not a.startswith("-")), None)
        if name is None:
            if self._current_cmdlet == "get-service":
                self._warn(lineno, "Get-Service 已转换为 systemctl list-units", original, category="command")
                return "systemctl list-units --type=service"
            return None
        action = {
            "start-service": "start",
            "stop-service": "stop",
            "restart-service": "restart",
            "get-service": "status",
        }.get(self._current_cmdlet, "status")
        self._warn(lineno, "服务管理已转换为 systemctl", original, category="command")
        return f"systemctl {action} {name.strip(chr(34) + chr(39))}"

    def cmd_get_item(self, lineno: int, args: list[str], original: str) -> str:
        path = next((a for a in args if not a.startswith("-")), '""')
        return f"ls -la {self._convert_arg(path, lineno)}"

    def cmd_get_help(self, lineno: int, args: list[str], original: str) -> str:
        name = next((a for a in args if not a.startswith("-")), "")
        return f"man {name}".strip()

    def _positional_paths(self, args: list[str], value_flags: tuple[str, ...]) -> list[str]:
        paths: list[str] = []
        i = 0
        while i < len(args):
            low = args[i].lower()
            if low in value_flags and i + 1 < len(args):
                paths.append(args[i + 1])
                i += 2
                continue
            if not args[i].startswith("-"):
                paths.append(args[i])
            i += 1
        return paths

    # ------------------------------------------------------------------
    # 流控制语句
    # ------------------------------------------------------------------
    def _convert_flow(self, text: str, lineno: int) -> str:
        m = re.match(r"(?i)^return\b\s*(.*)$", text)
        if m:
            value = m.group(1).strip()
            if not value:
                return "return 0"
            low = value.lower()
            if low == "$true":
                return "return 0"
            if low == "$false":
                return "return 1"
            if re.fullmatch(r"-?\d+", value):
                return f"return {value}"
            if low in ("$null", '""', "''"):
                return "return 0"
            converted = self._convert_expression(value, lineno)
            self._warn(lineno, "return 的返回值已通过 echo 输出，请确认调用方约定", text, category="control_flow")
            return f"echo {converted}; return 0"
        m = re.match(r"(?i)^exit\b\s*(.*)$", text)
        if m:
            code = m.group(1).strip()
            if not code:
                return "exit $?"
            if code.lower() == "$true":
                return "exit 0"
            if code.lower() == "$false":
                return "exit 1"
            return f"exit {self._convert_expression(code, lineno)}"
        m = re.match(r"(?i)^throw\b\s*(.*)$", text)
        if m:
            message = self._convert_expression(m.group(1).strip(), lineno)
            self._warn(lineno, "throw 已转换为 echo + exit 1", text, category="control_flow")
            return f"echo {message} >&2; exit 1"
        if re.match(r"(?i)^break\b", text):
            return "break"
        return "continue"

    # ------------------------------------------------------------------
    # 块闭合
    # ------------------------------------------------------------------
    def _close_block_line(self, lineno: int, text: str) -> list[str]:
        if text.startswith("}"):
            rest = text[1:].strip()
        else:
            rest = text.strip()
        if not rest:
            if self._stack and self._stack[-1].kind == "try":
                self._try_inline_pending = True
                return []
            return self._pop_block(lineno)
        low = rest.lower()
        if low.startswith("elseif") or low.startswith("else if"):
            after = re.sub(r"(?i)^else\s*", "", rest).strip()
            if self._stack:
                self._stack.pop()
            header = self._match_condition_header(after)
            if header is None:
                self._warn(lineno, "无法解析 elseif 条件", text, category="control_flow")
                return [self._c("# TODO: 手动检查: " + text)]
            keyword, cond, inline, block_open = header
            return self._emit_condition_block(lineno, text, "elseif", cond, inline, block_open)
        if low.startswith("else"):
            if self._stack:
                self._stack.pop()
            after = rest[4:].strip()
            lines = [self._c("else")]
            block = _Block("else", "fi")
            block.body_mark = len(self._out) + len(lines)
            self._stack.append(block)
            inline = ""
            if after.startswith("{"):
                close = find_matching(after, "{", "}")
                if close > 0:
                    inline = after[1:close].strip()
                else:
                    inline = after[1:].strip()
            if inline:
                lines.extend(self._convert_line(lineno, inline))
            if after.startswith("{") and (not after.endswith("}") or after == "{"):
                return lines
            self._stack.pop()
            if not inline:
                lines.append(self._c(":"))
            lines.append(self._c("fi"))
            return lines
        if low.startswith("catch"):
            return self._handle_catch(lineno, text, rest)
        if low.startswith("finally"):
            return self._handle_finally(lineno, text, rest)
        if low.startswith("while"):
            m = re.match(r"(?i)^while\s*\((.*)\)\s*$", rest)
            cond = self._convert_condition(m.group(1), lineno) if m else "0 -eq 0"
            lines: list[str] = []
            if self._stack:
                lines.append(self._c(f"if ! {cond}; then break; fi"))
                self._stack.pop()
            lines.append(self._c("done"))
            return lines
        return self._pop_block(lineno)

    @staticmethod
    def _parse_block_body(after: str) -> tuple[str, bool]:
        after = after.strip()
        if after.startswith("{"):
            close = find_matching(after, "{", "}")
            if close > 0:
                return after[1:close].strip(), close == len(after) - 1
            return after[1:].strip(), False
        return after, True

    @staticmethod
    def _is_effectful(line: str) -> bool:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return False
        if stripped in ("fi", "done", "else", "esac", "}"):
            return False
        return not stripped.endswith(("; then", "; do"))

    def _handle_catch(self, lineno: int, text: str, rest: str) -> list[str]:
        after = rest[5:].strip()
        type_name = ""
        if after.startswith("["):
            close_type = find_matching(after, "[", "]")
            if close_type > 0:
                type_name = after[1:close_type].strip()
                after = after[close_type + 1:].strip()
        inline, complete = self._parse_block_body(after)
        if self._try_buffer is None:
            self._warn(lineno, "catch 分支仅保留结构，错误处理逻辑需人工转换", text, category="control_flow")
            lines = [self._c("else  # TODO: catch 块")]
            if inline:
                lines.extend(self._convert_line(lineno, inline))
            if complete:
                if not inline:
                    lines.append(self._c(":"))
                lines.append(self._c("fi"))
            else:
                block = _Block("catch", "fi")
                block.body_mark = len(self._out) + len(lines)
                self._stack.append(block)
            return lines
        buffer = self._try_buffer
        self._try_buffer = None
        self._try_inline_pending = False
        if self._stack and self._stack[-1].kind == "try":
            self._stack.pop()
        meaningful = [line for line in buffer if line.strip()]
        effectful = [line for line in meaningful if self._is_effectful(line)]
        if not type_name and len(effectful) == 1 and len(meaningful) == 1:
            self._warn(
                lineno,
                "try/catch 已近似转换为 if ! 判断：仅在命令失败时执行 catch，"
                "PowerShell 异常语义可能不同，请核对",
                text,
                category="control_flow",
            )
            lines = [self._c(f"if ! {effectful[0].strip()}; then")]
            if inline:
                lines.extend(self._convert_line(lineno, inline))
            if complete:
                if not inline:
                    lines.append(self._c(":"))
                lines.append(self._c("fi"))
            else:
                block = _Block("catch", "fi")
                block.body_mark = len(self._out) + len(lines)
                self._stack.append(block)
            return lines
        self._warn(lineno, "try/catch 已简化处理：try 体直接执行，catch 分支仅保留结构", text, category="control_flow")
        if type_name:
            self._warn(
                lineno,
                f"catch 类型 {type_name} 已忽略，错误处理逻辑需人工转换，请核对",
                text,
                category="control_flow",
            )
        lines = [self._c("if true; then  # TODO: try/catch 未等价转换")]
        if not any(self._is_effectful(line) for line in buffer):
            lines.append(self._c(":"))
        lines.extend(buffer)
        lines.append(self._c("else  # TODO: catch 块"))
        if inline:
            lines.extend(self._convert_line(lineno, inline))
        if complete:
            if not inline:
                lines.append(self._c(":"))
            lines.append(self._c("fi"))
        else:
            block = _Block("catch", "fi")
            block.body_mark = len(self._out) + len(lines)
            self._stack.append(block)
        return lines

    def _handle_finally(self, lineno: int, text: str, rest: str) -> list[str]:
        lines: list[str] = []
        if self._try_buffer is not None:
            if self._stack and self._stack[-1].kind == "try":
                self._stack.pop()
            lines.extend(self._try_buffer)
            self._try_buffer = None
            self._try_inline_pending = False
        elif self._stack and self._stack[-1].kind in ("try", "catch"):
            block = self._stack.pop()
            if block.body_mark >= 0 and len(self._out) == block.body_mark:
                lines.append(self._c(":"))
            if block.close_word:
                lines.append(self._c(block.close_word))
        self._warn(lineno, "finally 块总是执行，已转换为独立的 if true 块，请核对", text, category="control_flow")
        lines.append(self._c("if true; then  # TODO: finally 块总是执行"))
        after = rest[7:].strip()
        inline, complete = self._parse_block_body(after)
        if inline:
            lines.extend(self._convert_line(lineno, inline))
        if complete:
            if not inline:
                lines.append(self._c(":"))
            lines.append(self._c("fi"))
        else:
            block = _Block("finally", "fi")
            block.body_mark = len(self._out) + len(lines)
            self._stack.append(block)
        return lines

    def _pop_block(self, lineno: int) -> list[str]:
        if not self._stack:
            self._warn(lineno, "多余的 '}'", "", category="misc")
            return [self._c("# 多余的 }，已忽略")]
        block = self._stack.pop()
        lines: list[str] = []
        if block.body_mark >= 0 and len(self._out) == block.body_mark:
            lines.append(self._c(":"))
        if block.close_word:
            lines.append(self._c(block.close_word))
        return lines

    # ------------------------------------------------------------------
    # 收尾
    # ------------------------------------------------------------------
    def _finish(self) -> None:
        if self._pipe_buffer is not None:
            joined = " ".join(self._pipe_buffer)
            self._pipe_buffer = None
            self._out.append(
                self._c(self._todo(0, joined, "行尾管道未找到后续命令行，未转换", category="misc"))
            )
        if self._try_buffer is not None:
            self._warn(
                self._try_lineno,
                "try 块未找到 catch/finally/结束花括号，已按顺序执行 try 体",
                category="control_flow",
            )
            self._out.extend(self._try_buffer)
            self._try_buffer = None
            self._try_inline_pending = False
            while self._stack and self._stack[-1].kind == "try":
                self._stack.pop()
        if self._here_end is not None:
            self._warn(
                self._here_lineno,
                "here-string 未找到结束标记，内容已丢弃，请人工检查",
                self._here_end,
                category="strings",
            )
            self._out.append(self._c("# TODO: here-string 未闭合，请人工检查"))
            self._here_end = None
            self._here_lines = []
        while self._stack:
            block = self._stack.pop()
            if block.kind == "comment":
                continue
            self._warn(0, f"{block.kind} 块未正常闭合，已自动补全", category="misc")
            if block.close_word:
                self._out.append(block.close_word)
