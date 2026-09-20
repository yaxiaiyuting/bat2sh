"""明文 HTTP 可达性探针（Phase 2 第 0 步，阻断验证）。

问题：targetSdk 28 下 Android 的 `usesCleartextTraffic` 默认为 false，
而 Flet 不暴露该开关（生成的 manifest 里没有这个属性）。
但 Android 的 cleartext 限制是在 **Java 框架层**执行的
（NetworkSecurityPolicy，由 HttpURLConnection / OkHttp / WebView / Cronet 主动查询），
而 core/api/provider.py 走的是 urllib.request -> CPython socket -> 原生 socket 系统调用，
**不经过 Java 网络栈**。所以两种可能都存在，必须实测。

本探针用与 provider.py **完全相同**的调用栈（urllib.request）发请求：
  1. http://127.0.0.1:PORT/probe          经 adb reverse 打到 host（纯明文）
  2. http://10.0.2.2:PORT/probe           模拟器到 host 的别名（纯明文）
  3. POST http://127.0.0.1:PORT/chat/completions  复刻 provider.py 的 SSE 形态
  4. https://example.com/                 HTTPS 对照组（应当永远可用）

结果同时进 UI 与 stdout（logcat tag flet.python）。
"""

from __future__ import annotations

import json
import threading
import time
import traceback
import urllib.error
import urllib.request

import flet as ft

PORT = 8731
TIMEOUT = 8.0

RESULTS: list[tuple[str, bool, str]] = []


def _try(label: str, url: str, data: bytes | None = None, headers: dict | None = None) -> None:
    """发一个请求并记录结果。异常类型与原文都保留 —— 判定依据就是这个。"""
    started = time.time()
    try:
        req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(200)
            ms = (time.time() - started) * 1000
            RESULTS.append((label, True, f"HTTP {resp.status} ({ms:.0f}ms) body={body[:80]!r}"))
    except Exception as exc:  # noqa: BLE001
        ms = (time.time() - started) * 1000
        detail = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, urllib.error.HTTPError):
            # HTTP 错误码说明 socket 层是通的 —— 依然算「明文可达」
            RESULTS.append((label, True, f"HTTP {exc.code}（socket 可达，仅业务码非 2xx）({ms:.0f}ms)"))
            return
        RESULTS.append((label, False, f"{detail} ({ms:.0f}ms)"))


def run_probes() -> None:
    print("=" * 66, flush=True)
    print("CLEARTEXT PROBE START (targetSdk 28, urllib.request)", flush=True)

    _try("1. http 127.0.0.1 (adb reverse)", f"http://127.0.0.1:{PORT}/probe")
    _try("2. http 10.0.2.2 (host alias)", f"http://10.0.2.2:{PORT}/probe")
    payload = json.dumps({
        "model": "probe", "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0, "stream": True,
    }).encode("utf-8")
    _try("3. POST http /chat/completions", f"http://127.0.0.1:{PORT}/chat/completions",
         data=payload, headers={"Content-Type": "application/json"})
    _try("4. https example.com (control)", "https://example.com/")

    print("-" * 66, flush=True)
    cleartext_ok = False
    for label, ok, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label}: {detail}", flush=True)
        if ok and ("http " in label or "POST http" in label):
            cleartext_ok = True
    print("-" * 66, flush=True)
    print(f"VERDICT: cleartext_http={'REACHABLE' if cleartext_ok else 'BLOCKED'}", flush=True)
    print("CLEARTEXT PROBE END", flush=True)
    print("=" * 66, flush=True)


def main(page: ft.Page) -> None:
    page.title = "cleartext probe"
    status = ft.Text("probing...", selectable=True, font_family="monospace", size=12)
    page.add(ft.Column([status], scroll=ft.ScrollMode.AUTO, expand=True))

    def work() -> None:
        time.sleep(1.0)  # 给 logcat 一点时间挂上
        try:
            run_probes()
        except Exception:  # noqa: BLE001
            print("PROBE CRASHED:\n" + traceback.format_exc(), flush=True)
        text = "\n".join(f"[{'PASS' if ok else 'FAIL'}] {lbl}\n    {d}" for lbl, ok, d in RESULTS)
        status.value = text or "(no results)"
        try:
            page.update()
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=work, daemon=True).start()


ft.run(main)
