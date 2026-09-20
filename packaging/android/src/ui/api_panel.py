"""API 修复界面：设置对话框 + 并行修复面板。

并行面板采用 Phase 1 §4.5 选定的**方案 B（可展开列表）**：
    聚合头（计数 + 进度条）
    ListView(ExpansionTile × N)      ← 固定高度、自身滚动
    [应用全部] [取消]

三处针对手机屏幕的实测优化（依据 docs/android-api-assessment.md §4.4.3 / §4.5.3）：
  1. **按需渲染**：折叠行只更新一行短字符串（状态 + 字节数）；
     流式正文只在**被展开的那一条**上写入控件，展开时一次性补齐。
     这让每轮 page.update() 要序列化的控件树小一个量级。
  2. **批量刷新**：工作线程只 queue.put，**绝不** page.update()；
     唯一调用 page.update() 的是 _drain()，跑在 page 的事件循环里，
     每轮把已到达的事件全部吃掉再刷新一次（实测批量比 ≈28:1）。
  3. **单条重试**：失败条目自带「重试」，一条失败不阻塞其它（错误隔离）。

本模块不导入 core —— 一律经 api_bridge 中转。
"""

from __future__ import annotations

import asyncio
import queue
import sys
import threading
from pathlib import Path

import flet as ft

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import api_bridge  # noqa: E402

MONO = "monospace"
_POLL_SECONDS = 0.02          # ≈50 fps 上限；实测足够且批量比高
_STREAM_BOX_HEIGHT = 110        # 展开一条（正文 110 + 重试行 + 标题）应能装进 _LIST_HEIGHT
_LIST_HEIGHT = 250

_COLOR = {
    "grey": ft.Colors.GREY_600,
    "blue": ft.Colors.BLUE_400,
    "green": ft.Colors.GREEN_600,
    "red": ft.Colors.RED_500,
    "orange": ft.Colors.ORANGE_600,
}


def _color(name: str):
    return _COLOR.get(name, ft.Colors.GREY_600)


# ====================================================================== 设置

