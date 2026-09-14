"""设置、差异预览、报告、关于对话框、API 修复对话框。"""

from __future__ import annotations

import difflib
import time

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QTextCharFormat, QTextCursor
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
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import APP_DESCRIPTION, APP_DISPLAY_NAME, APP_HOMEPAGE, __version__
from ..core.api import fixer
from ..core.api.config import ApiConfig, missing_requirements
from ..core.api.provider import (
    ProviderError,
    create_provider,
    error_category,
    redact,
)
from ..core.settings import (
    INDENT_CHOICES,
    ConvertSettings,
    delete_preset,
    load_presets,
    save_presets,
)
from ..core.syntax import bash_syntax_error
from ..core.types import ConvertReport
from .theme import report_level_color


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: ConvertSettings,
        api_config: ApiConfig | None = None,
        parent: QWidget | None = None,
        api_test_factory=create_provider,
    ):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(520)
        self._settings = settings
        self._api_config = api_config or ApiConfig()
        self._api_test_factory = api_test_factory
        self._test_worker: ConnectionTestWorker | None = None
        self._test_key = ""
        self._presets: dict[str, ConvertSettings] = {}
        self._build()
        self._load()
        self._reload_presets()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        preset_row = QWidget()
        preset_layout = QHBoxLayout(preset_row)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        self.preset_combo = QComboBox()
        self.preset_combo.setEditable(True)
        self.preset_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.preset_combo.setToolTip("选择预设后点“保存为预设”可覆盖；输入新名称可另存")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        self.preset_combo.editTextChanged.connect(self._update_preset_buttons)
        self.save_preset_button = QPushButton("保存为预设")
        self.save_preset_button.clicked.connect(self._save_preset)
        self.delete_preset_button = QPushButton("删除预设")
        self.delete_preset_button.clicked.connect(self._delete_preset)
        preset_layout.addWidget(self.preset_combo, 1)
        preset_layout.addWidget(self.save_preset_button)
        preset_layout.addWidget(self.delete_preset_button)
        form.addRow("设置预设", preset_row)

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

        self.last_exit_combo = QComboBox()
        self.last_exit_combo.addItem("warn（保守，生成 TODO）", "warn")
        self.last_exit_combo.addItem("map（近似映射为 $?）", "map")
        form.addRow("$LASTEXITCODE 策略", self.last_exit_combo)

        self.run_timeout_spin = QSpinBox()
        self.run_timeout_spin.setRange(1, 3600)
        self.run_timeout_spin.setSuffix(" 秒")
        self.run_timeout_spin.setToolTip("“转换并运行”的默认超时；超时后自动终止脚本（含子进程）")
        form.addRow("运行超时", self.run_timeout_spin)

        api_title = QLabel("API 修复（为无法自动转换的 TODO 获取建议）")
        api_title.setStyleSheet("font-weight: bold;")
        form.addRow(api_title)

        self.api_provider_combo = QComboBox()
        self.api_provider_combo.addItem("OpenAI 兼容", "openai")
        form.addRow("API 类型", self.api_provider_combo)

        self.api_base_edit = QLineEdit()
        self.api_base_edit.setPlaceholderText("https://api.openai.com/v1 或本地端点（必填）")
        form.addRow("API 地址", self.api_base_edit)

        self.api_model_edit = QLineEdit()
        self.api_model_edit.setPlaceholderText("如 gpt-4o-mini（必填）")
        form.addRow("模型", self.api_model_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("留空则使用 BAT2SH_API_KEY 环境变量")
        form.addRow("API key", self.api_key_edit)

        self.api_timeout_spin = QSpinBox()
        self.api_timeout_spin.setRange(1, 600)
        self.api_timeout_spin.setSuffix(" 秒")
        form.addRow("API 超时", self.api_timeout_spin)

        self.api_context_spin = QSpinBox()
        self.api_context_spin.setRange(0, 10)
        self.api_context_spin.setSuffix(" 行")
        self.api_context_spin.setToolTip("发送给 API 的源文件上下文行数（上限 10；不发送整文件）")
        form.addRow("API 上下文", self.api_context_spin)

        test_row = QWidget()
        test_layout = QHBoxLayout(test_row)
        test_layout.setContentsMargins(0, 0, 0, 0)
        self.api_test_button = QPushButton("测试连接")
        self.api_test_button.setToolTip(
            "用当前填写的地址 / 模型 / key 发送一次最小请求"
            "（固定 10 秒超时，不保存设置、不发送任何文件内容）"
        )
        self.api_test_button.clicked.connect(self._start_api_test)
        self.api_test_status = QLabel("")
        self.api_test_status.setWordWrap(True)
        test_layout.addWidget(self.api_test_button)
        test_layout.addWidget(self.api_test_status, 1)
        form.addRow("连接测试", test_row)

        for editor in (self.api_base_edit, self.api_model_edit, self.api_key_edit):
            editor.textChanged.connect(self._clear_api_test_status_if_idle)
        self.api_provider_combo.currentIndexChanged.connect(self._clear_api_test_status_if_idle)

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
        self._apply_settings(self._settings)

    def _apply_settings(self, settings: ConvertSettings) -> None:
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
        exit_index = self.last_exit_combo.findData(settings.last_exit_code)
        self.last_exit_combo.setCurrentIndex(max(0, exit_index))
        self.run_timeout_spin.setValue(int(settings.run_timeout))
        theme_index = self.theme_combo.findData(settings.theme)
        self.theme_combo.setCurrentIndex(max(0, theme_index))
        self._apply_api_config(self._api_config)

    def _apply_api_config(self, api_config: ApiConfig) -> None:
        api_config = api_config.normalized()
        provider_index = self.api_provider_combo.findData(api_config.provider)
        self.api_provider_combo.setCurrentIndex(max(0, provider_index))
        self.api_base_edit.setText(api_config.base_url)
        self.api_model_edit.setText(api_config.model)
        self.api_key_edit.setText(api_config.api_key)
        self.api_timeout_spin.setValue(int(api_config.timeout))
        self.api_context_spin.setValue(api_config.context_lines)

    # -- API 连接测试 ------------------------------------------------

    def _clear_api_test_status_if_idle(self, *_args) -> None:
        if self._test_worker is not None:
            return
        self.api_test_status.clear()
        self.api_test_status.setToolTip("")

    def _show_api_test_result(self, ok: bool, message: str) -> None:
        color = "#43a047" if ok else "#e53935"
        mark = "✓" if ok else "✗"
        self.api_test_status.setStyleSheet(f"color: {color};")
        self.api_test_status.setText(f"{mark} {message}")

    def _start_api_test(self) -> None:
        if self._test_worker is not None:
            return
        config = self.result_api_config()
        missing = missing_requirements(config)
        if missing:
            self._show_api_test_result(False, "缺少配置：" + "；".join(missing))
            return
        try:
            provider = self._api_test_factory(config)
        except ProviderError as exc:
            self._show_api_test_result(
                False, f"{error_category(exc)}：{redact(str(exc), config.api_key)}"
            )
            return
        self._test_key = config.api_key
        self.api_test_button.setEnabled(False)
        self.api_test_status.setStyleSheet("color: palette(mid);")
        self.api_test_status.setText("正在连接 …")
        self.api_test_status.setToolTip("")
        worker = ConnectionTestWorker(provider)
        _LIVE_TEST_WORKERS.add(worker)
        worker.succeeded.connect(self._on_api_test_succeeded)
        worker.failed.connect(self._on_api_test_failed)
        worker.finished.connect(self._on_api_test_finished)
        worker.finished.connect(lambda: _LIVE_TEST_WORKERS.discard(worker))
        worker.finished.connect(worker.deleteLater)
        self._test_worker = worker
        worker.start()

    def _on_api_test_succeeded(self, reply: str, elapsed_ms: float) -> None:
        self._show_api_test_result(True, f"连接成功（{elapsed_ms:.0f} ms）")
        if reply:
            self.api_test_status.setToolTip(redact(reply[:200], self._test_key))

    def _on_api_test_failed(self, message: str) -> None:
        self._show_api_test_result(False, redact(message, self._test_key))

    def _on_api_test_finished(self) -> None:
        self._test_worker = None
        self.api_test_button.setEnabled(True)

    def _reload_presets(self) -> None:
        self._presets = load_presets()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("（自定义）", None)
        for name in self._presets:
            self.preset_combo.addItem(name, name)
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)
        self._update_preset_buttons()

    def _update_preset_buttons(self) -> None:
        name = self.preset_combo.currentText().strip()
        self.save_preset_button.setEnabled(bool(name) and name != "（自定义）")
        self.delete_preset_button.setEnabled(self.preset_combo.currentData() is not None)

    def _on_preset_selected(self, index: int) -> None:
        name = self.preset_combo.itemData(index)
        if name and name in self._presets:
            self._apply_settings(self._presets[name])
        self._update_preset_buttons()

    def _save_preset(self) -> None:
        name = self.preset_combo.currentText().strip()
        if not name or name == "（自定义）":
            return
        save_presets(name, self.result_settings())
        self._reload_presets()
        index = self.preset_combo.findText(name)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)

    def _delete_preset(self) -> None:
        name = self.preset_combo.currentData()
        if not name:
            return
        delete_preset(name)
        self._reload_presets()
        self.preset_combo.setCurrentIndex(0)

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
            last_exit_code=self.last_exit_combo.currentData(),
            run_timeout=float(self.run_timeout_spin.value()),
            theme=self.theme_combo.currentData(),
            last_dir=self._settings.last_dir,
        )
        return settings.normalized()


    def result_api_config(self) -> ApiConfig:
        return ApiConfig(
            provider=self.api_provider_combo.currentData(),
            base_url=self.api_base_edit.text(),
            model=self.api_model_edit.text(),
            api_key=self.api_key_edit.text(),
            timeout=float(self.api_timeout_spin.value()),
            max_retries=self._api_config.max_retries,
            context_lines=self.api_context_spin.value(),
        ).normalized()


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
    def __init__(
        self,
        title: str,
        blocks: list[tuple[str, str]],
        dark: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        self.viewer.setPlainText("\n".join(text for text, _level in blocks))
        selections: list[QTextEdit.ExtraSelection] = []
        offset = 0
        for text, level in blocks:
            color = report_level_color(level, dark)
            if color is not None and text:
                selection = QTextEdit.ExtraSelection()
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(color))
                selection.format = fmt
                cursor = self.viewer.textCursor()
                cursor.setPosition(offset)
                cursor.setPosition(offset + len(text), QTextCursor.MoveMode.KeepAnchor)
                selection.cursor = cursor
                selections.append(selection)
            offset += len(text) + 1
        self.viewer.setExtraSelections(selections)
        layout.addWidget(self.viewer)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class RunConfirmDialog(QDialog):
    def __init__(
        self,
        title: str,
        header: str,
        body: str,
        confirm_text: str = "执行",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(860, 620)
        layout = QVBoxLayout(self)
        header_label = QLabel(header)
        header_label.setWordWrap(True)
        layout.addWidget(header_label)
        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        self.viewer.setPlainText(body)
        layout.addWidget(self.viewer, 1)
        buttons = QDialogButtonBox()
        confirm_button = buttons.addButton(
            confirm_text, QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        confirm_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class TodoFixWorker(QThread):
    """后台执行一次 Provider 调用，避免阻塞 GUI 事件循环。"""

    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, provider, prompt: str, timeout: float, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._prompt = prompt
        self._timeout = timeout

    def run(self) -> None:
        try:
            raw = self._provider.complete(self._prompt, timeout=self._timeout)
        except ProviderError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # GUI 不应因意外 Provider 异常崩溃
            self.failed.emit(f"意外错误: {exc}")
        else:
            self.succeeded.emit(raw)


_LIVE_TEST_WORKERS: set[ConnectionTestWorker] = set()


class ConnectionTestWorker(QThread):
    """后台执行一次最小请求（固定 10 秒超时），回传延迟毫秒，避免阻塞 GUI。"""

    succeeded = Signal(str, float)
    failed = Signal(str)

    PROMPT = "say ok"
    TIMEOUT = 10.0

    def __init__(self, provider, parent=None):
        super().__init__(parent)
        self._provider = provider

    def run(self) -> None:
        started = time.monotonic()
        try:
            reply = self._provider.complete(self.PROMPT, timeout=self.TIMEOUT)
        except ProviderError as exc:
            self.failed.emit(f"{error_category(exc)}：{exc}")
        except Exception as exc:  # GUI 不应因意外 Provider 异常崩溃
            self.failed.emit(f"意外错误：{exc}")
        else:
            self.succeeded.emit(reply, (time.monotonic() - started) * 1000.0)


# 保活集合：设置对话框关闭/销毁后，仍在运行的测试线程不被 GC 提前销毁（否则 Qt 直接 abort）。
_LIVE_TEST_WORKERS: set[ConnectionTestWorker] = set()


class TodoFixDialog(QDialog):
    """逐条 API 修复：标记列表 + 发送前 payload 展示 + diff 预览 + 应用/跳过。

    变更只在内存中累积，关闭后由主窗口写回编辑器（不自动落盘，决策 7）。
    """

    def __init__(
        self,
        output_text: str,
        report: ConvertReport | None,
        source_text: str,
        api_config: ApiConfig,
        provider_factory=create_provider,
        dark: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("API 修复 TODO（建议需人工复核）")
        self.resize(1200, 780)
        self._source_text = source_text
        self._api_config = api_config
        self._provider_factory = provider_factory
        self._dark = dark
        self._markers = fixer.scan_todo_markers(output_text, report)
        self._text = output_text
        self._offset = 0
        self._index = 0
        self._pending_marker: fixer.TodoMarker | None = None
        self._pending_prompt = ""
        self._pending_replacement = ""
        self._candidate = ""
        self._applied = 0
        self._worker: TodoFixWorker | None = None
        self._closed = False
        self._build()
        self._select_current()

    @property
    def applied_count(self) -> int:
        return self._applied

    def result_text(self) -> str:
        return self._text

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("待处理标记"))
        self.marker_list = QListWidget()
        for index, marker in enumerate(self._markers):
            self.marker_list.addItem(self._marker_label(index, marker))
        left_layout.addWidget(self.marker_list, 1)
        note = QLabel("逐条处理：发送前核对将离开本机的内容；应用前查看差异。")
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        left_layout.addWidget(note)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("将发送的内容（原文，可复核）"))
        self.payload_view = QPlainTextEdit()
        self.payload_view.setReadOnly(True)
        right_layout.addWidget(self.payload_view, 1)
        right_layout.addWidget(QLabel("修复建议差异（当前 → 建议）"))
        self.diff_view = QTextBrowser()
        self.diff_view.setOpenExternalLinks(False)
        right_layout.addWidget(self.diff_view, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 880])
        layout.addWidget(splitter, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.privacy_label = QLabel()
        self.privacy_label.setWordWrap(True)
        self.privacy_label.setStyleSheet("color: palette(mid);")
        buttons.addWidget(self.privacy_label, 1)
        self.send_button = QPushButton("发送本条并获取建议")
        self.send_button.clicked.connect(self._start_request)
        self.apply_button = QPushButton("应用这条修改")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_current)
        self.skip_button = QPushButton("跳过本条")
        self.skip_button.clicked.connect(self._skip_current)
        buttons.addWidget(self.send_button)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.skip_button)
        layout.addLayout(buttons)

        footer = QHBoxLayout()
        hint = QLabel("API 建议仍需人工复核，不保证语义正确；保存文件仍由主界面完成。")
        hint.setStyleSheet("color: palette(mid);")
        footer.addWidget(hint, 1)
        discard_button = QPushButton("放弃本次修复")
        discard_button.clicked.connect(self.reject)
        done_button = QPushButton("完成")
        done_button.setDefault(True)
        done_button.clicked.connect(self.accept)
        footer.addWidget(discard_button)
        footer.addWidget(done_button)
        layout.addLayout(footer)

    def closeEvent(self, event) -> None:
        self._closed = True
        event.accept()
        self.accept()

    def _current_marker(self) -> fixer.TodoMarker | None:
        if 0 <= self._index < len(self._markers):
            return self._markers[self._index]
        return None

    def _marker_label(self, index: int, marker: fixer.TodoMarker) -> str:
        text = marker.marker_text if len(marker.marker_text) <= 72 else marker.marker_text[:72] + "…"
        return f"{index + 1}. 第 {marker.out_line} 行: {text}"

    def _select_current(self) -> None:
        marker = self._current_marker()
        if marker is None:
            self.marker_list.clearSelection()
            self.payload_view.setPlainText("")
            self.diff_view.clear()
            self.send_button.setEnabled(False)
            self.apply_button.setEnabled(False)
            self.skip_button.setEnabled(False)
            self.privacy_label.setText("")
            self.status_label.setText(
                f"全部处理完成：已应用 {self._applied} 处（关闭后写回编辑器，保存仍由主界面完成）。"
            )
            return
        self.marker_list.setCurrentRow(self._index)
        effective = marker.out_line + self._offset
        self._pending_marker = marker
        self._pending_prompt = fixer.build_prompt(
            marker,
            self._source_text,
            "源脚本",
            self._text,
            self._api_config.context_lines,
            out_line=effective,
        )
        self.payload_view.setPlainText(self._pending_prompt)
        self.diff_view.clear()
        self.privacy_label.setText(
            f"点击“发送本条并获取建议”即确认将上方内容发送到 {self._api_config.base_url}"
            "（内容将离开本机，可能被服务提供方记录）。"
        )
        self.status_label.setText(
            f"待处理 {self._index + 1}/{len(self._markers)}：核对将发送的内容。"
        )
        self.send_button.setEnabled(True)
        self.apply_button.setEnabled(False)
        self.skip_button.setEnabled(True)

    def _start_request(self) -> None:
        marker = self._pending_marker
        if marker is None or self._worker is not None:
            return
        try:
            provider = self._provider_factory(self._api_config)
        except ProviderError as exc:
            self.status_label.setText(f"API 配置错误：{exc}")
            return
        self.send_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.status_label.setText(f"请求中（{self._api_config.base_url}）…")
        worker = TodoFixWorker(provider, self._pending_prompt, self._api_config.timeout)
        worker.succeeded.connect(self._on_response)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def _on_worker_finished(self) -> None:
        self._worker = None

    def _on_failure(self, message: str) -> None:
        if self._closed:
            return
        self.status_label.setText(
            "API 调用失败（本条保留 TODO）："
            + redact(message, self._api_config.api_key)
        )
        self.send_button.setEnabled(True)
        self.skip_button.setEnabled(True)

    def _on_response(self, raw: str) -> None:
        if self._closed:
            return
        marker = self._pending_marker
        if marker is None:
            return
        replacement = fixer.clean_completion(raw)
        if (
            not replacement
            or "# TODO" in replacement
            or replacement.strip() == marker.line_text.strip()
        ):
            self.status_label.setText("模型未给出可用修改，本条保留 TODO（可跳过）。")
            self.send_button.setEnabled(True)
            self.skip_button.setEnabled(True)
            return
        effective = marker.out_line + self._offset
        candidate = fixer.apply_replacement(self._text, effective, replacement)
        problem = bash_syntax_error(candidate)
        if problem:
            self.status_label.setText(f"建议未通过 bash -n，已拒绝：{problem}")
            self.send_button.setEnabled(True)
            self.skip_button.setEnabled(True)
            return
        self._pending_replacement = replacement
        self._candidate = candidate
        self.diff_view.setHtml(
            build_diff_html(self._text, candidate, "当前脚本", "修复建议", self._dark)
        )
        self.status_label.setText("已收到建议：核对差异后选择“应用这条修改”或“跳过本条”。")
        self.apply_button.setEnabled(True)
        self.skip_button.setEnabled(True)

    def _apply_current(self) -> None:
        if not self._candidate:
            return
        self._offset += fixer.replacement_line_count(self._pending_replacement) - 1
        self._text = self._candidate
        self._applied += 1
        self._pending_replacement = ""
        self._candidate = ""
        self._advance()

    def _skip_current(self) -> None:
        self._pending_replacement = ""
        self._candidate = ""
        self._advance()

    def _advance(self) -> None:
        self._index += 1
        self._select_current()


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
