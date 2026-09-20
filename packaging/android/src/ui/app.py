"""bat2sh Android 主界面（Flet）。

布局（任务书 4.5 + Phase 2 §5.2，移动端用上下两栏而不是三栏）：
    工具栏  [选择文件] [转换] [保存] [校验] [运行] [设置]
    源代码  可编辑
    产物    只读 + 近似高亮
    报告 / 运行输出
    TODO 计数 + [用 AI 并行修复]
    并行面板（方案 B：可展开列表）

**线程纪律**（Phase 1 §4.4.3 实测结论）：
    所有后台线程一律**不直接**调用 page.update()，改为把「改控件」的动作
    投进 UiPump 队列，由唯一的 drainer 协程在 page 的事件循环里批量执行。
    这既覆盖并行修复的高频 chunk 流，也顺手消掉了原有 _log/_say
    从多个线程各自 update 的隐患（例如「转换」线程与并行 drainer 同时刷新）。
"""

from __future__ import annotations

import asyncio
import os
import queue
import sys
import threading
import time
from pathlib import Path

import flet as ft

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import api_bridge  # noqa: E402
import bridge  # noqa: E402
from termux import Termux  # noqa: E402
from ui import api_panel, highlighter  # noqa: E402
from ui.runner import ScriptRunner  # noqa: E402

DATA = Path(os.environ.get("FLET_APP_STORAGE_DATA") or "/tmp/bat2sh-android-data")
RUN_TIMEOUT = 60.0

MONO = "monospace"

# 启动自检用的内联样例：覆盖变量、外部命令、for 循环（需要 fork）
SAMPLE_NAME = "selftest.bat"
SAMPLE_BAT = chr(10).join([
    "@echo off",
    "set GREET=hello",
    "echo %GREET% from bat2sh",
    "for %%i in (1 2 3) do echo item %%i",
])

_PUMP_SECONDS = 0.03


class UiPump:
    """把「修改控件 + update」从任意线程安全地搬到 page 的事件循环。

    背景线程只 ``post()`` 一个可调用对象；唯一执行它们并 ``page.update()`` 的
    是 ``run()`` —— 它由 ``page.run_task`` 调度，因此天然在事件循环里。
    """

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self._q: queue.Queue = queue.Queue()

    def post(self, fn) -> None:
        self._q.put(fn)

    async def run(self) -> None:
        while True:
            batch = []
            while True:
                try:
                    batch.append(self._q.get_nowait())
                except queue.Empty:
                    break
            if batch:
                for fn in batch:
                    try:
                        fn()
                    except Exception:  # noqa: BLE001 —— 单个动作失败不影响其余
                        pass
                try:
                    self.page.update()
                except Exception:  # noqa: BLE001 —— 页面已销毁
                    pass
            await asyncio.sleep(_PUMP_SECONDS)


