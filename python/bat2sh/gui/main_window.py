"""主窗口：文件列表 / 源预览 / 转换结果三栏布局。"""

from __future__ import annotations

import os
import shutil
import signal
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from PySide6.QtCore import QProcess, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStyle,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_DISPLAY_NAME
from ..core.encoding import SUPPORTED_ENCODINGS, read_source
from ..core.engine import (
    ConversionResult,
    convert_text,
    detect_kind,
    output_path_for,
    write_output,
)
from ..core.recent import load_recent, save_recent, update_recent_list
from ..core.settings import ConvertSettings, save_settings
from ..core.types import ConvertReport, SourceKind, report_blocks
from .dialogs import AboutDialog, DiffDialog, ReportDialog, RunConfirmDialog, SettingsDialog
from .editor import CodeEditor
from .highlighter import highlighter_for
from .theme import apply_theme, system_is_dark

SCRIPT_SUFFIXES = (".bat", ".cmd", ".ps1", ".psm1")
RUN_TERMINATE_GRACE_MS = 2_000
SETSID_PATH = shutil.which("setsid")


def collect_script_paths(
    paths: list[Path],
    suffixes: tuple[str, ...] = SCRIPT_SUFFIXES,
    limit: int = 500,
) -> list[Path]:
    """收集可转换脚本路径；每个目录最多取 limit 个（按路径排序）。"""
    collected: list[Path] = []
    for path in paths:
        if path.is_dir():
            candidates: list[Path] = []
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in suffixes:
                    candidates.append(child)
                if len(candidates) >= limit:
                    break
            collected.extend(candidates)
        elif path.is_file() and path.suffix.lower() in suffixes:
            collected.append(path)
    return collected


def filter_new_paths(existing: set[Path], candidates: list[Path]) -> list[Path]:
    """按 ``resolve()`` 去重，返回不在 existing 中的新路径；不修改传入集合。"""
    seen = set(existing)
    fresh: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        fresh.append(candidate)
    return fresh


def needs_todo_confirmation(report: ConvertReport | None) -> bool:
    return bool(report is not None and (report.todo_count or report.error_count))


def error_display_lines(report: ConvertReport) -> list[str]:
    return [diagnostic.format() for diagnostic in report.errors]


def todo_display_lines(report: ConvertReport) -> list[str]:
    return [diagnostic.format() for diagnostic in report.todos]


def counts_text(report: ConvertReport | None) -> str:
    """状态栏计数文本；三色报告下错误/警告/TODO 分别计数。"""
    if report is None:
        return "错误 0 · 警告 0 · TODO 0 · 已转换 0/0"
    return (
        f"错误 {report.error_count} · 警告 {report.warning_count} · "
        f"TODO {report.todo_count} · 已转换 {report.converted_lines}/{report.total_lines}"
    )


@dataclass
class SourceFile:
    path: Path
    kind: SourceKind
    source_text: str = ""
    output_text: str = ""
    detected_encoding: str = ""
    encoding_override: str | None = None
    output_path: Path | None = None
    report: ConvertReport | None = None


def entry_to_result(entry: SourceFile, settings: ConvertSettings) -> ConversionResult:
    """把列表项与当前设置组装成写出所需的 ConversionResult。"""
    return ConversionResult(
        source_path=str(entry.path),
        output_path=str(entry.output_path or output_path_for(entry.path, settings)),
        kind=entry.kind,
        encoding=entry.detected_encoding or "utf-8",
        text=entry.output_text,
        report=entry.report or ConvertReport(),
    )


