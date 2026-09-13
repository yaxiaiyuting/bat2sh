"""设置、差异预览、报告、关于对话框。"""

from __future__ import annotations

import difflib

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import APP_DESCRIPTION, APP_DISPLAY_NAME, APP_HOMEPAGE, __version__
from ..core.settings import INDENT_CHOICES, ConvertSettings


class SettingsDialog(QDialog):
    def __init__(self, settings: ConvertSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(520)
        self._settings = settings
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        directory_row = QWidget()
        directory_layout = QHBoxLayout(directory_row)
        directory_layout.setContentsMargins(0, 0, 0, 0)
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("默认：与源文件同目录")
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_output_dir)
        directory_layout.addWidget(self.output_dir_edit)
        directory_layout.addWidget(browse)
        form.addRow("输出目录", directory_row)

        self.suffix_edit = QLineEdit()
        fmt = self.suffix_edit
        fmt.setPlaceholderText(".sh")
        form.addRow("输出后缀", self.suffix_edit)

        self.exec_check = QCheckBox("转换后自动添加可执行权限 (chmod +x)")
        form.addRow("", self.exec_check)

        self.backup_check = QCheckBox("覆盖已存在的输出文件前备份")
        form.addRow("", self.backup_check)

        self.backup_source_check = QCheckBox("转换前备份源文件")
        form.addRow("", self.backup_source_check)

        self.overwrite_check = QCheckBox("允许覆盖输出文件（关闭时已存在的文件不会被覆盖）")
        form.addRow("", self.overwrite_check)

        self.indent_combo = QComboBox()
        self.indent_combo.addItems(list(INDENT_CHOICES.keys()))
        form.addRow("缩进风格", self.indent_combo)

        self.quote_check = QCheckBox("为变量加双引号（防止空格导致的问题）")
        form.addRow("", self.quote_check)

        self.strict_check = QCheckBox("严格模式：脚本开头添加 set -euo pipefail")
        form.addRow("", self.strict_check)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        form.addRow("界面主题", self.theme_combo)

        layout.addLayout(form)

        encoding_note = QLabel(
            "输入编码在打开文件时自动检测（UTF-8 BOM → UTF-8 → GBK → Latin-1），"
            "可在主界面工具栏下方手动覆盖；输出统一为 UTF-8 无 BOM、LF 行尾。"
        )
        encoding_note.setWordWrap(True)
        encoding_note.setStyleSheet("color: palette(mid);")
        layout.addWidget(encoding_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir_edit.text())
        if directory:
            self.output_dir_edit.setText(directory)

    def _load(self) -> None:
        settings = self._settings
        self.output_dir_edit.setText(settings.output_dir or "")
        self.suffix_edit.setText(settings.suffix)
        self.exec_check.setChecked(settings.make_executable)
        self.backup_check.setChecked(settings.backup_existing)
        self.backup_source_check.setChecked(settings.backup_source)
        self.overwrite_check.setChecked(settings.overwrite)
        index = self.indent_combo.findText(settings.indent_label())
        self.indent_combo.setCurrentIndex(max(0, index))
        self.quote_check.setChecked(settings.quote_variables)
        self.strict_check.setChecked(settings.strict_mode)
        theme_index = self.theme_combo.findData(settings.theme)
        self.theme_combo.setCurrentIndex(max(0, theme_index))

    def result_settings(self) -> ConvertSettings:
        settings = ConvertSettings(
            output_dir=self.output_dir_edit.text().strip() or None,
            suffix=self.suffix_edit.text().strip() or ".sh",
            overwrite=self.overwrite_check.isChecked(),
            backup_existing=self.backup_check.isChecked(),
            backup_source=self.backup_source_check.isChecked(),
            make_executable=self.exec_check.isChecked(),
            indent=INDENT_CHOICES[self.indent_combo.currentText()],
            quote_variables=self.quote_check.isChecked(),
            strict_mode=self.strict_check.isChecked(),
            theme=self.theme_combo.currentData(),
            last_dir=self._settings.last_dir,
        )
        return settings.normalized()


def build_diff_html(
    source_text: str,
    output_text: str,
    source_name: str,
    output_name: str,
    dark: bool,
) -> str:
    """构造差异预览的 HTML（含深/浅色包装），不依赖 Qt。"""
    html = difflib.HtmlDiff(wrapcolumn=100).make_table(
        source_text.splitlines(),
        output_text.splitlines(),
        fromdesc=source_name,
        todesc=output_name,
        context=True,
        numlines=4,
    )
    background = "#232629" if dark else "#fcfcfc"
    foreground = "#eff0f1" if dark else "#232629"
    return f"<div style='background:{background};color:{foreground};'>{html}</div>"


class DiffDialog(QDialog):
    def __init__(
        self,
        source_text: str,
        output_text: str,
        source_name: str,
        output_name: str,
        dark: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("预览差异")
        self.resize(1100, 720)
        layout = QVBoxLayout(self)
        header = QLabel(f"{source_name}  →  {output_name}")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(
            build_diff_html(source_text, output_text, source_name, output_name, dark)
        )
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class ReportDialog(QDialog):
    def __init__(self, title: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(text)
        layout.addWidget(viewer)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("关于")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        title = QLabel(f"<h2>{APP_DISPLAY_NAME}</h2>")
        layout.addWidget(title)
        version = QLabel(f"版本 {__version__}")
        layout.addWidget(version)
        description = QLabel(APP_DESCRIPTION)
        description.setWordWrap(True)
        layout.addWidget(description)
        details = QLabel(
            "将 Windows 批处理与 PowerShell 脚本转换为 Bash 脚本。<br>"
            "无法自动转换的语句会插入 <code># TODO: 手动检查</code> 注释，"
            "并在预览中以红色背景标出。<br><br>"
            "技术栈：Python 3 + PySide6（Qt6），遵循 KDE Breeze 风格，"
            "在 Wayland 会话下原生运行。"
        )
        details.setWordWrap(True)
        layout.addWidget(details)
        link = QLabel(f'<a href="{APP_HOMEPAGE}">{APP_HOMEPAGE}</a>')
        link.setOpenExternalLinks(False)
        link.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
        layout.addWidget(link)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
