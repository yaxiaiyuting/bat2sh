"""TODO 并行修复编排（core/api/parallel.py）测试。

不访问网络：``FakeProvider`` 为线程安全的脚本化实现。并发/退避/合并语义断言集中在
``docs/v1.7.0-design.md``  §7.1 的不变量上；``sleep`` / ``jitter`` / ``syntax_checker``
均注入，测试免等待、免跑 bash（另有少量真实 ``bash -n`` 用例）。
"""

from __future__ import annotations

import threading
import time

import pytest

from bat2sh.core.api import fixer
from bat2sh.core.api.parallel import (
    RATE_LIMIT_BACKOFF_BASE,
    RATE_LIMIT_BACKOFF_CAP,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    FixEvent,
    _backoff_delay,
    evaluate_reply,
    format_status_line,
    merge_replacements,
    plan_tasks,
    run_parallel,
)
from bat2sh.core.api.provider import (
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderServerError,
)

OUTPUT = (
    "#!/usr/bin/env bash\n"
    "set -euo pipefail\n"
    "# TODO: 手动检查: cmdA\n"
    "echo keep\n"
    "# TODO: 手动检查: cmdB\n"
)
SOURCE = "cmdA\ncmdB\n"


def _marker(out_line: int, original: str, line_text: str) -> fixer.TodoMarker:
    return fixer.TodoMarker(
        out_line=out_line,
        kind="line",
        line_text=line_text,
        marker_text=line_text,
        original=original,
        source_line=out_line - 2,
        category="command",
        diagnostic_message="测试诊断",
    )


MARKER_A = _marker(3, "cmdA", "# TODO: 手动检查: cmdA")
MARKER_B = _marker(5, "cmdB", "# TODO: 手动检查: cmdB")


def _null_checker(_text: str) -> str | None:
    return None


def _pair() -> list:
    return plan_tasks([MARKER_A, MARKER_B], SOURCE, "demo.bat", OUTPUT, 3)


def _three_markers() -> list[fixer.TodoMarker]:
    return [
        _marker(2, "aaa", "# TODO: 手动检查: aaa"),
        _marker(4, "bbb", "# TODO: 手动检查: bbb"),
        _marker(6, "ccc", "# TODO: 手动检查: ccc"),
    ]


def _three_output() -> str:
    return (
        "#!/usr/bin/env bash\n"
        "# TODO: 手动检查: aaa\n"
        "echo keep1\n"
        "# TODO: 手动检查: bbb\n"
        "echo keep2\n"
        "# TODO: 手动检查: ccc\n"
    )


def _three_tasks():
    text = _three_output()
    source = "aaa\nbbb\nccc\n"
    return plan_tasks(_three_markers(), source, "demo.bat", text, 3), text


def _reply_for(prompt: str) -> str:
    for name in ("aaa", "bbb", "ccc"):
        if name in prompt:
            return f"echo fixed-{name}"
    return "echo fixed"


class FakeProvider:
    """线程安全脚本化 Provider：记录 prompt、观测最大在途并发。"""

    def __init__(self, reply_for=_reply_for, *, barrier=None, delay=0.0, report_rate_limit=False):
        self._reply_for = reply_for
        self._barrier = barrier
        self._delay = delay
        self._report_rate_limit = report_rate_limit
        self._lock = threading.Lock()
        self.prompts: list[str] = []
        self.inflight = 0
        self.max_inflight = 0

    def complete_stream(
        self, prompt, *, timeout, on_reasoning=None, on_warning=None, on_rate_limit=None
    ):
        with self._lock:
            self.prompts.append(prompt)
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            if self._barrier is not None:
                self._barrier.wait(timeout=5)
            if self._delay:
                time.sleep(self._delay)
            result = self._reply_for(prompt)
            if self._report_rate_limit and isinstance(result, BaseException):
                if on_rate_limit is not None:
                    on_rate_limit(1)
            if isinstance(result, BaseException):
                raise result
            if isinstance(result, str):
                result = [result]
            for chunk in result:
                yield chunk
        finally:
            with self._lock:
                self.inflight -= 1


def _collect():
    events: list[FixEvent] = []
    return events, events.append


# ---------------------------------------------------------------------------
# plan_tasks / evaluate_reply / format
# ---------------------------------------------------------------------------


def test_plan_tasks_freezes_out_line_and_builds_prompt():
    tasks = _pair()
    assert [t.out_line for t in tasks] == [3, 5]
    assert [t.index for t in tasks] == [1, 2]
    assert all(t.status == STATUS_PENDING for t in tasks)
    assert ">>> # TODO: 手动检查: cmdA" in tasks[0].prompt
    assert "cmdA" in tasks[0].prompt and "Windows 源脚本 demo.bat" in tasks[0].prompt


def test_plan_tasks_dedupes_same_out_line():
    duplicate = _marker(3, "cmdA", "# TODO: 手动检查: cmdA")
    tasks = plan_tasks([MARKER_A, duplicate, MARKER_B], SOURCE, "demo.bat", OUTPUT, 3)
    assert [t.out_line for t in tasks] == [3, 5]