class MainWindow(QMainWindow):
    def __init__(self, settings: ConvertSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self.files: list[SourceFile] = []
        self.current: SourceFile | None = None
        self.recent_files: list[Path] = load_recent()
        self._loading = False
        self._source_highlighter = None
        self._output_highlighter = None
        self._run_process: QProcess | None = None
        self._run_timer: QTimer | None = None
        self._run_tmp_path: Path | None = None
        self._run_timeout_hit = False
        self._run_stop_requested = False
        self._run_timeout_ms = 0
        self._run_active_name = ""
        app = QApplication.instance()
        self.dark = system_is_dark(app) if app is not None else False

        self._build_actions()
        self._build_toolbar()
        self._rebuild_recent_menu()
        self._build_ui()
        self._build_statusbar()
        self._rebuild_highlighters()

        self.resize(1500, 900)
        self.setAcceptDrops(True)
        self.setWindowTitle(APP_DISPLAY_NAME)
        self._update_actions()

    # ------------------------------------------------------------------
    # 构建界面
    # ------------------------------------------------------------------
    def _icon(self, theme_name: str, standard: QStyle.StandardPixmap) -> QIcon:
        return QIcon.fromTheme(theme_name, self.style().standardIcon(standard))

    def _make_action(
        self,
        text: str,
        icon: QIcon,
        shortcut: str | None,
        slot,
        tooltip: str = "",
    ) -> QAction:
        action = QAction(icon, text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        if tooltip:
            action.setToolTip(tooltip)
        action.setStatusTip(tooltip or text)
        return action

    def _build_actions(self) -> None:
        std = QStyle.StandardPixmap
        self.action_open = self._make_action(
            "打开文件", self._icon("document-open", std.SP_DialogOpenButton),
            "Ctrl+O", self.open_files, "打开 .bat/.cmd/.ps1 文件",
        )
        self.action_open_dir = self._make_action(
            "打开文件夹", self._icon("folder-open", std.SP_DirOpenIcon),
            "Ctrl+Shift+O", self.open_folder, "添加文件夹中的全部脚本",
        )
        self.action_convert = self._make_action(
            "转换", self._icon("system-run", std.SP_MediaPlay),
            "Ctrl+Return", self.convert_current, "转换当前文件（Ctrl+Enter）",
        )
        self.action_save = self._make_action(
            "保存", self._icon("document-save", std.SP_DialogSaveButton),
            "Ctrl+S", self.save_current, "保存转换结果（Ctrl+S）",
        )
        self.action_batch = self._make_action(
            "批量转换", self._icon("run-build", std.SP_FileDialogDetailedView),
            "Ctrl+Shift+R", self.batch_convert, "转换并保存列表中的全部文件",
        )
        self.action_run = self._make_action(
            "转换并运行", self._icon("media-playback-start", std.SP_MediaPlay),
            "Ctrl+Shift+Return", self.run_current, "转换并在内嵌面板中运行（超时可在设置中调整）",
        )
        self.action_diff = self._make_action(
            "预览差异", self._icon("document-preview", std.SP_FileDialogContentsView),
            "Ctrl+D", self.open_diff, "对比源文件与转换结果",
        )
        self.action_report = self._make_action(
            "转换报告", self._icon("document-properties", std.SP_FileDialogInfoView),
            "Ctrl+R", self.open_report, "查看当前文件的转换报告",
        )
        self.action_theme = self._make_action(
            "切换主题", self._icon("weather-clear-night", std.SP_BrowserReload),
            "Ctrl+T", self.toggle_theme, "在跟随系统 / 浅色 / 深色之间切换",
        )
        self.action_settings = self._make_action(
            "设置", self._icon("configure", std.SP_ComputerIcon),
            "Ctrl+,", self.open_settings, "转换选项",
        )
        self.action_about = self._make_action(
            "关于", self._icon("help-about", std.SP_MessageBoxInformation),
            None, self.show_about, "关于 bat2sh",
        )
        self.action_quit = self._make_action(
            "退出", self._icon("application-exit", std.SP_DialogCloseButton),
            "Ctrl+Q", self.close, "退出",
        )
        self.recent_menu = QMenu(self)
        self.action_recent = QAction(
            self._icon("document-open-recent", std.SP_FileDialogDetailedView),
            "最近打开",
            self,
        )
        self.action_recent.setMenu(self.recent_menu)
        self.action_recent.setStatusTip("重新打开最近使用过的文件")
        self.action_remove = QAction("移除所选", self)
        self.action_remove.triggered.connect(self.remove_selected)
        self.action_clear = QAction("清空列表", self)
        self.action_clear.triggered.connect(self.clear_files)
        self.action_convert_save = QAction("转换并保存", self)
        self.action_convert_save.triggered.connect(self.convert_and_save)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏", self)
        toolbar.setObjectName("main-toolbar")
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for action in (
            self.action_open,
            self.action_open_dir,
            self.action_recent,
            None,
            self.action_convert,
            self.action_save,
            self.action_batch,
            self.action_run,
            None,
            self.action_diff,
            self.action_report,
            None,
            self.action_theme,
            self.action_settings,
            self.action_about,
        ):
            if action is None:
                toolbar.addSeparator()
            else:
                toolbar.addAction(action)
        recent_button = toolbar.widgetForAction(self.action_recent)
        if isinstance(recent_button, QToolButton):
            recent_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_source_panel())
        splitter.addWidget(self._build_output_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([280, 620, 620])
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._build_run_panel())
        self.setCentralWidget(container)

    def _build_run_panel(self) -> QWidget:
        self.run_panel = QGroupBox("运行输出")
        layout = QVBoxLayout(self.run_panel)
        header = QHBoxLayout()
        self.run_status_label = QLabel("尚未运行")
        self.run_status_label.setStyleSheet("color: palette(mid);")
        self.run_stop_button = QPushButton("停止")
        self.run_stop_button.setToolTip("终止正在运行的脚本及其子进程")
        self.run_stop_button.setEnabled(False)
        self.run_stop_button.clicked.connect(self._stop_run)
        self.run_toggle_button = QToolButton()
        self.run_toggle_button.setText("展开")
        self.run_toggle_button.setCheckable(True)
        self.run_toggle_button.toggled.connect(self._toggle_run_panel)
        header.addWidget(self.run_status_label, 1)
        header.addWidget(self.run_stop_button)
        header.addWidget(self.run_toggle_button)
        layout.addLayout(header)
        self.run_input_row = QWidget()
        input_row = QHBoxLayout(self.run_input_row)
        input_row.setContentsMargins(0, 0, 0, 0)
        self.run_input = QLineEdit()
        self.run_input.setPlaceholderText("向脚本发送输入（运行中可用，回车发送）")
        self.run_input.setEnabled(False)
        self.run_input.returnPressed.connect(self._send_run_input)
        self.run_send_button = QPushButton("发送")
        self.run_send_button.setEnabled(False)
        self.run_send_button.clicked.connect(self._send_run_input)
        input_row.addWidget(self.run_input, 1)
        input_row.addWidget(self.run_send_button)
        layout.addWidget(self.run_input_row)
        self.run_output = QPlainTextEdit()
        self.run_output.setReadOnly(True)
        self.run_output.setPlaceholderText("运行输出将显示在这里")
        self.run_output.setMinimumHeight(120)
        self.run_output.setMaximumHeight(300)
        self.run_output.hide()
        self.run_input_row.hide()
        layout.addWidget(self.run_output)
        return self.run_panel

    def _toggle_run_panel(self, expanded: bool) -> None:
        self.run_output.setVisible(expanded)
        self.run_input_row.setVisible(expanded)
        self.run_toggle_button.setText("折叠" if expanded else "展开")

    def _build_left_panel(self) -> QWidget:
        box = QGroupBox("待转换文件")
        layout = QVBoxLayout(box)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._show_list_menu)
        self.file_list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.file_list)
        buttons = QHBoxLayout()
        remove_button = QPushButton("移除所选")
        remove_button.clicked.connect(self.remove_selected)
        clear_button = QPushButton("清空")
        clear_button.clicked.connect(self.clear_files)
        buttons.addWidget(remove_button)
        buttons.addWidget(clear_button)
        layout.addLayout(buttons)
        hint = QLabel("可将 .bat/.cmd/.ps1 文件或文件夹拖拽到此窗口")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)
        return box

    def _build_source_panel(self) -> QWidget:
        box = QGroupBox("源文件预览（只读）")
        layout = QVBoxLayout(box)
        header = QHBoxLayout()
        self.source_path_label = QLabel("未选择文件")
        self.source_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.kind_label = QLabel("")
        self.kind_label.setStyleSheet("color: palette(mid);")
        self.encoding_combo = QComboBox()
        self.encoding_combo.setToolTip("输入编码：可手动覆盖自动检测结果")
        self.encoding_combo.addItem("自动检测", None)
        for name in SUPPORTED_ENCODINGS:
            self.encoding_combo.addItem(name, name)
        self.encoding_combo.currentIndexChanged.connect(self._on_encoding_changed)
        header.addWidget(self.source_path_label, 1)
        header.addWidget(self.kind_label)
        header.addWidget(self.encoding_combo)
        layout.addLayout(header)
        self.source_editor = CodeEditor()
        self.source_editor.setReadOnly(True)
        layout.addWidget(self.source_editor)
        return box

    def _build_output_panel(self) -> QWidget:
        box = QGroupBox("转换结果（可编辑）")
        layout = QVBoxLayout(box)
        header = QHBoxLayout()
        self.output_path_label = QLabel("转换后在此预览")
        self.output_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        diff_button = QPushButton("预览差异")
        diff_button.setIcon(self._icon("document-preview", self.style().StandardPixmap.SP_FileDialogContentsView))
        diff_button.clicked.connect(self.open_diff)
        report_button = QPushButton("报告")
        report_button.setIcon(self._icon("document-properties", self.style().StandardPixmap.SP_FileDialogInfoView))
        report_button.clicked.connect(self.open_report)
        header.addWidget(self.output_path_label, 1)
        header.addWidget(diff_button)
        header.addWidget(report_button)
        layout.addLayout(header)
        self.output_editor = CodeEditor()
        layout.addWidget(self.output_editor)
        return box

    def _build_statusbar(self) -> None:
        status = self.statusBar()
        self.status_label = QLabel("就绪：请打开 .bat/.cmd/.ps1 文件")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        self.counts_label = QLabel("警告 0 · 错误 0 · 已转换 0/0")
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(self.progress)
        status.addPermanentWidget(self.counts_label)

    # ------------------------------------------------------------------
    # 高亮
    # ------------------------------------------------------------------
    def _rebuild_highlighters(self) -> None:
        if self._source_highlighter is not None:
            self._source_highlighter.setDocument(None)
        if self._output_highlighter is not None:
            self._output_highlighter.setDocument(None)
        kind = self.current.kind.value if self.current else "sh"
        self._source_highlighter = highlighter_for(kind, self.source_editor.document(), self.dark)
        self._output_highlighter = highlighter_for("sh", self.output_editor.document(), self.dark)

    # ------------------------------------------------------------------
    # 文件列表
    # ------------------------------------------------------------------
    def add_paths(self, paths: list[Path], select_last: bool = True) -> int:
        existing = {entry.path.resolve() for entry in self.files}
        new_paths = filter_new_paths(existing, collect_script_paths(paths))
        for candidate in new_paths:
            self.files.append(SourceFile(path=candidate, kind=detect_kind(candidate)))
        added = len(new_paths)
        if added:
            self.recent_files = update_recent_list(self.recent_files, new_paths)
            save_recent(self.recent_files)
            self._rebuild_recent_menu()
            self._refresh_list()
            if select_last:
                self.file_list.setCurrentRow(self.file_list.count() - 1)
            self.status_label.setText(f"已添加 {added} 个文件")
        elif paths:
            self.status_label.setText("没有可添加的 .bat/.cmd/.ps1 文件")
        self._update_actions()
        return added

    def open_paths(self, paths: list[Path]) -> None:
        self.add_paths(paths)

    def _refresh_list(self) -> None:
        self.file_list.blockSignals(True)
        current_row = self.file_list.currentRow()
        self.file_list.clear()
        for entry in self.files:
            item = QListWidgetItem(entry.path.name)
            item.setToolTip(str(entry.path))
            item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
            icon_name = "text-x-script" if entry.kind is not SourceKind.UNKNOWN else "text-x-generic"
            item.setIcon(QIcon.fromTheme(icon_name))
            self.file_list.addItem(item)
        if 0 <= current_row < self.file_list.count():
            self.file_list.setCurrentRow(current_row)
        self.file_list.blockSignals(False)

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.file_list.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self.files):
                entry = self.files.pop(row)
                if entry is self.current:
                    self.current = None
        self._refresh_list()
        if self.files and self.current is None:
            self.file_list.setCurrentRow(min(rows[-1], len(self.files) - 1))
        elif not self.files:
            self._clear_editors()
        self._update_actions()

    def clear_files(self) -> None:
        self.files.clear()
        self.current = None
        self._refresh_list()
        self._clear_editors()
        self._update_actions()

    def _clear_editors(self) -> None:
        self._loading = True
        self.source_editor.clear()
        self.output_editor.clear()
        self._loading = False
        self.source_path_label.setText("未选择文件")
        self.kind_label.setText("")
        self.output_path_label.setText("转换后在此预览")
        self._update_counts(None)

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.clear()
        if not self.recent_files:
            empty = self.recent_menu.addAction("（无）")
            empty.setEnabled(False)
            return
        for path in self.recent_files:
            action = self.recent_menu.addAction(str(path))
            action.setStatusTip("重新打开 " + str(path))
            action.triggered.connect(lambda checked=False, p=path: self.open_paths([p]))

    def _show_list_menu(self, position) -> None:
        menu = QMenu(self)
        menu.addAction(self.action_convert)
        menu.addAction(self.action_convert_save)
        menu.addAction(self.action_save)
        menu.addSeparator()
        menu.addAction(self.action_remove)
        menu.addAction(self.action_clear)
        reveal = menu.addAction("在文件管理器中显示")
        reveal.triggered.connect(self._reveal_current)
        menu.exec(self.file_list.mapToGlobal(position))

    def _reveal_current(self) -> None:
        if self.current:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current.path.parent)))

    def _on_row_changed(self, row: int) -> None:
        if self._loading or row < 0 or row >= len(self.files):
            return
        entry = self.files[row]
        if entry is self.current:
            return
        self.current = entry
        if not entry.source_text:
            if not self._read_entry(entry):
                return
        self._loading = True
        self.source_editor.setPlainText(entry.source_text)
        self.encoding_combo.setItemText(0, f"自动检测（{entry.detected_encoding}）")
        self.encoding_combo.setCurrentIndex(0)
        self._loading = False
        self.source_path_label.setText(str(entry.path))
        self.kind_label.setText(f"[{entry.kind.display_name}]")
        self._rebuild_highlighters()
        self.source_editor.moveCursor(self.source_editor.textCursor().MoveOperation.Start)
        self.convert_current()
        self._update_actions()

    def _read_entry(self, entry: SourceFile) -> bool:
        try:
            decoded = read_source(entry.path, entry.encoding_override)
        except OSError as exc:
            QMessageBox.critical(self, "读取失败", str(exc))
            self.status_label.setText(f"读取失败: {entry.path}")
            return False
        entry.source_text = decoded.text
        entry.detected_encoding = decoded.encoding
        return True

    def _on_encoding_changed(self, index: int) -> None:
        if self._loading or self.current is None:
            return
        override = self.encoding_combo.itemData(index)
        entry = self.current
        entry.encoding_override = override
        if self._read_entry(entry):
            self._loading = True
            self.source_editor.setPlainText(entry.source_text)
            self._loading = False
            self.convert_current()

    # ------------------------------------------------------------------
    # 转换 / 保存
    # ------------------------------------------------------------------
    def convert_current(self) -> None:
        entry = self.current
        if entry is None:
            return
        try:
            text, report = convert_text(entry.source_text, entry.kind, self.settings, entry.path.name)
        except Exception as exc:
            QMessageBox.critical(self, "转换失败", str(exc))
            return
        entry.output_text = text
        entry.report = report
        entry.output_path = output_path_for(entry.path, self.settings)
        self._loading = True
        self.output_editor.setPlainText(text)
        self._loading = False
        self.output_path_label.setText(str(entry.output_path))
        self._update_counts(report)
        self.status_label.setText(f"已转换 {entry.path.name}")
        self._update_actions()

    def save_current(self) -> None:
        entry = self.current
        if entry is None:
            return
        entry.output_text = self.output_editor.toPlainText()
        if not entry.output_text.strip():
            QMessageBox.warning(self, "保存", "没有可保存的转换结果，请先执行转换。")
            return
        entry.output_path = entry.output_path or output_path_for(entry.path, self.settings)
        result = entry_to_result(entry, self.settings)
        write_output(result, self.settings)
        if result.error:
            QMessageBox.critical(self, "保存失败", result.error)
            return
        message = f"已保存: {result.output_path}"
        if result.backup_path:
            message += f"（原文件已备份为 {result.backup_path}）"
        self.status_label.setText(message)

    def convert_and_save(self) -> None:
        self.convert_current()
        self.save_current()

    def batch_convert(self) -> None:
        if not self.files:
            QMessageBox.information(self, "批量转换", "文件列表为空。")
            return
        self.progress.show()
        self.progress.setRange(0, len(self.files))
        self.progress.setValue(0)
        saved = 0
        errors: list[str] = []
        total_errors = 0
        total_warnings = 0
        total_todos = 0
        for index, entry in enumerate(self.files, start=1):
            try:
                if not entry.source_text and not self._read_entry(entry):
                    errors.append(f"{entry.path}: 读取失败")
                else:
                    text, report = convert_text(entry.source_text, entry.kind, self.settings, entry.path.name)
                    entry.output_text = text
                    entry.report = report
                    entry.output_path = output_path_for(entry.path, self.settings)
                    result = entry_to_result(entry, self.settings)
                    write_output(result, self.settings)
                    total_errors += report.error_count
                    total_warnings += report.warning_count
                    total_todos += report.todo_count
                    if result.error:
                        errors.append(f"{entry.path}: {result.error}")
                    else:
                        saved += 1
            except Exception as exc:
                errors.append(f"{entry.path}: {exc}")
            self.progress.setValue(index)
            QApplication.processEvents()
        self.progress.hide()
        if self.current is not None:
            self._loading = True
            self.output_editor.setPlainText(self.current.output_text)
            self._loading = False
            self._update_counts(self.current.report)
        lines = [
            f"共处理文件: {len(self.files)}",
            f"成功写出: {saved}",
            f"失败: {len(errors)}",
            f"错误总数: {total_errors}",
            f"警告总数: {total_warnings}",
            f"无法自动转换（TODO）总数: {total_todos}",
        ]
        if errors:
            lines.append("")
            lines.append("── 错误 ─────────────────────────────────")
            lines.extend("  " + error for error in errors)
        ReportDialog("批量转换报告", [(line, "normal") for line in lines], self.dark, self).exec()
        self.status_label.setText(f"批量转换完成：成功 {saved} 个，失败 {len(errors)} 个")

    # ------------------------------------------------------------------
    # 转换并运行
    # ------------------------------------------------------------------
    def run_current(self) -> None:
        entry = self.current
        if entry is None:
            QMessageBox.information(self, "转换并运行", "请先打开并选择一个文件。")
            return
        if self._run_is_active():
            QMessageBox.information(self, "转换并运行", "已有脚本正在运行，请等待其结束。")
            return
        if not entry.output_text or self.output_editor.toPlainText() != entry.output_text:
            self.convert_current()
        if not entry.output_text.strip():
            QMessageBox.warning(self, "转换并运行", "转换结果为空，无法执行。")
            return
        if needs_todo_confirmation(entry.report):
            body = "\n".join(
                error_display_lines(entry.report) + todo_display_lines(entry.report)
            )
            manual_count = entry.report.error_count + entry.report.todo_count
            todo_dialog = RunConfirmDialog(
                "存在无法自动转换的语句",
                f"以下 {manual_count} 处需要人工检查，执行结果可能不正确：",
                body,
                "仍要执行",
                self,
            )
            if todo_dialog.exec() != QDialog.DialogCode.Accepted:
                self.status_label.setText("已取消执行")
                return
        preview_dialog = RunConfirmDialog(
            "执行确认",
            f"将执行以下脚本（工作目录：{entry.path.parent}）：",
            entry.output_text,
            "执行",
            self,
        )
        if preview_dialog.exec() != QDialog.DialogCode.Accepted:
            self.status_label.setText("已取消执行")
            return
        self._start_run(entry)

    def _start_run(self, entry: SourceFile) -> None:
        try:
            with NamedTemporaryFile(
                "w", suffix=".sh", delete=False, encoding="utf-8"
            ) as handle:
                handle.write(entry.output_text)
        except OSError as exc:
            QMessageBox.critical(self, "执行失败", f"无法创建临时脚本: {exc}")
            return
        self._run_tmp_path = Path(handle.name)
        self._run_timeout_hit = False
        self._run_stop_requested = False
        self._run_timeout_ms = self._current_run_timeout_ms()
        self._run_active_name = entry.path.name
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.setWorkingDirectory(str(entry.path.parent))
        if SETSID_PATH:
            process.setProgram(SETSID_PATH)
            process.setArguments(["bash", str(self._run_tmp_path)])
        else:
            process.setProgram("bash")
            process.setArguments([str(self._run_tmp_path)])
        process.readyReadStandardOutput.connect(self._on_run_output)
        process.finished.connect(self._on_run_finished)
        process.errorOccurred.connect(self._on_run_process_error)
        self._run_process = process
        self._run_timer = QTimer(self)
        self._run_timer.setSingleShot(True)
        self._run_timer.timeout.connect(self._on_run_timeout)
        self.run_output.clear()
        self.run_toggle_button.setChecked(True)
        self.run_status_label.setText(f"运行中：{entry.path.name}")
        self.status_label.setText(f"正在运行 {entry.path.name} …")
        self._update_run_controls(True)
        self._run_timer.start(self._run_timeout_ms)
        process.start()

    def _current_run_timeout_ms(self) -> int:
        return max(1, int(self.settings.run_timeout * 1000))

    def _update_run_controls(self, running: bool) -> None:
        self.run_stop_button.setEnabled(running)
        self.run_input.setEnabled(running)
        self.run_send_button.setEnabled(running)

    def _on_run_output(self) -> None:
        process = self._run_process
        if process is None:
            return
        data = bytes(process.readAllStandardOutput())
        if not data:
            return
        self.run_output.moveCursor(QTextCursor.MoveOperation.End)
        self.run_output.insertPlainText(data.decode("utf-8", errors="replace"))
        self.run_output.ensureCursorVisible()

    def _on_run_finished(self, exit_code: int, exit_status) -> None:
        if self._run_timer is not None:
            self._run_timer.stop()
        self._on_run_output()
        if self._run_stop_requested:
            summary = "已停止（用户中断）"
        elif self._run_timeout_hit:
            summary = f"运行超时（{self._run_timeout_ms / 1000:g} 秒），已终止"
        elif exit_status == QProcess.ExitStatus.CrashExit:
            summary = f"进程被强制终止（退出码 {exit_code}）"
        else:
            summary = f"运行结束：退出码 {exit_code}"
        self.run_status_label.setText(summary)
        self.status_label.setText(summary)
        self.run_output.appendPlainText(f"[{summary}]")
        self._update_run_controls(False)
        self._cleanup_run_tmp()

    def _stop_run(self) -> None:
        """用户点击“停止”：先 SIGTERM 整个进程组，宽限后 SIGKILL 兜底。"""
        process = self._run_process
        if process is None or not self._run_is_active():
            return
        self._run_stop_requested = True
        self.run_status_label.setText("正在停止…")
        self._kill_process_group(process, signal.SIGTERM)
        QTimer.singleShot(RUN_TERMINATE_GRACE_MS, self._force_kill_run)

    def _force_kill_run(self) -> None:
        process = self._run_process
        if process is not None and self._run_is_active():
            self._kill_process_group(process, signal.SIGKILL)

    @staticmethod
    def _kill_process_group(process: QProcess, sig: int) -> None:
        """优先终止整个进程组（setsid 会话），失败时回退为只杀主进程。"""
        pid: int | None = None
        try:
            pid = process.processId()
        except Exception:
            pid = None
        if pid:
            try:
                pgid = os.getpgid(pid)
            except OSError:
                pgid = None
            if pgid and pgid == pid and pgid != os.getpgid(0):
                try:
                    os.killpg(pgid, sig)
                    return
                except OSError:
                    pass
        process.kill()

    def _send_run_input(self) -> None:
        process = self._run_process
        if process is None or not self._run_is_active():
            return
        text = self.run_input.text()
        self.run_input.clear()
        process.write((text + "\n").encode("utf-8"))
        current = self.run_output.toPlainText()
        separator = "" if not current or current.endswith("\n") else "\n"
        cursor = self.run_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(f"{separator}> {text}\n")

    def _on_run_timeout(self) -> None:
        process = self._run_process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            return
        self._run_timeout_hit = True
        self._kill_process_group(process, signal.SIGKILL)

    def _on_run_process_error(self, error) -> None:
        if error != QProcess.ProcessError.FailedToStart:
            return
        if self._run_timer is not None:
            self._run_timer.stop()
        summary = "启动失败：无法执行 bash"
        self.run_status_label.setText(summary)
        self.status_label.setText(summary)
        self.run_output.appendPlainText(f"[{summary}]")
        self._update_run_controls(False)
        self._cleanup_run_tmp()

    def _run_is_active(self) -> bool:
        process = self._run_process
        return process is not None and process.state() != QProcess.ProcessState.NotRunning

    def _cleanup_run_tmp(self) -> None:
        if self._run_tmp_path is not None:
            try:
                self._run_tmp_path.unlink()
            except OSError:
                pass
            self._run_tmp_path = None

    # ------------------------------------------------------------------
    # 对话框
    # ------------------------------------------------------------------
    def open_files(self) -> None:
        directory = self.settings.last_dir or str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "打开脚本文件",
            directory,
            "脚本文件 (*.bat *.cmd *.ps1 *.psm1);;所有文件 (*)",
        )
        if paths:
            self.settings.last_dir = str(Path(paths[0]).parent)
            self.add_paths([Path(p) for p in paths])

    def open_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "打开文件夹", self.settings.last_dir or str(Path.home())
        )
        if directory:
            self.settings.last_dir = directory
            self.add_paths([Path(directory)])

    def open_diff(self) -> None:
        entry = self.current
        if entry is None:
            QMessageBox.information(self, "预览差异", "请先选择并转换一个文件。")
            return
        output_text = self.output_editor.toPlainText()
        output_name = str(entry.output_path or "output.sh")
        DiffDialog(
            entry.source_text,
            output_text,
            entry.path.name,
            Path(output_name).name,
            self.dark,
            self,
        ).exec()

    def open_report(self) -> None:
        entry = self.current
        if entry is None or entry.report is None:
            QMessageBox.information(self, "转换报告", "尚无转换报告，请先转换文件。")
            return
        blocks = report_blocks(entry.report)
        if entry.report.error_count or entry.report.todo_count:
            blocks.append(("", "normal"))
            if entry.report.error_count:
                blocks.append(
                    ("提示：“错误”表示生成脚本存在必须人工处理的问题。", "error")
                )
            if entry.report.todo_count:
                blocks.append(
                    ("提示：输出脚本中以 # TODO 开头的行需要人工确认。", "normal")
                )
        else:
            blocks.append(("", "normal"))
            blocks.append(("所有语句均已自动转换。", "normal"))
        ReportDialog(f"转换报告 - {entry.path.name}", blocks, self.dark, self).exec()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        self.settings = dialog.result_settings()
        save_settings(self.settings)
        app = QApplication.instance()
        self.dark = apply_theme(app, self.settings.theme)
        self._rebuild_highlighters()
        if self.current is not None:
            self.convert_current()
        self.status_label.setText("设置已更新")

    def toggle_theme(self) -> None:
        order = ["system", "light", "dark"]
        try:
            index = order.index(self.settings.theme)
        except ValueError:
            index = 0
        self.settings.theme = order[(index + 1) % len(order)]
        save_settings(self.settings)
        app = QApplication.instance()
        self.dark = apply_theme(app, self.settings.theme)
        self._rebuild_highlighters()
        labels = {"system": "跟随系统", "light": "浅色", "dark": "深色"}
        self.status_label.setText(f"主题: {labels[self.settings.theme]}")

    def show_about(self) -> None:
        AboutDialog(self).exec()

    # ------------------------------------------------------------------
    # 拖拽与状态
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()

    def _update_counts(self, report: ConvertReport | None) -> None:
        self.counts_label.setText(counts_text(report))

    def _update_actions(self) -> None:
        has_current = self.current is not None
        for action in (
            self.action_convert,
            self.action_save,
            self.action_run,
            self.action_convert_save,
            self.action_diff,
            self.action_report,
        ):
            action.setEnabled(has_current)
        self.action_batch.setEnabled(bool(self.files))
        self.action_remove.setEnabled(self.file_list.count() > 0)
        self.action_clear.setEnabled(self.file_list.count() > 0)

    def closeEvent(self, event) -> None:
        if self._run_is_active():
            name = self._run_active_name or "脚本"
            reply = QMessageBox.question(
                self,
                "脚本运行中",
                f"{name} 仍在运行，是否终止并退出？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            if self._run_timer is not None:
                self._run_timer.stop()
            process = self._run_process
            if process is not None:
                self._kill_process_group(process, signal.SIGKILL)
            self._cleanup_run_tmp()
        save_settings(self.settings)
        super().closeEvent(event)