def open_settings_dialog(page: ft.Page, cfg, on_saved) -> None:
    """API 设置对话框。key 用 password 字段，且**从不**写入日志。"""

    endpoint = ft.TextField(
        label="API 地址（base_url）", value=cfg.base_url, text_size=12,
        hint_text="https://api.example.com/v1 或 http://192.168.1.10:11434/v1",
        keyboard_type=ft.KeyboardType.URL, autocorrect=False)
    key = ft.TextField(
        label="API key（可留空 —— 本地端点常无鉴权）", value=cfg.api_key,
        text_size=12, password=True, can_reveal_password=True,
        autocorrect=False, enable_suggestions=False)
    model = ft.TextField(
        label="模型名（model）", value=cfg.model, text_size=12,
        hint_text="如 gpt-4o-mini / qwen2.5-coder / llama3.1")
    timeout = ft.TextField(
        label="超时（秒）", value="%g" % cfg.timeout, text_size=12,
        keyboard_type=ft.KeyboardType.NUMBER)
    thinking = ft.Switch(label="启用思维链（enable_thinking）", value=cfg.enable_thinking,
                         label_text_style=ft.TextStyle(size=12))
    conc = ft.Dropdown(
        label="并行并发数（max_concurrency）", value=str(cfg.max_concurrency),
        options=[ft.DropdownOption(str(i)) for i in range(1, 17)], text_size=12)

    msg = ft.Text("", size=11, color=ft.Colors.RED_500)
    path_hint = ft.Text("配置文件：" + str(api_bridge.config_path()),
                        size=10, color=ft.Colors.GREY_600, selectable=True)

    def save(e) -> None:
        try:
            new_cfg = api_bridge.ApiConfig(
                provider=cfg.provider,
                base_url=endpoint.value or "",
                model=model.value or "",
                api_key=key.value or "",
                timeout=float(timeout.value or 30),
                max_retries=cfg.max_retries,
                context_lines=cfg.context_lines,
                enable_thinking=bool(thinking.value),
                max_concurrency=int(conc.value or 3),
            ).normalized()
        except (TypeError, ValueError) as exc:
            msg.value = "数值格式不对：" + str(exc)
            page.update()
            return
        missing = api_bridge.missing_requirements(new_cfg)
        if missing:
            msg.value = "还缺：" + "；".join(missing)
            page.update()
            return
        try:
            api_bridge.save_config(new_cfg)
        except OSError as exc:
            # 注意：异常文本可能含路径，但不含 key；仍然过一遍 redact 兜底
            msg.value = api_bridge.safe_error("保存失败：" + str(exc), new_cfg)
            page.update()
            return
        page.pop_dialog()
        on_saved(new_cfg)

    dialog = ft.AlertDialog(
        title=ft.Text("API 设置", size=16),
        content=ft.Container(
            content=ft.Column([endpoint, key, model, conc, timeout, thinking,
                               msg, path_hint],
                              spacing=10, scroll=ft.ScrollMode.AUTO, tight=True),
            width=340, height=430),
        actions=[
            ft.TextButton("取消", on_click=lambda e: page.pop_dialog()),
            ft.FilledButton("保存", on_click=save),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)


def open_privacy_dialog(page: ft.Page, n: int, endpoint: str, on_confirm) -> None:
    """隐私提示：每次发送前确认一次（不记忆 —— 任务书要求）。"""

    def confirm(e) -> None:
        page.pop_dialog()
        on_confirm()

    body = ft.Column([
        ft.Text("将把 %d 条 TODO 发送到：" % n, size=13),
        ft.Text(endpoint, size=12, font_family=MONO, selectable=True,
                color=ft.Colors.BLUE_400),
        ft.Text(api_bridge.prompts_preview([None] * n), size=11,
                color=ft.Colors.GREY_700),
        ft.Text("内容会离开本机。请确认该 endpoint 是你信任的服务。",
                size=11, color=ft.Colors.ORANGE_600),
    ], spacing=8, tight=True, scroll=ft.ScrollMode.AUTO)

    dialog = ft.AlertDialog(
        title=ft.Text("确认发送", size=16),
        content=ft.Container(content=body, width=330),
        actions=[
            ft.TextButton("取消", on_click=lambda e: page.pop_dialog()),
            ft.FilledButton("确认发送", on_click=confirm),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)


# ================================================================ 作业调度

class FixJob:
    """一次并行修复作业：工作线程 + 事件队列 + 事件循环内批量刷新。

    **这是纪律「禁止工作线程直接 page.update()」的落点。**
    工作线程只做 ``queue.put``；唯一碰控件与 ``page.update()`` 的地方在 ``_drain()``，
    它由 ``page.run_task`` 调度在 page 自己的事件循环里。
    """

    def __init__(self, page: ft.Page, on_events, on_finish) -> None:
        self.page = page
        self._on_events = on_events      # (list[FixEvent]) -> None（只改控件，不 update）
        self._on_finish = on_finish      # (result, error) -> None
        self._q: queue.Queue = queue.Queue()
        self._finished = threading.Event()
        self._running = False
        self._result = None
        self._error = ""
        self.cancel_event = threading.Event()

    @property
    def running(self) -> bool:
        return self._running

    def start(self, *, tasks, provider, text: str, timeout: float,
              syntax_checker, max_concurrency: int) -> bool:
        if self._running:
            return False
        self._running = True
        self._finished.clear()
        self.cancel_event = threading.Event()
        self._result = None
        self._error = ""
        q = self._q

        def worker() -> None:
            try:
                self._result = api_bridge.run_parallel(
                    tasks, provider,
                    text=text, timeout=timeout,
                    syntax_checker=syntax_checker,   # ← 必须注入（见 api_bridge）
                    on_event=q.put,                  # ← 只入队，不碰 UI
                    cancel_event=self.cancel_event,
                    max_concurrency=max_concurrency,
                )
            except BaseException as exc:  # noqa: BLE001 —— 编排异常也不能让 UI 崩
                self._error = api_bridge.safe_error(
                    "%s: %s" % (type(exc).__name__, exc))
            finally:
                self._finished.set()

        self.page.run_thread(worker)
        self.page.run_task(self._drain)
        return True

    def cancel(self) -> None:
        self.cancel_event.set()

    async def _drain(self) -> None:
        while True:
            batch = []
            while True:
                try:
                    batch.append(self._q.get_nowait())
                except queue.Empty:
                    break
            if batch:
                self._on_events(batch)
                try:
                    self.page.update()
                except Exception:  # noqa: BLE001 —— 页面已销毁时忽略
                    pass
            # 所有事件都在 _finished.set() 之前入队，故「已结束且队列空」= 全部消费完
            if self._finished.is_set() and self._q.empty():
                break
            await asyncio.sleep(_POLL_SECONDS)
        self._running = False
        self._on_finish(self._result, self._error)


# ================================================================ 并行面板

class ParallelPanel:
    """方案 B：可展开列表。整块由 app.py 插入报告区之下。"""

    def __init__(self, page: ft.Page, tx, on_apply) -> None:
        self.page = page
        self.tx = tx
        self.on_apply = on_apply           # (new_text: str, summary: str) -> None
        self.cfg = None
        self.text = ""
        self.tasks: list = []
        self.buffers: dict[int, str] = {}
        self.streams: dict[int, ft.Text] = {}
        self.subtitles: dict[int, ft.Text] = {}
        self.leads: dict[int, ft.Text] = {}
        self.retries: dict[int, ft.TextButton] = {}
        self.cards: dict[int, ft.Container] = {}
        self.tiles: dict[int, ft.ExpansionTile] = {}
        self.expanded: set[int] = set()
        # 只自动展开「第一条进入 running 的」，之后不再抢焦点（Phase 1 §4.5.3）
        self._auto_expanded = False
        self._job = FixJob(page, self._apply_events, self._finish)

        self.counts = ft.Text("", size=12, weight=ft.FontWeight.BOLD)
        self.bar = ft.ProgressBar(value=0, bar_height=6, border_radius=3)
        self.hint = ft.Text(
            "转换后若报告里有 TODO，点上面的「用 AI 并行修复」。",
            size=11, color=ft.Colors.GREY_600)
        self.rows = ft.ListView(height=_LIST_HEIGHT, spacing=4, padding=0)
        self.apply_btn = ft.FilledButton("应用全部", on_click=self._on_apply_all,
                                         disabled=True)
        self.cancel_btn = ft.OutlinedButton("取消", on_click=self._on_cancel,
                                            disabled=True)
        self.view = ft.Container(
            content=ft.Column([
                ft.Row([ft.Text("AI 并行修复", size=13, weight=ft.FontWeight.BOLD),
                        self.counts],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                self.bar,
                self.hint,
                self.rows,
                ft.Row([self.apply_btn, self.cancel_btn], spacing=8),
            ], spacing=6),
            padding=10, border_radius=8, bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE))

    # ------------------------------------------------------------ 生命周期
    def set_config(self, cfg) -> None:
        self.cfg = cfg

    def busy(self) -> bool:
        return self._job.running

    def begin(self, tasks, cfg, text: str) -> None:
        """为一批任务重建行。"""
        self.cfg = cfg
        self.text = text
        self.tasks = list(tasks)
        self.buffers.clear()
        self.streams.clear()
        self.subtitles.clear()
        self.leads.clear()
        self.retries.clear()
        self.cards.clear()
        self.tiles.clear()
        self.expanded.clear()
        self._auto_expanded = False
        self.rows.controls = [self._make_tile(t) for t in self.tasks]
        self.hint.value = "点击任意一行可展开该条的流式输出。"
        self.apply_btn.disabled = True
        self.cancel_btn.disabled = False
        self._refresh_counts()

    def start(self, provider) -> bool:
        checker = api_bridge.make_syntax_checker(self.tx)
        return self._job.start(
            tasks=self.tasks, provider=provider, text=self.text,
            timeout=self.cfg.timeout, syntax_checker=checker,
            max_concurrency=self.cfg.max_concurrency)

    def cancel(self) -> None:
        self._job.cancel()
        if self.cfg is not None:
            self.hint.value = "正在取消…（在途请求会被 socket shutdown 打断）"

    # ------------------------------------------------------------ 行构造
    def _make_tile(self, task) -> ft.ExpansionTile:
        idx = task.index
        icon, label, color = api_bridge.status_meta(task.status)
        lead = ft.Text(icon, size=15, color=_color(color))
        sub = ft.Text("%s %s" % (icon, label), size=10, color=_color(color))
        stream = ft.Text("", size=10, font_family=MONO, selectable=True,
                         color=ft.Colors.GREY_200)
        box = ft.Container(
            content=ft.Column([stream], scroll=ft.ScrollMode.AUTO, auto_scroll=True),
            height=_STREAM_BOX_HEIGHT, bgcolor=ft.Colors.GREY_900,
            padding=8, border_radius=6)
        retry = ft.TextButton("重试这一条", visible=False,
                              on_click=lambda e, t=task: self._on_retry(t))
        tile = ft.ExpansionTile(
            title=ft.Text(api_bridge.task_title(task), size=12,
                          font_family=MONO),
            subtitle=sub,
            leading=lead,
            # horizontal_alignment=STRETCH 是必须的：ExpansionTile 的 controls
            # 不会横向拉伸子元素，而空的流式 Text 宽度为 0 —— 会让深色框
            # 塌成一条竖线（与 PoC 报告 §4.6 bug#2 同型，实机踩到过：
            # 失败条目没有 chunk，正文为空，框就塌了）。
            controls=[ft.Column([box, ft.Row([retry])], spacing=4,
                                horizontal_alignment=ft.CrossAxisAlignment.STRETCH)],
            on_change=lambda e, t=task: self._on_expand(e, t),
            maintain_state=True,
        )
        self.streams[idx] = stream
        self.subtitles[idx] = sub
        self.leads[idx] = lead
        self.retries[idx] = retry
        self.tiles[idx] = tile
        return tile

    def _on_expand(self, e, task) -> None:
        idx = task.index
        opened = str(getattr(e, "data", "")).strip().lower() in ("true", "1")
        if opened:
            self.expanded.add(idx)
            # 展开时一次性补齐已缓冲的正文（按需渲染）
            self.streams[idx].value = self.buffers.get(idx, "")
        else:
            self.expanded.discard(idx)
        self.page.update()

    # ------------------------------------------------------------ 事件应用
    def _apply_events(self, events) -> None:
        """只改控件值，**不** update —— update 由 FixJob._drain 每轮统一做一次。"""
        touched = set()
        for ev in events:
            if ev.index < 1 or ev.index > len(self.tasks):
                continue
            task = self.tasks[ev.index - 1]
            if ev.chunk:
                buf = self.buffers.get(ev.index, "") + ev.chunk
                self.buffers[ev.index] = buf
                if ev.index in self.expanded:
                    # 只有展开的这条才写控件 / 才需要重排并滚到底
                    self.streams[ev.index].value = buf
            else:
                if ev.status:
                    task.status = ev.status
                task.detail = ev.detail
                self._refresh_row(ev.index)
                # 第一条转入 running 的条目自动展开：用户一按就能看到流式反馈，
                # 之后不再切换，避免抢走用户正在读的那一条。
                if (task.status == api_bridge.STATUS_RUNNING
                        and not self._auto_expanded):
                    self._auto_expanded = True
                    self.expanded.add(ev.index)
                    self.tiles[ev.index].expanded = True
                    self.streams[ev.index].value = self.buffers.get(ev.index, "")
            touched.add(ev.index)
        if touched:
            self._refresh_counts()

    def _refresh_row(self, idx: int) -> None:
        task = self.tasks[idx - 1]
        icon, label, color = api_bridge.status_meta(task.status)
        detail = ("：" + task.detail) if task.detail else ""
        self.leads[idx].value = icon
        self.leads[idx].color = _color(color)
        self.subtitles[idx].value = ("%s %s%s" % (icon, label, detail))[:110]
        self.subtitles[idx].color = _color(color)
        self.retries[idx].visible = (task.status == api_bridge.STATUS_FAILED)

    def _refresh_counts(self) -> None:
        total = len(self.tasks)
        by: dict[str, int] = {}
        for t in self.tasks:
            by[t.status] = by.get(t.status, 0) + 1
        done = by.get(api_bridge.STATUS_DONE, 0)
        failed = by.get(api_bridge.STATUS_FAILED, 0)
        running = by.get(api_bridge.STATUS_RUNNING, 0)
        pending = by.get(api_bridge.STATUS_PENDING, 0)
        skipped = by.get(api_bridge.STATUS_SKIPPED, 0)
        parts = ["%d/%d 完成" % (done, total)]
        if running:
            parts.append("%d 进行中" % running)
        if pending:
            parts.append("%d 等待" % pending)
        if failed:
            parts.append("%d 失败" % failed)
        if skipped:
            parts.append("%d 跳过" % skipped)
        self.counts.value = " · ".join(parts)
        self.bar.value = (done + failed + skipped) / total if total else 0

    def _summary(self) -> str:
        """基于面板中**全部**任务汇总。

        不能直接用 ``ParallelResult`` 的 summarize：单条重试跑的是一个只有 1 条任务的
        作业，直接用它会让汇总行从「共 2 条」退化成「共 1 条」（实机踩过）。
        """
        by: dict[str, int] = {}
        for t in self.tasks:
            by[t.status] = by.get(t.status, 0) + 1
        return "共 %d 条：完成 %d / 失败 %d / 跳过 %d" % (
            len(self.tasks),
            by.get(api_bridge.STATUS_DONE, 0),
            by.get(api_bridge.STATUS_FAILED, 0),
            by.get(api_bridge.STATUS_SKIPPED, 0),
        )

    def _finish(self, result, error: str) -> None:
        self.cancel_btn.disabled = True
        if error:
            self.hint.value = "并行修复异常：" + error
            self.page.update()
            return
        if result is not None:
            self.hint.value = self._summary()
        self.apply_btn.disabled = not any(
            t.status == api_bridge.STATUS_DONE for t in self.tasks)
        self.page.update()

    # ------------------------------------------------------------ 交互
    def _on_cancel(self, e) -> None:
        if self._job.running:
            self.cancel()
        self.page.update()

    def _on_retry(self, task) -> None:
        if self._job.running:
            self.hint.value = "当前作业还在跑，稍后再重试这一条。"
            self.page.update()
            return
        if self.cfg is None:
            return
        try:
            provider = api_bridge.make_provider(self.cfg)
        except api_bridge.ProviderError as exc:
            self.hint.value = api_bridge.safe_error(
                "%s：%s" % (api_bridge.error_category(exc), exc), self.cfg)
            self.page.update()
            return
        # 单条重跑：复用同一套编排（并发 1），错误隔离语义不变
        task.status = api_bridge.STATUS_PENDING
        task.detail = ""
        task.replacement = ""
        task.retries = 0
        self._refresh_row(task.index)
        self.apply_btn.disabled = True
        self.cancel_btn.disabled = False
        self.hint.value = "正在重试 %s…" % api_bridge.task_title(task)
        checker = api_bridge.make_syntax_checker(self.tx)
        self._job.start(tasks=[task], provider=provider, text=self.text,
                        timeout=self.cfg.timeout, syntax_checker=checker,
                        max_concurrency=1)
        self.page.update()

    def _on_apply_all(self, e) -> None:
        if self.cfg is None:
            return
        checker = api_bridge.make_syntax_checker(self.tx)
        try:
            merged, dropped = api_bridge.merge_replacements(
                self.text, self.tasks, syntax_checker=checker)
        except Exception as exc:  # noqa: BLE001
            self.hint.value = api_bridge.safe_error(
                "合并失败：%s: %s" % (type(exc).__name__, exc), self.cfg)
            self.page.update()
            return
        for t in dropped:
            self._refresh_row(t.index)
        if merged == self.text:
            self.hint.value = "没有可应用的修改（%d 条被语法闸门丢弃）。" % len(dropped)
            self.page.update()
            return
        diff = api_bridge.render_diff(self.text, merged)
        note = ""
        if dropped:
            note = "注意：%d 条在合并阶段被 bash -n 闸门丢弃（不会写入产物）。" % len(dropped)

        def confirm(ev) -> None:
            self.page.pop_dialog()
            self.on_apply(merged, "已应用 %d 条修复" % len(
                [t for t in self.tasks if t.status == api_bridge.STATUS_DONE]))

        dialog = ft.AlertDialog(
            title=ft.Text("确认应用修复", size=16),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("以下改动将写入产物（已逐条通过 bash -n 闸门）：", size=12),
                    ft.Container(
                        content=ft.Column([
                            # 必须显式给浅色：默认前景色在浅色主题下是深色，
                            # 落在 GREY_900 上会变成「深底深字」几乎不可读（实机踩过）
                            ft.Text(diff, size=11, font_family=MONO, selectable=True,
                                    color=ft.Colors.GREY_200)
                        ], scroll=ft.ScrollMode.AUTO,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                        height=300, bgcolor=ft.Colors.GREY_900, padding=8,
                        border_radius=6),
                    ft.Text(note, size=11, color=ft.Colors.ORANGE_600,
                            visible=bool(note)),
                ], spacing=8, tight=True),
                width=340),
            actions=[
                ft.TextButton("取消", on_click=lambda ev: self.page.pop_dialog()),
                ft.FilledButton("确认应用", on_click=confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)