@pytest.mark.parametrize(
    "raw",
    ["", "   \n ", "# TODO: 手动检查: 原样", "# TODO: 手动检查: cmdA"],
)
def test_evaluate_reply_marks_skipped(raw):
    task = _pair()[0]
    evaluate_reply(task, raw, OUTPUT, syntax_checker=_null_checker)
    assert task.status == STATUS_SKIPPED
    assert task.replacement == ""


def test_evaluate_reply_done_and_failed(monkeypatch):
    task = _pair()[0]
    evaluate_reply(task, "echo fixed", OUTPUT, syntax_checker=_null_checker)
    assert task.status == STATUS_DONE
    assert task.replacement == "echo fixed"

    failing = _pair()[0]
    evaluate_reply(failing, "echo fixed", OUTPUT, syntax_checker=lambda _t: "语法错误")
    assert failing.status == STATUS_FAILED
    assert "bash -n" in failing.detail


def test_format_status_line():
    task = _pair()[0]
    assert format_status_line(task) == "#1 第3行 pending"
    task.status = STATUS_DONE
    task.detail = "ok"
    assert format_status_line(task) == "#1 第3行 done：ok"


# ---------------------------------------------------------------------------
# 合并：从后往前 + 行号偏移 + 逐级语法闸门
# ---------------------------------------------------------------------------


def test_merge_applies_back_to_front_with_line_shift(bash_check):
    tasks = _pair()
    evaluate_reply(tasks[0], "echo AAAA", OUTPUT, syntax_checker=_null_checker)
    evaluate_reply(tasks[1], "echo B1\necho B2", OUTPUT, syntax_checker=_null_checker)
    assert [t.status for t in tasks] == [STATUS_DONE, STATUS_DONE]

    merged, dropped = merge_replacements(OUTPUT, tasks, syntax_checker=_null_checker)
    assert dropped == []
    assert merged.splitlines() == [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "echo AAAA",
        "echo keep",
        "echo B1",
        "echo B2",
    ]
    assert "cmdA" not in merged and "cmdB" not in merged
    # 高行号的 2 行替换不得破坏低行号（第 3 行）的替换位置
    assert merged.splitlines()[2] == "echo AAAA"
    bash_check(merged)


def test_merge_drops_only_the_item_that_breaks_syntax():
    tasks = _pair()
    evaluate_reply(tasks[0], "echo AAAA", OUTPUT, syntax_checker=_null_checker)
    evaluate_reply(tasks[1], "echo BROKEN", OUTPUT, syntax_checker=_null_checker)

    checker = lambda text: "坏语法" if "BROKEN" in text else None
    merged, dropped = merge_replacements(OUTPUT, tasks, syntax_checker=checker)

    assert [t.index for t in dropped] == [2]
    assert tasks[1].status == STATUS_FAILED
    assert tasks[0].status == STATUS_DONE
    assert "AAAA" in merged and "BROKEN" not in merged


def test_merge_returns_original_when_checker_always_fails():
    tasks = _pair()
    evaluate_reply(tasks[0], "echo AAAA", OUTPUT, syntax_checker=_null_checker)
    evaluate_reply(tasks[1], "echo BBBB", OUTPUT, syntax_checker=_null_checker)
    merged, dropped = merge_replacements(
        OUTPUT, tasks, syntax_checker=lambda _t: "永远失败"
    )
    assert merged == OUTPUT
    assert [t.index for t in dropped] == [2, 1]
    assert all(t.status == STATUS_FAILED for t in tasks)


# ---------------------------------------------------------------------------
# 退避公式 / 并发调度 / 限流
# ---------------------------------------------------------------------------


def test_backoff_delay_is_exponential_and_capped():
    assert RATE_LIMIT_BACKOFF_BASE == 1.0
    assert _backoff_delay(1) == 1.0
    assert _backoff_delay(2) == 2.0
    assert _backoff_delay(3) == 4.0
    assert _backoff_delay(4) == 8.0
    assert _backoff_delay(6) == 30.0
    assert _backoff_delay(50) == RATE_LIMIT_BACKOFF_CAP


def test_concurrency_one_is_serial_and_all_done():
    tasks, text = _three_tasks()
    provider = FakeProvider()
    result = run_parallel(
        tasks,
        provider,
        text=text,
        timeout=1.0,
        syntax_checker=_null_checker,
        max_concurrency=1,
    )
    assert result.final_concurrency == 1
    assert len(result.done) == 3
    assert provider.max_inflight == 1


def test_concurrency_greater_than_task_count():
    tasks, text = _three_tasks()
    provider = FakeProvider()
    result = run_parallel(
        tasks,
        provider,
        text=text,
        timeout=1.0,
        syntax_checker=_null_checker,
        max_concurrency=8,
    )
    assert len(result.done) == 3
    assert 1 <= provider.max_inflight <= 3
    assert result.final_concurrency == 8


def test_true_parallelism_with_barrier():
    tasks, text = _three_tasks()
    provider = FakeProvider(barrier=threading.Barrier(3))
    result = run_parallel(
        tasks,
        provider,
        text=text,
        timeout=1.0,
        syntax_checker=_null_checker,
        max_concurrency=3,
    )
    assert provider.max_inflight == 3
    assert len(result.done) == 3