class App:
    """Android 版：选择 / 转换 / 高亮 / 保存 / bash -n / 运行 / API 并行修复。"""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.tx = Termux(DATA)
        self.runner = ScriptRunner(self.tx)
        self.conversion: bridge.Conversion | None = None
        self.source_name = ""
        self.picker = ft.FilePicker()
        self.pump = UiPump(page)

        # --- API 修复（Phase 2）---
        self.api_cfg = api_bridge.load_config()
        self.parallel = api_panel.ParallelPanel(page, self.tx, on_apply=self._on_fix_applied)
        self.fix_btn = ft.FilledButton("用 AI 并行修复", on_click=self.on_fix, disabled=True)
        self.todo_line = ft.Text("", size=11, color=ft.Colors.GREY_700)

        self.status = ft.Text("正在准备内嵌 Termux 运行时…", selectable=True,
                              size=12, color=ft.Colors.GREY_700)
        self.source = ft.TextField(
            multiline=True, min_lines=6, max_lines=12, text_size=12,
            text_style=ft.TextStyle(font_family=MONO), value="", expand=True,
            hint_text="点「选择文件」载入 .bat / .cmd / .ps1，或直接在这里粘贴")
        self.out_view = ft.Text(spans=[], selectable=True, size=12,
                                font_family=MONO, color=ft.Colors.GREY_200)
        # 注意：不要给这个 Container 加 expand —— 在 Column 里 expand 只作用于主轴，
        # 交叉轴会收缩到子元素宽度，空产物时会塌成一条竖线。固定高度即可。
        self.out_box = ft.Container(
            content=ft.Column([self.out_view], scroll=ft.ScrollMode.AUTO),
            height=260, bgcolor=ft.Colors.GREY_900, padding=10,
            border_radius=8)
        self.report = ft.TextField(
            multiline=True, read_only=True, min_lines=6, max_lines=16,
            text_size=12, text_style=ft.TextStyle(font_family=MONO),
            value="", expand=True)

    # ------------------------------------------------------------ 组装
    def build(self) -> None:
        self.page.title = "bat2sh"
        # 滚动交给下面那个 root Column（page.scroll 与嵌套滚动会打架）
        self.page.services.append(self.picker)

        toolbar = ft.Row(
            [
                ft.FilledButton("选择文件", on_click=self.on_pick),
                ft.FilledButton("转换", on_click=self.on_convert),
                ft.FilledButton("保存", on_click=self.on_save),
                ft.FilledButton("校验", on_click=self.on_check),
                ft.FilledButton("运行", on_click=self.on_run),
                ft.OutlinedButton("设置", on_click=self.on_settings),
            ],
            wrap=True, spacing=8, run_spacing=8,
        )

        # 整页包在一个 STRETCH 的 Column 里：Flet 1.0 的 Page 没有
        # horizontal_alignment，若直接 page.add(Container)，交叉轴是 start，
        # 无宽度的 Container 会收缩成一条竖线（产物框就踩过这个坑）。
        root = ft.Column(
            [
                ft.Text("bat2sh", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("Windows 批处理 / PowerShell -> Bash（Android 版）",
                        size=11, color=ft.Colors.GREY_600),
                toolbar,
                self.status,
                ft.Divider(height=8),
                ft.Text("源代码", weight=ft.FontWeight.BOLD, size=13),
                self.source,
                ft.Text("产物（只读 + 近似高亮）", weight=ft.FontWeight.BOLD, size=13),
                self.out_box,
                ft.Text("报告 / 运行输出", weight=ft.FontWeight.BOLD, size=13),
                self.report,
                ft.Divider(height=8),
                ft.Row([self.fix_btn, self.todo_line], spacing=10,
                       wrap=True, run_spacing=6),
                self.parallel.view,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self.page.add(root)
        # 唯一的 UI 刷新协程：所有后台线程都经它改控件
        self.page.run_task(self.pump.run)
        threading.Thread(target=self._boot, daemon=True).start()
        self._refresh_todo_state()

    # ------------------------------------------------------------ 工具
    def _say(self, msg: str) -> None:
        """任意线程可调：改状态栏文字。"""
        self.pump.post(lambda: setattr(self.status, "value", msg))

    def _log(self, msg: str) -> None:
        """任意线程可调：追加一行日志。stdout 立即写（logcat），控件改动入队。"""
        stamp = time.strftime("%H:%M:%S")
        line = "[" + stamp + "] " + msg
        print(line, flush=True)  # 镜像到 stdout -> logcat tag flet.python
        self.pump.post(lambda: self._log_now(line))

    def _log_now(self, line: str) -> None:
        """只允许在事件循环里执行（由 pump 调度）。"""
        old = self.report.value or ""
        # 分隔符必须加在**新行之前**：加在后面会让两次日志首尾相连
        combined = (old + chr(10) + line) if old else line
        # 面板只保留最近 200 行，避免长时间运行把内存撑爆
        lines = combined.splitlines()
        if len(lines) > 200:
            combined = chr(10).join(lines[-200:])
        self.report.value = combined

    def _show_script(self, script: str) -> None:
        spans, truncated = highlighter.build_spans(script or "")
        self.out_view.spans = spans
        if truncated:
            self._log("产物较长，高亮视图已截断（完整内容仍会保存 / 运行）")

    def _require_conversion(self) -> bool:
        if self.conversion is None or not self.conversion.ok:
            self._say("请先「选择文件」并「转换」")
            return False
        return True

    def _refresh_todo_state(self) -> None:
        """刷新「TODO N 条」与修复按钮可用性。只改控件，由调用方负责 update。"""
        conv = self.conversion
        if conv is None or not conv.ok:
            self.todo_line.value = ""
            self.fix_btn.disabled = True
            return
        try:
            n = api_bridge.count_todos(conv.script, conv.report)
        except Exception:  # noqa: BLE001
            n = 0
        if n:
            self.todo_line.value = "报告里 TODO %d 条" % n
            self.fix_btn.disabled = False
        else:
            self.todo_line.value = "报告里没有可修复的 TODO"
            self.fix_btn.disabled = True

    # ------------------------------------------------------------ 启动
    def _boot(self) -> None:
        try:
            self._say("正在解压 Termux 运行时（首次启动约需数秒）…")
            info = self.tx.ensure()
            self.tx.prepare_dirs()
            if not self.tx.ready:
                self._say("运行时不可用：" + info)
                self._log("Termux 运行时准备失败：" + info)
                return
            rc, out, err, mode = self.tx.run(
                ["-c", "echo READY; bash --version | head -1; id"], timeout=30)
            self._say("就绪（入口进程：%s）" % mode)
            self._log("Termux 运行时：" + info)
            self._log("入口方式：" + mode + "  rc=" + str(rc))
            self._log((out or err).strip())
            self._log("工作目录：" + str(self.tx.work))
            self._log("API 配置：" + api_bridge.describe(self.api_cfg))
            self._self_test()
        except Exception as exc:  # noqa: BLE001
            self._say("启动失败：" + type(exc).__name__ + ": " + str(exc))

    def _self_test(self) -> None:
        """启动自检：用内联样例跑一遍 转换 -> bash -n -> 运行。

        复用按钮走的同一条链路（bridge.convert / runner.stage / check / run），
        所以它过了就说明设备上的主流程是通的；用户一打开应用即可看到结果。
        """
        self._log("--- 启动自检 ---")
        try:
            conv = bridge.convert(SAMPLE_BAT, SAMPLE_NAME)
            if not conv.ok:
                self._log("自检失败（转换）：" + conv.error)
                return
            self._log("转换 OK：" + conv.headline())
            p = self.runner.stage(conv.script, "selftest.sh")
            checked, ok, msg = self.runner.check(p)
            self._log("bash -n：%s %s" % ("PASS" if ok else "FAIL",
                                         msg if checked else "（未执行）" + msg))
            rc, out, err, mode = self.runner.run(p, timeout=30)
            self._log("运行 rc=%s via %s" % (rc, mode))
            if (out or "").strip():
                self._log(out.rstrip())
            if (err or "").strip():
                self._log("[stderr] " + err.rstrip())
            self._log("--- 自检%s ---" % ("通过" if (ok and rc == 0) else "存在失败项"))
            # 顺带自检 API 侧最关键的一环：Termux 版语法闸门真的能跑 bash -n
            good, gmsg = api_bridge.check_script(self.tx, "echo ok\n")
            bad, bmsg = api_bridge.check_script(self.tx, "if true; then\n")
            self._log("语法闸门自检：合法脚本=%s，非法脚本=%s"
                      % ("通过" if good else "异常(" + gmsg + ")",
                         "检出错误" if not bad else "漏检!(%s)" % bmsg))
        except Exception as exc:  # noqa: BLE001
            self._log("自检异常：" + type(exc).__name__ + ": " + str(exc))

    # ------------------------------------------------------------ 事件
    async def on_pick(self, e) -> None:
        try:
            files = await self.picker.pick_files(
                dialog_title="选择 .bat / .cmd / .ps1",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["bat", "cmd", "ps1"],
                allow_multiple=False, with_data=True)
        except Exception as exc:  # noqa: BLE001
            self._say("选择文件失败：" + str(exc))
            return
        if not files:
            return
        f = files[0]
        self.source_name = f.name or "input.bat"
        raw = f.bytes
        if raw is None and f.path:
            try:
                raw = Path(f.path).read_bytes()
            except OSError as exc:
                self._say("读取失败：" + str(exc))
                return
        if raw is None:
            self._say("未能读取文件内容（" + self.source_name + "）")
            return
        text, enc, replaced = bridge.decode_source(raw)
        self.source.value = text
        self.conversion = None
        self._show_script("")
        self._refresh_todo_state()
        note = "已载入 %s（%d 字节，编码 %s%s）" % (
            self.source_name, len(raw), enc, "，含替换字符" if replaced else "")
        self._say(note)
        self._log(note)
        self.page.update()

    def on_convert(self, e) -> None:
        text = self.source.value or ""
        name = self.source_name or "input.bat"
        if not text.strip():
            self._say("源内容为空")
            return
        self._say("转换中…")

        def work() -> None:
            try:
                conv = bridge.convert(text, name)
            except Exception as exc:  # noqa: BLE001
                self.conversion = None
                self._say("转换异常：" + type(exc).__name__ + ": " + str(exc))
                return
            self.conversion = conv
            self.pump.post(lambda: setattr(
                self.report, "value", chr(10).join(conv.diagnostics())))
            self.pump.post(lambda: self._show_script(conv.script))
            self.pump.post(self._refresh_todo_state)
            self._say(conv.headline())

        threading.Thread(target=work, daemon=True).start()

    async def on_save(self, e) -> None:
        if not self._require_conversion():
            return
        conv = self.conversion
        assert conv is not None
        try:
            p = self.runner.stage(conv.script, conv.output_name)
        except OSError as exc:
            self._say("写入应用目录失败：" + str(exc))
            return
        self._log("已保存到应用目录：" + str(p))
        try:
            target = await self.picker.save_file(
                dialog_title="保存产物",
                file_name=conv.output_name,
                src_bytes=conv.script.encode("utf-8"))
            if target:
                self._log("已导出到：" + str(target))
                self._say("已导出：" + str(target))
                return
        except Exception as exc:  # noqa: BLE001
            self._log("系统另存为不可用，保留应用目录副本：" + str(exc))
        self._say("已保存：" + str(p))

    def on_check(self, e) -> None:
        if not self._require_conversion():
            return
        conv = self.conversion
        assert conv is not None
        try:
            p = self.runner.stage(conv.script, conv.output_name)
        except OSError as exc:
            self._say("写入失败：" + str(exc))
            return
        self._say("bash -n 校验中…")

        def work() -> None:
            checked, ok, msg = self.runner.check(p)
            if not checked:
                self._say("未执行校验：" + msg)
                self._log("bash -n 未执行：" + msg)
                return
            self._say(("bash -n 通过" if ok else "bash -n 失败") + "：" + msg)
            self._log("bash -n " + ("PASS" if ok else "FAIL") + " " + str(p))
            if not ok:
                self._log(msg)

        threading.Thread(target=work, daemon=True).start()

    def on_run(self, e) -> None:
        if not self._require_conversion():
            return
        if not self.tx.ready:
            self._say("Termux 运行时不可用，无法运行（可先用「校验」）")
            return
        conv = self.conversion
        assert conv is not None
        try:
            p = self.runner.stage(conv.script, conv.output_name)
        except OSError as exc:
            self._say("写入失败：" + str(exc))
            return
        self._say("运行中（最多 %ds）…" % int(RUN_TIMEOUT))
        self._log("$ bash " + str(p))

        def work() -> None:
            rc, out, err, mode = self.runner.run(p, timeout=RUN_TIMEOUT)
            if (out or "").strip():
                self._log(out.rstrip())
            if (err or "").strip():
                self._log("[stderr] " + err.rstrip())
            self._log("[rc=%s via %s]" % (rc, mode))
            self._say("运行结束 rc=" + str(rc))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ API 修复
    def on_settings(self, e) -> None:
        def saved(new_cfg) -> None:
            self.api_cfg = new_cfg
            self.parallel.set_config(new_cfg)
            # describe() 只报 key 是否已设置，绝不回显 key 本体
            self._log("API 配置已保存：" + api_bridge.describe(new_cfg))
            self._say("API 配置已保存")

        api_panel.open_settings_dialog(self.page, self.api_cfg, saved)

    async def on_fix(self, e) -> None:
        if not self._require_conversion():
            return
        conv = self.conversion
        assert conv is not None
        if self.parallel.busy():
            self._say("已有一个并行修复作业在跑")
            return
        if not self.tx.ready:
            self._say("Termux 运行时不可用：并行修复需要 bash -n 闸门")
            return
        missing = api_bridge.missing_requirements(self.api_cfg)
        if missing:
            self._say("请先在「设置」里配置：" + "；".join(missing))
            api_panel.open_settings_dialog(self.page, self.api_cfg,
                                           lambda c: self._on_settings_saved(c))
            return
        try:
            markers = api_bridge.scan_markers(conv.script, conv.report)
        except Exception as exc:  # noqa: BLE001
            self._say("扫描 TODO 失败：" + str(exc))
            return
        if not markers:
            self._say("没有可修复的 TODO")
            return
        try:
            tasks = api_bridge.plan_tasks(
                markers, self.source.value or "", self.source_name or "source.bat",
                conv.script, self.api_cfg.context_lines)
        except Exception as exc:  # noqa: BLE001
            self._say("构造任务失败：" + str(exc))
            return

        def confirmed() -> None:
            try:
                provider = api_bridge.make_provider(self.api_cfg)
            except api_bridge.ProviderError as exc:
                self._say(api_bridge.safe_error(
                    "%s：%s" % (api_bridge.error_category(exc), exc), self.api_cfg))
                return
            self.parallel.set_config(self.api_cfg)
            self.parallel.begin(tasks, self.api_cfg, conv.script)
            if not self.parallel.start(provider):
                self._say("已有一个并行修复作业在跑")
                return
            self._log("并行修复开始：%d 条，并发 %d，endpoint=%s" % (
                len(tasks), self.api_cfg.max_concurrency, self.api_cfg.base_url))
            self._say("并行修复中（并发 %d）…" % self.api_cfg.max_concurrency)

        api_panel.open_privacy_dialog(
            self.page, len(tasks), self.api_cfg.base_url, confirmed)

    def _on_settings_saved(self, new_cfg) -> None:
        self.api_cfg = new_cfg
        self.parallel.set_config(new_cfg)
        self._log("API 配置已保存：" + api_bridge.describe(new_cfg))
        self._say("API 配置已保存")

    def _on_fix_applied(self, new_text: str, summary: str) -> None:
        """并行面板确认应用后：写回产物 -> 重新校验 -> 落盘。"""
        conv = self.conversion
        if conv is None:
            return
        conv.script = new_text
        self._show_script(new_text)
        self._log(summary)
        self._say(summary)
        self._refresh_todo_state()
        self.page.update()

        def work() -> None:
            try:
                p = self.runner.stage(new_text, conv.output_name)
            except OSError as exc:
                self._log("写入修复后产物失败：" + str(exc))
                return
            self._log("修复后产物已保存：" + str(p))
            checked, ok, msg = self.runner.check(p)
            self._log("修复后 bash -n：%s %s" % (
                "PASS" if ok else "FAIL", msg if checked else "（未执行）" + msg))

        threading.Thread(target=work, daemon=True).start()


def build(page: ft.Page) -> None:
    App(page).build()
