"""API 修复桥 —— core 零改动。

`core/api/` 的四个模块（config / provider / fixer / parallel）在 Android 上**原样可用**，
本模块只做三件 Flet 侧的事：

1. **配置读写**：`ApiConfig` 落到 `<FLET_APP_STORAGE_DATA>/config/bat2sh/api.json`。
   `XDG_CONFIG_HOME` 由 `main.py` 的**首条语句**注入，core 的 `api_config_path()`
   自动跟随 —— 实测见 docs/android-api-assessment.md §4.2。

2. **注入 Termux 版 syntax_checker（关键）**：
   core 默认的 `bash_syntax_error` 用 `shutil.which("bash")` 找 bash，
   **找不到就 return None** —— 即「静默判通过」。Android 上 Termux 的 bash 不在 PATH 里，
   于是并行修复的每一处「建议未通过 bash -n」闸门都会假通过，
   **坏的合并会被当成好的写进产物，而用户看不到任何错误**。
   `run_parallel` 与 `merge_replacements` 都接受 `syntax_checker` 注入，
   所以这里换掉即可，**core 一行都不用改**。

3. **编排薄封装**：`plan_tasks` / `run_parallel` / `merge_replacements`。

本模块**不导入 flet**（保持可在桌面直接 smoke test），也不做任何 UI 决策。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from bat2sh.core.api import config as api_config  # noqa: E402
from bat2sh.core.api import fixer, parallel  # noqa: E402
from bat2sh.core.api.config import ApiConfig  # noqa: E402
from bat2sh.core.api.parallel import (  # noqa: E402
    STATUS_DONE, STATUS_FAILED, STATUS_PENDING, STATUS_RUNNING, STATUS_SKIPPED,
    FixEvent, FixTask, ParallelResult,
)
from bat2sh.core.api.provider import (  # noqa: E402
    ProviderError, create_provider, error_category, redact,
)
from bat2sh.core.types import ConvertReport  # noqa: E402

# 语法闸门探针文件名。用前缀点开头，避免与用户的产物重名。
_SYNTAX_PROBE_NAME = ".bat2sh_syntax_probe.sh"

# 状态 -> (图标, 中文标签, 颜色名)。颜色名由 UI 层映射到 ft.Colors，避免本模块依赖 flet。
STATUS_META: dict[str, tuple[str, str, str]] = {
    STATUS_PENDING: ("⏸", "等待", "grey"),
    STATUS_RUNNING: ("⟳", "流式中", "blue"),
    STATUS_DONE: ("✓", "完成", "green"),
    STATUS_FAILED: ("✗", "失败", "red"),
    STATUS_SKIPPED: ("⊘", "跳过", "orange"),
}


def status_meta(status: str) -> tuple[str, str, str]:
    return STATUS_META.get(status, ("?", status, "grey"))


# ------------------------------------------------------------------ 配置

def config_path() -> Path:
    """当前生效的 api.json 路径（跟随 XDG_CONFIG_HOME）。"""
    return api_config.api_config_path()


def load_config() -> ApiConfig:
    return api_config.load_api_config()


def save_config(cfg: ApiConfig) -> None:
    api_config.save_api_config(cfg)


def missing_requirements(cfg: ApiConfig) -> list[str]:
    """必填项缺失说明；空列表 = 可发起请求。"""
    missing = api_config.missing_requirements(cfg)
    if not cfg.api_key:
        # key 允许为空（本地端点常无鉴权），仅作提示，不算「缺失」
        pass
    return missing


def describe(cfg: ApiConfig) -> str:
    """给用户看的一行配置摘要 —— **绝不包含 key 本体**，只报是否已设置。"""
    key_state = "已设置(%d 字符)" % len(cfg.api_key) if cfg.api_key else "未设置"
    return (
        "endpoint=%s  model=%s  key=%s  并发=%d  思考=%s  超时=%gs"
        % (
            cfg.base_url or "(未配置)",
            cfg.model or "(未配置)",
            key_state,
            cfg.max_concurrency,
            "开" if cfg.enable_thinking else "关",
            cfg.timeout,
        )
    )


def safe_error(msg: str, cfg: ApiConfig | None = None) -> str:
    """所有对外错误信息的唯一出口：把 key 抹成 ***（纪律 6）。

    core 的 ProviderError 已保证自身消息不含 key（provider.py 文档），
    这里再兜一层，防止异常链/底层 socket 文本意外带上凭据。
    """
    if cfg is None:
        return msg
    return redact(msg, cfg.api_key)


def make_provider(cfg: ApiConfig):
    """构造 provider。配置缺失抛 ProviderConfigError，由调用方转成用户提示。"""
    return create_provider(cfg)


# ------------------------------------------------------------------ 语法闸门

def make_syntax_checker(tx):
    """构造 Termux 版 ``syntax_checker``，注入给 run_parallel / merge_replacements。

    契约（与 core ``SyntaxChecker`` 一致）：返回 ``None`` = 通过，返回字符串 = 失败原因。

    **与 core 默认实现的关键差别**：core 在「跑不了 bash -n」时返回 None（判通过）；
    这里在「未真正执行校验」时返回**失败**。宁可拒绝一处合法建议，也不能让坏代码静默进产物。
    """
    def checker(script: str) -> str | None:
        if not tx.ready:
            return "无法执行 bash -n：Termux 运行时不可用"
        # 路径延迟到调用时再取：工厂函数本身不应该依赖 tx 已经可用
        try:
            probe = Path(tx.work) / _SYNTAX_PROBE_NAME
            tx.prepare_dirs()
            probe.write_text(script, encoding="utf-8")
        except (OSError, TypeError) as exc:
            return "无法执行 bash -n：写入探针失败 %s" % exc
        checked, ok, message = tx.syntax_check(probe)
        if not checked:
            # 「未执行」必须判失败 —— 这正是 core 默认实现在 Android 上的漏洞
            return "无法执行 bash -n（%s）" % message
        return None if ok else message

    return checker


def check_script(tx, script: str) -> tuple[bool, str]:
    """给 UI 用的单次校验：返回 (是否通过, 信息)。未执行 = 不通过。"""
    problem = make_syntax_checker(tx)(script)
    return (problem is None), (problem or "bash -n 通过")


# ------------------------------------------------------------------ 编排

def count_todos(output_text: str, report: ConvertReport | None = None) -> int:
    return fixer.count_markers(output_text, report)


def scan_markers(output_text: str, report: ConvertReport | None = None):
    return fixer.scan_todo_markers(output_text, report)


def plan_tasks(markers, source_text: str, source_name: str, output_text: str,
               context_lines: int) -> list[FixTask]:
    """为每个标记冻结行号并构造 prompt（prompt 即「将发送的内容」）。"""
    return parallel.plan_tasks(markers, source_text, source_name, output_text, context_lines)


def prompts_preview(tasks) -> str:
    """隐私提示里展示的「将要发送什么」摘要（不含 key）。"""
    lines = ["将发送 %d 条，每条包含：" % len(tasks),
             "  · 该处 TODO 标记原文与报告元数据",
             "  · 源脚本对应行 ±N 行上下文",
             "  · 目标 Bash 相邻 2 行（其它 TODO 已替换为占位说明）"]
    return "\n".join(lines)


def run_parallel(tasks, provider, *, text: str, timeout: float, syntax_checker,
                 on_event, cancel_event, max_concurrency: int) -> ParallelResult:
    """跑并行修复。**阻塞**函数 —— 调用方必须放在工作线程里（见 ui/api_panel.py）。"""
    return parallel.run_parallel(
        tasks, provider,
        text=text,
        timeout=timeout,
        syntax_checker=syntax_checker,   # ← 必须注入，否则静默假通过
        on_event=on_event,
        max_concurrency=max_concurrency,
        cancel_event=cancel_event,
    )


def merge_replacements(text: str, tasks, *, syntax_checker) -> tuple[str, list[FixTask]]:
    """合并 done 条目（降序 + 逐步 bash -n 闸门）。返回 (新文本, 被丢弃的条目)。"""
    return parallel.merge_replacements(text, tasks, syntax_checker=syntax_checker)


def render_diff(old: str, new: str) -> str:
    return fixer.render_diff(old, new, "当前", "修复后")


def summarize(result: ParallelResult) -> str:
    done, failed = len(result.done), len(result.failed)
    skipped = len(result.skipped)
    total = len(result.tasks)
    extra = ""
    if result.rate_limit_hits:
        extra = "，限流 %d 次" % result.rate_limit_hits
    if result.final_concurrency != 0:
        extra += "，最终并发 %d" % result.final_concurrency
    return "共 %d 条：完成 %d / 失败 %d / 跳过 %d%s" % (total, done, failed, skipped, extra)


def task_title(task: FixTask) -> str:
    """展开行的标题。"""
    return "#%d 第 %d 行" % (task.index, task.out_line)


def task_subtitle(task: FixTask) -> str:
    icon, label, _ = status_meta(task.status)
    detail = ("：" + task.detail) if task.detail else ""
    return "%s %s%s" % (icon, label, detail)


__all__ = [
    "ApiConfig", "FixEvent", "FixTask", "ParallelResult", "ProviderError",
    "STATUS_DONE", "STATUS_FAILED", "STATUS_PENDING", "STATUS_RUNNING", "STATUS_SKIPPED",
    "check_script", "config_path", "count_todos", "describe", "error_category",
    "load_config", "make_provider", "make_syntax_checker", "merge_replacements",
    "missing_requirements", "plan_tasks", "prompts_preview", "render_diff",
    "run_parallel", "safe_error", "save_config", "scan_markers", "status_meta",
    "summarize", "task_subtitle", "task_title",
]
