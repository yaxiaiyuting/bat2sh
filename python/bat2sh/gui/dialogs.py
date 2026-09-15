"""设置、差异预览、报告、关于对话框、API 修复对话框。"""

from __future__ import annotations

import difflib
import threading
import time

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFontDatabase,
    QTextCharFormat,
    QTextCursor,
)
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
    QListWidgetItem,
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
from ..core.api import fixer, parallel
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
        self.api_timeout_spin.setToolTip(
            "空闲超时：流式响应中两次数据到达的最大间隔（默认 30 秒）；超时后自动重试"
        )
        form.addRow("API 超时", self.api_timeout_spin)

        self.enable_thinking_check = QCheckBox("启用思维链（更准但更慢）")
        self.enable_thinking_check.setToolTip(
            "关闭（默认）时请求显式携带 enable_thinking: false（更快）；"
            "开启则交由端点默认行为决定"
        )
        form.addRow("思维链", self.enable_thinking_check)

        self.api_context_spin = QSpinBox()
        self.api_context_spin.setRange(0, 10)
        self.api_context_spin.setSuffix(" 行")
        self.api_context_spin.setToolTip("发送给 API 的源文件上下文行数（上限 10；不发送整文件）")
        form.addRow("API 上下文", self.api_context_spin)

        self.max_concurrency_spin = QSpinBox()
        self.max_concurrency_spin.setRange(1, 16)
        self.max_concurrency_spin.setToolTip(
            "并行修复的并发数（默认 3，范围 1-16）；遇 429 限流会自动降并发"
        )
        form.addRow("修复并发数", self.max_concurrency_spin)

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
        self.enable_thinking_check.setChecked(api_config.enable_thinking)
        self.api_context_spin.setValue(api_config.context_lines)
        self.max_concurrency_spin.setValue(api_config.max_concurrency)

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
            enable_thinking=self.enable_thinking_check.isChecked(),
            max_concurrency=self.max_concurrency_spin.value(),
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


class _StreamCancelled(Exception):
    """内部信号：用户在思考阶段请求停止（不作为错误展示）。"""


class TodoFixWorker(QThread):
    """后台执行一次流式 Provider 调用，避免阻塞 GUI 事件循环。"""

    succeeded = Signal(str)
    failed = Signal(str)
    chunk = Signal(str)
    reasoning = Signal(int)
    warning = Signal(str)
    cancelled = Signal()

    def __init__(self, provider, prompt: str, timeout: float, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._prompt = prompt
        self._timeout = timeout
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """请求停止接收：正文块边界与思维链回调处都会检查（不应用部分输出）。"""
        self._cancel_requested = True

    def _on_reasoning(self, count: int) -> None:
        """思维链回调：思考阶段也能立即响应取消（否则要等到正文才开始检查）。"""
        if self._cancel_requested:
            raise _StreamCancelled
        self.reasoning.emit(count)

    def run(self) -> None:
        stream = None
        chunks: list[str] = []
        try:
            stream = self._provider.complete_stream(
                self._prompt,
                timeout=self._timeout,
                on_reasoning=self._on_reasoning,
                on_warning=self.warning.emit,
            )
            for chunk in stream:
                if self._cancel_requested:
                    self.cancelled.emit()
                    return
                chunks.append(chunk)
                self.chunk.emit(chunk)
        except _StreamCancelled:
            self.cancelled.emit()
        except ProviderError as exc:
            if self._cancel_requested:
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))
        except Exception as exc:  # GUI 不应因意外 Provider 异常崩溃
            if self._cancel_requested:
                self.cancelled.emit()
            else:
                self.failed.emit(f"意外错误: {exc}")
        else:
            if self._cancel_requested:
                self.cancelled.emit()
            else:
                self.succeeded.emit("".join(chunks))
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()


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


