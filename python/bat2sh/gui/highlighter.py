"""语法高亮：批处理 / PowerShell / Bash 与 TODO 行强调。"""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


def _fmt(color: str, bold: bool = False, italic: bool = False, bg: str | None = None) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    if bg:
        fmt.setBackground(QColor(bg))
    return fmt


def _colors(dark: bool) -> dict[str, str]:
    if dark:
        return {
            "comment": "#7f9e7f",
            "keyword": "#6fb3ff",
            "command": "#c3e88d",
            "variable": "#f2b76f",
            "string": "#e2a07a",
            "number": "#d1a0f0",
            "operator": "#9fc4e8",
            "label": "#e5c07b",
            "todo_bg": "#8b2f2f",
            "todo_fg": "#ffe9e9",
            "warn_fg": "#ffb454",
        }
    return {
        "comment": "#5b7a5b",
        "keyword": "#1565c0",
        "command": "#2e7d32",
        "variable": "#b06000",
        "string": "#a13d2d",
        "number": "#7b3fa0",
        "operator": "#3b6ea5",
        "label": "#8a6d1a",
        "todo_bg": "#ffd6d6",
        "todo_fg": "#8b0000",
        "warn_fg": "#b26a00",
    }


_BATCH_RULES: tuple[tuple[str, str, bool], ...] = (
    (r"^\s*(::|(?i:rem)\b).*$", "comment", False),
    (r"^\s*:[A-Za-z_][\w.\-]*", "label", True),
    (r"%[A-Za-z_][A-Za-z0-9_]*%|%%[A-Za-z0-9*]|%~?[A-Za-z0-9*]", "variable", False),
    (r"\b(?i:if|else|for|in|do|goto|call|set|exit|shift|not|exist|defined|errorlevel|start)\b", "keyword", True),
    (
        r"\b(?i:echo|dir|copy|xcopy|robocopy|move|del|erase|mkdir|md|rmdir|rd|type|cls|cd|chdir|pause|"
        r"ping|ipconfig|netstat|tasklist|taskkill|findstr|find|fc|comp|where|attrib|mklink|timeout|"
        r"title|color|chcp|powershell|runas|shutdown|ver|systeminfo|choice|call|set)\b",
        "command",
        False,
    ),
    (r"\"[^\"]*\"", "string", False),
    (r"\b\d+\b", "number", False),
    (r"[<>|&]|>>?", "operator", False),
)

_PS_RULES: tuple[tuple[str, str, bool], ...] = (
    (r"#.*$", "comment", False),
    (
        r"\b(?i:if|elseif|else|foreach|for|while|do|until|switch|function|param|try|catch|finally|"
        r"return|break|continue|throw|exit|in|filter|process|begin|end)\b",
        "keyword",
        True,
    ),
    (r"\b[A-Z][a-z]+-[A-Z]\w+\b", "command", False),
    (r"\$env:[A-Za-z_]\w*|\$\{?[A-Za-z_]\w*\}?|\$[@?$!*#_]", "variable", False),
    (r"(?i)-(eq|ne|gt|lt|ge|le|and|or|not|xor|like|notlike|match|replace|join|split|contains)\b", "operator", False),
    (r"\"[^\"]*\"|'[^']*'", "string", False),
    (r"\b\d+(\.\d+)?\b", "number", False),
    (r"\|+|&&|\|\|", "operator", False),
)

_BASH_RULES: tuple[tuple[str, str, bool], ...] = (
    (r"^#!.*$", "keyword", True),
    (r"#.*$", "comment", False),
    (
        r"\b(if|then|else|elif|fi|for|in|do|done|while|until|case|esac|function|select|return|exit|"
        r"local|export|declare|readonly|set|shift|source|break|continue|eval|trap)\b",
        "keyword",
        True,
    ),
    (
        r"\b(echo|printf|read|cd|pwd|ls|cp|mv|rm|mkdir|rmdir|touch|cat|grep|sed|awk|find|xargs|"
        r"chmod|chown|sleep|clear|pkill|kill|xdg-open|basename|dirname|seq|env|date|systemctl|"
        r"curl|wget|tar|zip|unzip|rsync|tee|tail|head|sort|wc|true|false|command|realpath|readlink|"
        r"pushd|popd|nohup|rsync|zip)\b",
        "command",
        False,
    ),
    (r"\$\{[^}]*\}|\$[A-Za-z_]\w*|\$[@?$!*#0-9-]", "variable", False),
    (r"\"(\\.|[^\"\\])*\"|'[^']*'", "string", False),
    (r"\b\d+\b", "number", False),
    (r"&&|\|\||[|&]|>>?|<<?|=\~", "operator", False),
)

_TODO_RE = r"^#\s*TODO.*$"
_WARN_RE = r"^#\s*(?:WARN|警告).*$"


class RuleHighlighter(QSyntaxHighlighter):
    def __init__(self, document, rules, dark: bool):
        super().__init__(document)
        colors = _colors(dark)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        for pattern, color_key, bold in rules:
            regex = QRegularExpression(
                pattern,
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            )
            self._rules.append((regex, _fmt(colors[color_key], bold=bold)))
        self._todo_fmt = _fmt(colors["todo_fg"], bold=True, bg=colors["todo_bg"])
        self._warn_fmt = _fmt(colors["warn_fg"], bold=True)

    def highlightBlock(self, text: str) -> None:
        for regex, fmt in self._rules:
            iterator = regex.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)
        todo = QRegularExpression(_TODO_RE, QRegularExpression.PatternOption.CaseInsensitiveOption)
        iterator = todo.globalMatch(text)
        while iterator.hasNext():
            match = iterator.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self._todo_fmt)
        warn = QRegularExpression(_WARN_RE, QRegularExpression.PatternOption.CaseInsensitiveOption)
        iterator = warn.globalMatch(text)
        while iterator.hasNext():
            match = iterator.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self._warn_fmt)


class BatchHighlighter(RuleHighlighter):
    def __init__(self, document, dark: bool = False):
        super().__init__(document, _BATCH_RULES, dark)


class PowerShellHighlighter(RuleHighlighter):
    def __init__(self, document, dark: bool = False):
        super().__init__(document, _PS_RULES, dark)


class BashHighlighter(RuleHighlighter):
    def __init__(self, document, dark: bool = False):
        super().__init__(document, _BASH_RULES, dark)


def highlighter_for(kind: str, document, dark: bool) -> RuleHighlighter:
    if kind == "bat":
        return BatchHighlighter(document, dark)
    if kind == "ps1":
        return PowerShellHighlighter(document, dark)
    return BashHighlighter(document, dark)