def test_error_isolation_keeps_other_tasks():
    def reply(prompt: str):
        if "bbb" in prompt:
            return ProviderNetworkError("网络断了")
        return _reply_for(prompt)

    tasks, text = _three_tasks()
    result = run_parallel(
        tasks,
        FakeProvider(reply),
        text=text,
        timeout=1.0,
        syntax_checker=_null_checker,
        max_concurrency=3,
    )
    assert [t.status for t in tasks] == [STATUS_DONE, STATUS_FAILED, STATUS_DONE]
    assert [t.index for t in result.failed] == [2]
    assert "网络断了" in tasks[1].detail


def test_unexpected_exception_is_isolated():
    def reply(prompt: str):
        if "bbb" in prompt:
            raise RuntimeError("boom")
        return _reply_for(prompt)

    tasks, text = _three_tasks()
    result = run_parallel(
        tasks,
        FakeProvider(reply),
        text=text,
        timeout=1.0,
        syntax_checker=_null_checker,
        max_concurrency=3,
    )
    assert len(result.done) == 2
    assert "意外错误" in tasks[1].detail


def test_rate_limit_backoff_sequence_and_floor_serial():
    """并发=1 时退避序列完全确定：1,2,4,8,16,30（上限）；最后一次失败不再退避。"""
    tasks, text = _three_tasks()
    tasks = tasks[:1]
    delays: list[float] = []
    provider = FakeProvider(lambda _p: ProviderRateLimitError("429"))
    result = run_parallel(
        tasks,
        provider,
        text=text,
        timeout=1.0,
        syntax_checker=_null_checker,
        sleep=delays.append,
        jitter=lambda: 1.0,
        max_concurrency=1,
        rate_limit_retries=6,
    )
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]
    assert result.final_concurrency == 1
    assert result.rate_limit_hits == 7
    assert tasks[0].retries == 6
    assert tasks[0].status == STATUS_FAILED


def test_rate_limit_shrinks_concurrency_within_bounds():
    tasks, text = _three_tasks()
    delays: list[float] = []
    provider = FakeProvider(lambda _p: ProviderRateLimitError("429"))
    result = run_parallel(
        tasks,
        provider,
        text=text,
        timeout=1.0,
        syntax_checker=_null_checker,
        sleep=delays.append,
        jitter=lambda: 1.0,
        max_concurrency=3,
        rate_limit_retries=1,
    )
    assert result.rate_limit_hits == 6
    assert result.final_concurrency == 1
    assert 1 <= result.final_concurrency <= 3
    assert all(RATE_LIMIT_BACKOFF_BASE <= d <= RATE_LIMIT_BACKOFF_CAP for d in delays)


def test_rate_limit_callback_reported_by_provider():
    provider = FakeProvider(lambda _p: ProviderRateLimitError("429"), report_rate_limit=True)
    tasks, text = _three_tasks()
    result = run_parallel(
        tasks[:1],
        provider,
        text=text,
        timeout=1.0,
        syntax_checker=_null_checker,
        sleep=lambda _s: None,
        jitter=lambda: 1.0,
        max_concurrency=3,
        rate_limit_retries=0,
    )
    assert result.rate_limit_hits == 1
    assert result.final_concurrency == 2


def test_server_error_does_not_shrink_concurrency():
    tasks, text = _three_tasks()
    result = run_parallel(
        tasks,
        FakeProvider(lambda _p: ProviderServerError("500")),
        text=text,
        timeout=1.0,
        syntax_checker=_null_checker,
        sleep=lambda _s: None,
        max_concurrency=3,
    )
    assert result.rate_limit_hits == 0
    assert result.final_concurrency == 3
    assert len(result.failed) == 3


# ---------------------------------------------------------------------------
# 面板事件 / 取消
# ---------------------------------------------------------------------------


def test_events_cover_running_chunks_and_terminal_status():
    tasks, text = _three_tasks()
    events, on_event = _collect()
    run_parallel(
        tasks,
        FakeProvider(lambda _p: ["echo part1", "echo part2"]),
        text=text,
        timeout=1.0,
        syntax_checker=_null_checker,
        on_event=on_event,
        max_concurrency=2,
    )
    assert all(e.status == STATUS_RUNNING for e in events if e.chunk)
    assert [e.chunk for e in events if e.chunk]
    terminal = [e for e in events if not e.chunk and e.status in (STATUS_DONE, STATUS_FAILED)]
    assert len(terminal) == 3
    assert {e.index for e in terminal} == {1, 2, 3}


def test_cancel_event_marks_pending_as_skipped():
    tasks, text = _three_tasks()
    cancel = threading.Event()
    cancel.set()
    result = run_parallel(
        tasks,
        FakeProvider(),
        text=text,
        timeout=1.0,
        syntax_checker=_null_checker,
        max_concurrency=3,
        cancel_event=cancel,
    )
    assert len(result.skipped) == 3
    assert all(t.detail == "已取消" for t in tasks)
    assert result.final_concurrency == 3