class ParallelFixWorker(QThread):
    """后台运行并行修复编排（``parallel.run_parallel``），事件经队列连接投递到 GUI 线程。"""

    event = Signal(int, str, str, str)  # index, status, detail, chunk
    completed = Signal()

    def __init__(self, tasks, provider, api_config, text, cancel_event, parent=None):
        super().__init__(parent)
        self._tasks = list(tasks)
        self._provider = provider
        self._api_config = api_config
        self._text = text
        self._cancel_event = cancel_event
        self.error = ""

    def run(self) -> None:
        try:
            parallel.run_parallel(
                self._tasks,
                self._provider,
                text=self._text,
                timeout=self._api_config.timeout,
                on_event=self._on_event,
                max_concurrency=self._api_config.max_concurrency,
                cancel_event=self._cancel_event,
            )
        except KeyboardInterrupt:
            pass
        except Exception as exc:  # 编排异常不应让 GUI 崩溃
            self.error = str(exc)
        finally:
            self.completed.emit()

    def _on_event(self, event) -> None:
        self.event.emit(event.index, event.status, event.detail, event.chunk)


class TodoFixDialog(QDialog):
    """多选并行 API 修复：勾选条目 → 并发获取建议 → 聚合 diff → 一次应用。

    变更只在内存中累积，``accept`` 后由主窗口写回编辑器（不自动落盘，决策 7）。
    """

    MAX_RETRY_ROUNDS = 3

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
        self.setWindowTitle("API 修复 TODO（多选并行；建议需人工复核）")
        self.resize(1240, 820)
        self._source_text = source_text
        self._api_config = api_config
        self._provider_factory = provider_factory
        self._dark = dark
        self._markers = fixer.scan_todo_markers(output_text, report)
        self._text = output_text
        self._tasks = parallel.plan_tasks(
            self._markers,
            source_text,
            "源脚本",
            output_text,
            api_config.context_lines,
        )
        self._selected: list = []
        self._attempted: list = []
        self._merged = ""
        self._applied = 0
        self._rounds = 0
        self._running = False
        self._collected = False
        self._closed = False
        self._worker: ParallelFixWorker | None = None
        self._workers: list = []  # 保活：已结束的线程对象不被提前 GC
        self._stream_started: set = set()
        self._cancel_event = threading.Event()
        self._build()
        self._sync_selection()

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
        left_layout.addWidget(QLabel("待处理标记（勾选要并行修复的条目）"))
        self.marker_list = QListWidget()
        for index, marker in enumerate(self._markers):
            item = QListWidgetItem(self._marker_label(index, marker))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.marker_list.addItem(item)
        self.marker_list.itemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.marker_list, 1)
        select_row = QHBoxLayout()
        self.select_all_button = QPushButton("全选")
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.select_none_button = QPushButton("全不选")
        self.select_none_button.clicked.connect(lambda: self._set_all_checked(False))
        select_row.addWidget(self.select_all_button)
        select_row.addWidget(self.select_none_button)
        left_layout.addLayout(select_row)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("将发送的条目（原文，可复核）"))
        self.payload_view = QPlainTextEdit()
        self.payload_view.setReadOnly(True)
        self.payload_view.setMaximumHeight(150)
        right_layout.addWidget(self.payload_view)
        right_layout.addWidget(QLabel("聚合状态（每条一行，实时刷新）"))
        self.status_list = QListWidget()
        right_layout.addWidget(self.status_list)
        right_layout.addWidget(QLabel("模型输出（流式，按 #序号 归属）"))
        self.stream_view = QPlainTextEdit()
        self.stream_view.setReadOnly(True)
        self.stream_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.stream_view.setPlaceholderText("开始后，模型正文将实时显示在这里（思维链仅显示段数）")
        stream_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        if stream_font.pointSize() < 10:
            stream_font.setPointSize(10)
        self.stream_view.setFont(stream_font)
        self.stream_view.setMinimumHeight(80)
        self.stream_view.setMaximumHeight(180)
        right_layout.addWidget(self.stream_view)
        right_layout.addWidget(QLabel("修复建议差异（当前 → 聚合建议）"))
        self.diff_view = QTextBrowser()
        self.diff_view.setOpenExternalLinks(False)
        right_layout.addWidget(self.diff_view, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 900])
        layout.addWidget(splitter, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        hint = QLabel("API 建议仍需人工复核，不保证语义正确；保存文件仍由主界面完成。")
        hint.setStyleSheet("color: palette(mid);")
        buttons.addWidget(hint, 1)
        self.send_button = QPushButton("开始并行修复")
        self.send_button.clicked.connect(self._start_run)
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._request_stop)
        self.retry_button = QPushButton("重试失败项")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(self._retry_failed)
        self.apply_button = QPushButton("应用全部修改")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_all)
        for button in (
            self.send_button,
            self.stop_button,
            self.retry_button,
            self.apply_button,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        footer = QHBoxLayout()
        footer.addStretch(1)
        discard_button = QPushButton("放弃本次修复")
        discard_button.clicked.connect(self.reject)
        footer.addWidget(discard_button)
        layout.addLayout(footer)

    def closeEvent(self, event) -> None:
        self._closed = True
        self._cancel_event.set()
        if self._worker is not None:
            self._worker.wait(2000)
        event.accept()
        self.accept()

    # ------------------------------------------------------------------
    # 选择与展示
    # ------------------------------------------------------------------
    def _marker_label(self, index: int, marker: fixer.TodoMarker) -> str:
        text = marker.marker_text if len(marker.marker_text) <= 72 else marker.marker_text[:72] + "…"
        return f"{index + 1}. 第 {marker.out_line} 行: {text}"

    def _set_all_checked(self, checked: bool) -> None:
        if self._running or self._collected:
            return
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.marker_list.count()):
            self.marker_list.item(row).setCheckState(state)

    def _checked_tasks(self) -> list:
        return [
            task
            for row, task in enumerate(self._tasks)
            if self.marker_list.item(row) is not None
            and self.marker_list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def _task_by_index(self, index: int):
        for task in self._tasks:
            if task.index == index:
                return task
        return None

    def _on_selection_changed(self, _item) -> None:
        self._sync_selection()

    def _sync_selection(self) -> None:
        self._selected = self._checked_tasks()
        self._refresh_payload()
        self._refresh_status_rows()
        if not self._running and not self._collected:
            self.send_button.setEnabled(bool(self._selected))

    def _refresh_payload(self) -> None:
        lines = [f"将发送 {len(self._selected)} 条到 {self._api_config.base_url}"]
        for task in self._selected:
            lines.append(f"#{task.index} 第 {task.out_line} 行: {task.marker.marker_text}")
        if self._selected:
            lines.append("（内容将离开本机，可能被服务提供方记录；prompt 不含 API key）")
        self.payload_view.setPlainText("\n".join(lines))

    def _refresh_status_rows(self) -> None:
        selected = {task.index for task in self._selected}
        self.status_list.clear()
        for task in self._tasks:
            if task.index in selected:
                self.status_list.addItem(self._row_text(task))
            else:
                self.status_list.addItem(
                    f"#{task.index} 第{task.out_line}行 {parallel.STATUS_SKIPPED}：未选择"
                )

    def _update_row(self, index: int, text: str) -> None:
        row = index - 1
        if 0 <= row < self.status_list.count():
            self.status_list.item(row).setText(text)

    def _append_stream(self, text: str) -> None:
        cursor = self.stream_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.stream_view.setTextCursor(cursor)
        self.stream_view.insertPlainText(redact(text, self._api_config.api_key))
        self.stream_view.ensureCursorVisible()

    def _row_text(self, task) -> str:
        return redact(
            parallel.format_status_line(task), self._api_config.api_key
        )

    def _row_text_from_event(self, index: int, status: str, detail: str) -> str:
        """用事件自身的 detail 渲染行（思维链/限流等瞬时信息不写回 task.detail）。"""
        task = self._task_by_index(index)
        out_line = task.out_line if task is not None else 0
        line = f"#{index} 第{out_line}行 {status}"
        return redact(
            f"{line}：{detail}" if detail else line, self._api_config.api_key
        )

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------
    def _start_run(self) -> None:
        if self._running:
            return
        selected = self._checked_tasks()
        if not selected:
            self.status_label.setText("未选择任何条目。")
            return
        self._launch(selected)

    def _launch(self, tasks: list) -> None:
        try:
            provider = self._provider_factory(self._api_config)
        except ProviderError as exc:
            self.status_label.setText(f"API 配置错误：{exc}")
            return
        for task in tasks:
            if not any(task is item for item in self._attempted):
                self._attempted.append(task)
        self._running = True
        self._cancel_event = threading.Event()
        self.send_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.select_all_button.setEnabled(False)
        self.select_none_button.setEnabled(False)
        self.marker_list.setEnabled(False)
        self.status_label.setText(
            f"并行请求中（并发 {self._api_config.max_concurrency}；"
            f"端点 {self._api_config.base_url}）…"
        )
        worker = ParallelFixWorker(
            tasks, provider, self._api_config, self._text, self._cancel_event
        )
        worker.event.connect(self._on_worker_event, Qt.ConnectionType.QueuedConnection)
        worker.completed.connect(
            self._on_worker_completed, Qt.ConnectionType.QueuedConnection
        )
        self._worker = worker
        self._workers.append(worker)
        worker.start()

    def _on_worker_event(self, index: int, status: str, detail: str, chunk: str) -> None:
        if self._closed:
            return
        if chunk:
            if index not in self._stream_started:
                self._stream_started.add(index)
                self._append_stream(f"#{index}: ")
            self._append_stream(chunk)
            return
        if status == parallel.STATUS_RUNNING and detail.startswith("警告："):
            self._append_stream(f"#{index} [警告] {detail[len('警告：'):]}\n")
            return
        if status == parallel.STATUS_RUNNING and detail.startswith("限流"):
            self._append_stream(f"#{index} [{detail}]\n")
            return
        self._update_row(index, self._row_text_from_event(index, status, detail))
        if status != parallel.STATUS_RUNNING and index in self._stream_started:
            self._append_stream("\n")
            self._stream_started.discard(index)

    def _on_worker_completed(self) -> None:
        worker = self._worker
        self._worker = None
        self._running = False
        self.stop_button.setEnabled(False)
        if self._closed:
            return
        if worker is not None and worker.error:
            self.status_label.setText(
                "编排异常（已中止本条会话）："
                + redact(worker.error, self._api_config.api_key)
            )
        merged, _dropped = parallel.merge_replacements(self._text, self._attempted)
        self._merged = merged
        self._collected = True
        for task in self._attempted:
            self._update_row(task.index, self._row_text(task))
        if merged != self._text:
            self.diff_view.setHtml(
                build_diff_html(self._text, merged, "当前脚本", "修复建议", self._dark)
            )
            self.apply_button.setEnabled(True)
        done = [t for t in self._attempted if t.status == parallel.STATUS_DONE]
        skipped = [t for t in self._attempted if t.status == parallel.STATUS_SKIPPED]
        failed = [t for t in self._attempted if t.status == parallel.STATUS_FAILED]
        self.retry_button.setEnabled(
            bool(failed) and self._rounds < self.MAX_RETRY_ROUNDS
        )
        parts = [
            f"收集完成：可修复 {len(done)} / 跳过 {len(skipped)} / 失败 {len(failed)}"
        ]
        if failed and self.retry_button.isEnabled():
            parts.append("可点击“重试失败项”")
        if self.apply_button.isEnabled():
            parts.append("核对聚合差异后点击“应用全部修改”")
        elif not failed:
            parts.append("没有可用修改（保留 TODO，需人工处理）")
        self.status_label.setText("；".join(parts))

    def _retry_failed(self) -> None:
        if self._running:
            return
        failed = [t for t in self._attempted if t.status == parallel.STATUS_FAILED]
        if not failed or self._rounds >= self.MAX_RETRY_ROUNDS:
            return
        self._rounds += 1
        for task in failed:
            task.status = parallel.STATUS_PENDING
            task.replacement = ""
            task.detail = ""
            task.retries = 0
            self._update_row(task.index, self._row_text(task))
        self.status_label.setText(f"重试 {len(failed)} 条（第 {self._rounds} 轮）…")
        self._launch(failed)

    def _request_stop(self) -> None:
        self._cancel_event.set()
        self.status_label.setText("正在停止…（需等待当前请求返回，最长一个空闲超时）")
        self.stop_button.setEnabled(False)

    def _apply_all(self) -> None:
        if not self._merged or self._merged == self._text:
            return
        self._text = self._merged
        self._applied = sum(
            1 for task in self._attempted if task.status == parallel.STATUS_DONE
        )
        self.accept()


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
