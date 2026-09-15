"""TODO 并行修复编排（v1.7.0 C 阶段）。

设计依据 ``docs/v1.7.0-design.md``：
- §3 线程池 + 可收缩限流器（不用 ``ThreadPoolExecutor``，因其无法安全降并发）；
- §4 429 指数退避 + 主动降并发（下限 1、上限 = 初始并发）；
- §5 全部收完 → 从后往前合并（out_line 降序）+ 逐级 ``bash -n`` 闸门；
- §7 接口契约。

纯标准库；不导入 GUI；不直接调用 bash（语法校验经 ``syntax_checker`` 注入，
默认 ``bash_syntax_error``，测试可注入以提速）。``on_event`` 由多个工作线程触发，
本模块用内部锁串行化，消费者无需自带锁。

已知限制（见设计文档 §7.2）：阻塞中的 socket 读无法被其它线程打断，取消/中断在
最坏情况下要等到当前空闲超时（默认 30s）才完全生效；工作线程为 daemon，保证进程可退出。
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from ..syntax import bash_syntax_error
from .fixer import TodoMarker, apply_replacement, build_prompt, clean_completion
from .provider import ProviderError, ProviderRateLimitError

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

DEFAULT_MAX_CONCURRENCY = 3
MIN_MAX_CONCURRENCY = 1
MAX_MAX_CONCURRENCY = 16
RATE_LIMIT_BACKOFF_BASE = 1.0
RATE_LIMIT_BACKOFF_CAP = 30.0
RATE_LIMIT_RETRIES = 2
_CANCEL_POLL_SECONDS = 0.2

SyntaxChecker = Callable[[str], str | None]


@dataclass
class FixTask:
    """一条待修复 TODO（并行任务单元）。

    ``out_line`` 在扫描时**冻结**：并行路径下所有 prompt 都基于同一份原始脚本构造，
    不存在顺序处理的行号漂移（对比 v1.6 串行路径的 offset）。
    """

    index: int
    marker: TodoMarker
    out_line: int
    prompt: str
    status: str = STATUS_PENDING
    replacement: str = ""
    detail: str = ""
    rate_limit_hits: int = 0
    retries: int = 0


@dataclass
class FixEvent:
    """面板事件：状态迁移或流式正文块。"""

    index: int
    status: str
    detail: str = ""
    chunk: str = ""


@dataclass
class ParallelResult:
    tasks: list[FixTask]
    rate_limit_hits: int
    final_concurrency: int

    def _with_status(self, status: str) -> list[FixTask]:
        return [t for t in self.tasks if t.status == status]

    @property
    def done(self) -> list[FixTask]:
        return self._with_status(STATUS_DONE)

    @property
    def failed(self) -> list[FixTask]:
        return self._with_status(STATUS_FAILED)

    @property
    def skipped(self) -> list[FixTask]:
        return self._with_status(STATUS_SKIPPED)


def plan_tasks(
    markers: Sequence[TodoMarker],
    source_text: str,
    source_name: str,
    output_text: str,
    context_lines: int,
) -> list[FixTask]:
    """为每个标记冻结 ``out_line`` 并构造 prompt；同一行只保留首个（防御性去重）。"""
    tasks: list[FixTask] = []
    seen: set[int] = set()
    for marker in markers:
        if marker.out_line in seen:
            continue
        seen.add(marker.out_line)
        tasks.append(
            FixTask(
                index=len(tasks) + 1,
                marker=marker,
                out_line=marker.out_line,
                prompt=build_prompt(
                    marker,
                    source_text,
                    source_name,
                    output_text,
                    context_lines,
                    out_line=marker.out_line,
                ),
            )
        )
    return tasks


def evaluate_reply(
    task: FixTask, raw: str, text: str, *, syntax_checker: SyntaxChecker = bash_syntax_error
) -> None:
    """把模型回复落到 ``task``（就地修改 status/replacement/detail）。

    - 空回复 / 含 ``# TODO`` / 与原文行相同 → ``skipped``（模型未给出可用修改）；
    - 单条替换后未通过语法闸门 → ``failed``；
    - 其余 → ``done``。
    """
    replacement = clean_completion(raw)
    if (
        not replacement
        or "# TODO" in replacement
        or replacement.strip() == task.marker.line_text.strip()
    ):
        task.status = STATUS_SKIPPED
        task.detail = "模型未给出可用修改"
        return
    try:
        candidate = apply_replacement(text, task.out_line, replacement)
    except ValueError as exc:
        task.status = STATUS_FAILED
        task.detail = f"行号越界（第 {task.out_line} 行）：{exc}"
        return
    problem = syntax_checker(candidate)
    if problem:
        task.status = STATUS_FAILED
        task.detail = f"建议未通过 bash -n：{problem}"
        return
    task.replacement = replacement
    task.status = STATUS_DONE
    task.detail = ""


def merge_replacements(
    text: str, tasks: Sequence[FixTask], *, syntax_checker: SyntaxChecker = bash_syntax_error
) -> tuple[str, list[FixTask]]:
    """仅合并 ``done`` 条目：按 ``out_line`` **降序**应用，每步过语法闸门。

    降序保证已应用的修改都在更大的行号上（即文件更下方），不会改变待处理行号；
    逐步 ``bash -n`` 保证最终产物一定通过校验（失败条目标记 ``failed`` 后跳过，不阻塞其余）。
    """
    accepted = sorted(
        (t for t in tasks if t.status == STATUS_DONE and t.replacement),
        key=lambda t: t.out_line,
        reverse=True,
    )
    current = text
    dropped: list[FixTask] = []
    for task in accepted:
        try:
            candidate = apply_replacement(current, task.out_line, task.replacement)
        except ValueError as exc:
            task.status = STATUS_FAILED
            task.detail = f"合并失败（行号越界）：{exc}"
            dropped.append(task)
            continue
        problem = syntax_checker(candidate)
        if problem:
            task.status = STATUS_FAILED
            task.detail = f"合并后未通过 bash -n：{problem}"
            dropped.append(task)
            continue
        current = candidate
    return current, dropped


def format_status_line(task: FixTask) -> str:
    """面板单行文本（CLI/GUI 在此之上自行加装饰）。"""
    line = f"#{task.index} 第{task.out_line}行 {task.status}"
    return f"{line}：{task.detail}" if task.detail else line


def _backoff_delay(consecutive: int) -> float:
    """指数退避：首次 1×BASE，其后 2×、4×…，上限 CAP。"""
    return min(
        RATE_LIMIT_BACKOFF_CAP,
        RATE_LIMIT_BACKOFF_BASE * (2 ** max(0, consecutive - 1)),
    )


class _AdaptiveLimiter:
    """可收缩限流器：只降不升，在途请求从不被打断（仅节流后续派发）。"""

    def __init__(self, limit: int) -> None:
        self._limit = max(MIN_MAX_CONCURRENCY, int(limit))
        self._inflight = 0
        self._cond = threading.Condition()

    @property
    def limit(self) -> int:
        with self._cond:
            return self._limit

    def acquire(self, should_stop: Callable[[], bool]) -> bool:
        with self._cond:
            while self._inflight >= self._limit:
                if should_stop():
                    return False
                self._cond.wait(timeout=_CANCEL_POLL_SECONDS)
            if should_stop():
                return False
            self._inflight += 1
            return True

    def release(self) -> None:
        with self._cond:
            self._inflight -= 1
            self._cond.notify_all()

    def shrink(self) -> bool:
        """降 1（下限 1）；已在下限返回 False。"""
        with self._cond:
            if self._limit <= MIN_MAX_CONCURRENCY:
                return False
            self._limit -= 1
            return True


class _Scheduler:
    """任务派发：队列空但仍有在途任务时等待，避免工作线程提前退出而漏掉重试任务。"""

    def __init__(self, tasks: Sequence[FixTask]) -> None:
        self._cond = threading.Condition()
        self._queue = list(tasks)
        self._active = 0
        self._done = 0
        self._total = len(tasks)

    def next_task(self, should_stop: Callable[[], bool]) -> FixTask | None:
        with self._cond:
            while not self._queue and self._active > 0 and self._done < self._total:
                if should_stop():
                    return None
                self._cond.wait(timeout=_CANCEL_POLL_SECONDS)
            if not self._queue or should_stop():
                return None
            task = self._queue.pop(0)
            self._active += 1
            return task

    def finish(self, task: FixTask, requeue: bool) -> None:
        with self._cond:
            self._active -= 1
            if requeue:
                self._queue.append(task)
            else:
                self._done += 1
            self._cond.notify_all()

    def queued(self) -> list[FixTask]:
        with self._cond:
            return list(self._queue)


def run_parallel(
    tasks: Sequence[FixTask],
    provider,
    *,
    text: str,
    timeout: float,
    syntax_checker: SyntaxChecker = bash_syntax_error,
    on_event: Callable[[FixEvent], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    rate_limit_retries: int = RATE_LIMIT_RETRIES,
    cancel_event: threading.Event | None = None,
) -> ParallelResult:
    """并发执行全部任务：限流器 + 429 退避降并发 + 错误隔离。

    ``sleep`` / ``jitter`` 可注入（测试免等待）；``cancel_event`` 由调用方提供时用于
    外部取消（GUI 停止按钮），否则内部创建并响应 ``KeyboardInterrupt``。
    """
    tasks = list(tasks)
    initial = min(MAX_MAX_CONCURRENCY, max(MIN_MAX_CONCURRENCY, int(max_concurrency)))
    limiter = _AdaptiveLimiter(initial)
    scheduler = _Scheduler(tasks)
    event_lock = threading.Lock()
    cancel = cancel_event if cancel_event is not None else threading.Event()
    stats = {"rate_limit_hits": 0, "consecutive": 0}
    stats_lock = threading.Lock()

    def should_stop() -> bool:
        return cancel.is_set()

    def emit(event: FixEvent) -> None:
        if on_event is None:
            return
        with event_lock:
            on_event(event)

    def set_status(task: FixTask, status: str, detail: str = "") -> None:
        task.status = status
        task.detail = detail
        emit(FixEvent(task.index, status, detail))

    def note_rate_limit(task: FixTask, label: str) -> None:
        with stats_lock:
            stats["rate_limit_hits"] += 1
            stats["consecutive"] += 1
        limiter.shrink()
        emit(FixEvent(task.index, STATUS_RUNNING, f"{label}：并发降至 {limiter.limit}"))

    def execute(task: FixTask) -> bool:
        """返回 True 表示需要重新入队（429 退避重试）。就地修改 task。"""
        hits_seen = 0

        def on_rate_limit(hits: int) -> None:
            nonlocal hits_seen
            hits_seen = max(hits_seen, hits)
            note_rate_limit(task, f"限流 429（第 {hits} 次）")

        def on_reasoning(count: int) -> None:
            emit(FixEvent(task.index, STATUS_RUNNING, f"思考中（思维链 {count} 段）"))

        def on_warning(message: str) -> None:
            emit(FixEvent(task.index, STATUS_RUNNING, f"警告：{message}"))

        set_status(task, STATUS_RUNNING)
        stream = None
        chunks: list[str] = []
        try:
            stream = provider.complete_stream(
                task.prompt,
                timeout=timeout,
                on_reasoning=on_reasoning,
                on_warning=on_warning,
                on_rate_limit=on_rate_limit,
            )
            for chunk in stream:
                if cancel.is_set():
                    break
                chunks.append(chunk)
                emit(FixEvent(task.index, STATUS_RUNNING, "", chunk))
        except ProviderRateLimitError as exc:
            task.rate_limit_hits += 1
            if hits_seen == 0:  # provider 未上报（如注入的假实现）时补记一次
                note_rate_limit(task, "限流 429")
            if task.retries < rate_limit_retries and not cancel.is_set():
                task.retries += 1
                with stats_lock:
                    consecutive = stats["consecutive"]
                delay = _backoff_delay(consecutive)
                sleep(delay * jitter())
                set_status(task, STATUS_PENDING, f"限流退避 {delay:g}s 后重试")
                return True
            set_status(task, STATUS_FAILED, f"限流 429（重试 {task.retries} 次后仍失败）：{exc}")
            return False
        except ProviderError as exc:
            if cancel.is_set():
                set_status(task, STATUS_SKIPPED, "已取消")
                return False
            set_status(task, STATUS_FAILED, f"API 调用失败：{exc}")
            return False
        except Exception as exc:  # 单任务意外异常不得阻塞其余任务（错误隔离）
            if cancel.is_set():
                set_status(task, STATUS_SKIPPED, "已取消")
                return False
            set_status(task, STATUS_FAILED, f"意外错误：{exc}")
            return False
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()

        if cancel.is_set():
            set_status(task, STATUS_SKIPPED, "已取消")
            return False
        with stats_lock:
            stats["consecutive"] = 0
        try:
            evaluate_reply(task, "".join(chunks), text, syntax_checker=syntax_checker)
        except Exception as exc:  # 校验/替换阶段的意外异常同样只影响本条
            set_status(task, STATUS_FAILED, f"评估建议失败：{exc}")
            return False
        emit(FixEvent(task.index, task.status, task.detail))
        return False

    def worker() -> None:
        while not cancel.is_set():
            if not limiter.acquire(should_stop):
                return
            if cancel.is_set():
                limiter.release()
                return
            task = scheduler.next_task(should_stop)
            if task is None:
                limiter.release()
                return
            requeue = False
            try:
                requeue = execute(task)
            finally:
                limiter.release()
                scheduler.finish(task, requeue)

    threads = [
        threading.Thread(target=worker, name=f"bat2sh-fix-{i}", daemon=True)
        for i in range(initial)
    ]
    for thread in threads:
        thread.start()
    interrupted = False
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        interrupted = True
        cancel.set()
        cancel_in_flight = getattr(provider, "cancel_in_flight", None)
        if callable(cancel_in_flight):
            cancel_in_flight()
        for thread in threads:
            thread.join(timeout=2.0)

    for task in scheduler.queued():
        if task.status == STATUS_PENDING:
            set_status(task, STATUS_SKIPPED, "已取消")

    with stats_lock:
        hits = stats["rate_limit_hits"]
    if interrupted:
        raise KeyboardInterrupt
    return ParallelResult(tasks=tasks, rate_limit_hits=hits, final_concurrency=limiter.limit)
