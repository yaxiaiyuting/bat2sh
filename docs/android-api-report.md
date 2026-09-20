# bat2sh Android —— API 修复（含并行）实现报告

> 会话：Android API Phase 2。分支 `android-api`；起点 HEAD（锁定）= `c476e5e`。
> 前置：Phase 1 只读评估 `docs/android-api-assessment.md`（用户已确认其 3 个问题）。
>
> **未合并 main、未 bump 版本、未打 tag。**

---

## 0. 结论摘要

| 项 | 结果 |
| :--- | :--- |
| **第 0 步：明文 HTTP 探针（阻断项）** | ✅ **REACHABLE** —— 4/4 探针 HTTP 200，**无需任何 manifest 补救** |
| API 设置 UI | ✅ endpoint / key / model / enable_thinking / max_concurrency（+ timeout） |
| 并行修复（默认并发 3） | ✅ 复用 `core/api/parallel.py`，**core 零改动** |
| **并行 UI 方案** | ✅ **方案 B（可展开列表）** + 自动展开首条 + 按需渲染 |
| 逐 chunk 流式显示 | ✅ 实机验证（含展开补齐） |
| 错误隔离 | ✅ 实机验证：1 条失败不阻塞另 1 条 |
| 单条重试 | ✅ 实机验证：失败条目重试后转 ✓ 完成 |
| 聚合 diff → 确认 → 应用 | ✅ 实机验证：应用后重新 `bash -n` = PASS |
| **语法闸门注入** | ✅ `run_parallel` 与 `merge_replacements` 两处都注入 Termux 版 |
| `python/bat2sh/core/` | ✅ **零改动（diff = 0 行）** |
| 交付 APK | `packaging/android/build/apk/bat2sh-android-arm64-v8a.apk`（**87,247,863 B**，sha256 `525ebdce…1cd9`） |
| 构建/验证设备 | Android 14（API 34）x86_64 模拟器 `poc34`（`emulator-5554`） |

**一句话**：`core/api/` 四个模块原样复用，Python 侧**零改动**；Flet 侧新增
`api_bridge.py`（桥 + Termux 语法闸门）与 `ui/api_panel.py`（设置 + 方案 B 并行面板），
把「工作线程 → 队列 → 事件循环批量刷新」这条 Phase 1 实测出来的通道落地；
在真机上跑通了 **转换 → 隐私确认 → 并行流式修复 → 错误隔离 → 单条重试 → 聚合 diff → 应用 → `bash -n`** 全链路。

---

## 1. 第 0 步（阻断验证）：明文 HTTP 探针

### 1.1 背景

Phase 1 §4.3.3 发现：targetSdk 28 时 `android:usesCleartextTraffic` 默认 **false**，
而 Flet 不暴露该开关，生成的 manifest 里也确实没有这个属性。
若 Android 真的拦明文，`http://192.168.x.x:11434/v1`（Ollama / LM Studio / vLLM 的默认形态）就不可用。

但有一个反向论据：Android 的 cleartext 限制在 **Java 框架层**执行
（`NetworkSecurityPolicy`，由 `HttpURLConnection` / OkHttp / WebView / Cronet 主动查询），
**不是内核级封锁**；而 `provider.py` 走的是 `urllib.request` → CPython `socket` → 原生 socket，
**不经过 Java 网络栈**。

**结论不能靠推理定案，必须实测。**

### 1.2 仪器

`packaging/android/probe-cleartext/` —— 一个独立的极小 Flet 工程
（`target_sdk_version = 28`，与正式工程一致），用与 `provider.py` **完全相同**的
`urllib.request` 调用栈发 4 个请求：

| # | 探针 | 目的 |
| :--- | :--- | :--- |
| 1 | `GET http://127.0.0.1:8731/probe`（经 `adb reverse` 打到 host） | 纯明文 HTTP |
| 2 | `GET http://10.0.2.2:8731/probe`（模拟器到 host 的别名） | 纯明文 HTTP，非 loopback 语义 |
| 3 | `POST http://127.0.0.1:8731/chat/completions`（`stream:true`） | 复刻 provider.py 的 SSE 形态 |
| 4 | `GET https://example.com/` | HTTPS 对照组 |

host 侧 `/tmp/p2-smoke/http_server.py` 记录每一条到达的请求，用来证明请求**真的从设备打到了 host**。

### 1.3 实机结果（`emulator-5554`，logcat tag `flet.python`）

```
CLEARTEXT PROBE START (targetSdk 28, urllib.request)
  [PASS] 1. http 127.0.0.1 (adb reverse): HTTP 200 (18ms) body=b'cleartext-ok'
  [PASS] 2. http 10.0.2.2 (host alias): HTTP 200 (943ms) body=b'cleartext-ok'
  [PASS] 3. POST http /chat/completions: HTTP 200 (153ms) body=b'data: {"choices": [{"delta": {"content": "echo "}}]}...'
  [PASS] 4. https example.com (control): HTTP 200 (1624ms) body=b'<!doctype html>...'
VERDICT: cleartext_http=REACHABLE
```

host 侧同步记录到 3 条来自设备的请求（12:45:34–35），与 logcat 时间戳对齐：

```
[host 12:45:34] "GET /probe HTTP/1.1" 200 -
[host 12:45:35] "GET /probe HTTP/1.1" 200 -
[host 12:45:35] "POST /chat/completions HTTP/1.1" 200 -
```

### 1.4 判定

> ✅ **明文 HTTP 可达。Phase 1 的反向论据成立：Android 的 cleartext 策略在 Java 框架层，
> CPython 的原生 socket 不受其约束。**
>
> **因此不需要 `--template-dir` 或任何 manifest 补救**，本地 `http://` 端点
> （Ollama / LM Studio / vLLM / llama.cpp server）可直接使用。
> §4.3.3 的隐患**关闭**，且是「实测证明不存在」而不是「绕过去了」。

---

## 2. 交付物

### 2.1 APK

| 项 | 值 |
| :--- | :--- |
| 路径 | `packaging/android/build/apk/bat2sh-android-arm64-v8a.apk` |
| 大小 | **87,247,863 字节**（83.2 MiB） |
| sha256 | `525ebdce5df3edf7d319c8da822e68bb0da625d018abdb874ad3cc6597311cd9` |
| ABI | arm64-v8a（含 `lib/arm64-v8a/*` 与 `assets/app.zip` 内的 `assets/bootstrap-aarch64.zip`） |
| targetSdk | 28 |
| 包名 / versionName | `io.github.bat2sh_android` / 2.8.1（**未 bump**） |
| 签名 | debug 签名 |

**验证过的内容**（`aapt2` + `unzip`）：

```
package="io.github.bat2sh_android"   targetSdkVersion=28
uses-permission android.permission.INTERNET   ← 显式声明 + Flet 默认，二者一致
lib/arm64-v8a/libpython3.14.so / libflutter.so / libapp.so ...
assets/app.zip  →  内含 assets/bootstrap-aarch64.zip，且**不含** x86_64 那份
```

> ⚠️ **构建顺序很重要**：`flet build` 会清空 `build/apk/`，所以 **arm64 必须是最后一次构建**，
> 否则交付文件会被后续的 x86_64 构建删掉（本次实际踩到过一次）。
> 交付前已确认 `build/apk/bat2sh-android-arm64-v8a.apk` 存在且 sha256 如上行。
>
> 另：arm64 曾有一次构建在 Gradle 阶段失败（`Doctor found issues in 2 categories`），
> **原样重跑即成功** —— 属代理瞬时抖动，非代码或配置缺陷（本 session 之前也出现过同类抖动）。
> 交付大小/sha256 以本文件为准；凡代码改动后重新构建，sha256 都会变。

### 2.2 代码（`packaging/android/`）

| 文件 | 状态 | 行数 | 说明 |
| :--- | :--- | ---: | :--- |
| `pyproject.toml` | 修改 | 27 | 新增 `[tool.flet.android.permission]` 显式声明 INTERNET |
| `src/main.py` | 修改 | 46 | **首条语句**注入 `XDG_CONFIG_HOME`（早于一切 core import） |
| `src/api_bridge.py` | **新增** | 232 | core 桥：配置读写 / provider / **Termux 语法闸门** / 编排封装 |
| `src/ui/api_panel.py` | **新增** | 556 | 设置对话框 + 隐私对话框 + `FixJob` + **方案 B 并行面板** |
| `src/ui/app.py` | 修改 | 519 | `UiPump` 线程纪律 + 按钮/面板接入 + 应用后回写与复检 |
| `probe-cleartext/` | **新增** | — | 第 0 步探针工程（独立 Flet 项目） |

**`python/bat2sh/core/`：`git diff` = 0 行。** 纪律 1 满足。

### 2.3 文档

- `docs/android-api-assessment.md`（Phase 1，已提交于 `ec5e507`）
- 本文件

---

## 3. 实现说明

### 3.1 配置路径：Flet 层注入，core 零改动

`main.py` 最前面（早于 `import flet` 与 `import ui.app`）：

```python
_storage = os.environ.get("FLET_APP_STORAGE_DATA")
if _storage:
    os.environ["XDG_CONFIG_HOME"] = os.path.join(_storage, "config")
```

Android 实际落点：`/data/user/0/io.github.bat2sh_android/files/data/config/bat2sh/api.json`。
仅当 `FLET_APP_STORAGE_DATA` 存在（= 跑在 Flet 容器里）才覆盖，
这样桌面 smoke test 仍读用户真实的 `~/.config/bat2sh/api.json`。

**实机确认**（logcat）：`API 配置：endpoint=http://127.0.0.1:8731/v1  model=fake-model  key=已设置(17 字符)  并发=3  思考=关  超时=60s`

### 3.2 ★ 语法闸门注入（评估 §4.4.4 的落实）

core 默认的 `bash_syntax_error` 在 `shutil.which("bash")` 为 None 时 **`return None`（判通过）**。
Android 上 Termux 的 bash 不在 PATH，于是每一处「建议未通过 `bash -n`」的闸门都会
**静默假通过** —— 坏的合并会被写进产物且用户看不到任何错误。

`api_bridge.make_syntax_checker(tx)` 把它换掉，契约不变（`None`=通过，字符串=失败原因），
但**「未执行」一律判失败**：

```python
def checker(script: str) -> str | None:
    if not tx.ready:
        return "无法执行 bash -n：Termux 运行时不可用"
    probe = Path(tx.work) / _SYNTAX_PROBE_NAME
    tx.prepare_dirs(); probe.write_text(script, encoding="utf-8")
    checked, ok, message = tx.syntax_check(probe)
    if not checked:
        return "无法执行 bash -n（%s）" % message     # ← 未执行 = 失败，不是通过
    return None if ok else message
```

**同时注入两处**（`grep -c` 各命中 2 次）：

- `api_bridge.run_parallel(..., syntax_checker=...)` → 逐条建议的闸门
- `api_bridge.merge_replacements(..., syntax_checker=...)` → 合并阶段的闸门

**实机自检证据**（每次启动都跑，用户可自行复现）：

```
[13:00:xx] 语法闸门自检：合法脚本=通过，非法脚本=检出错误
```

即：合法脚本判通过（不会误杀），非法脚本（`if true; then` 未闭合）**真的被检出** ——
证明闸门在设备上确实执行了 `bash -n`，而不是假通过。

### 3.3 ★ 刷新节流：工作线程只入队，事件循环批量刷新

`ui/api_panel.py::FixJob` 是纪律「禁止工作线程直接 `page.update()`」的唯一落点：

```python
def worker() -> None:                      # 跑在 page.run_thread 的线程里
    self._result = api_bridge.run_parallel(
        ..., on_event=q.put, ...)          # ← 只入队，绝不碰 UI
    ...
self.page.run_thread(worker)
self.page.run_task(self._drain)            # ← 唯一的 UI 刷新协程

async def _drain(self):                    # 跑在 page 的事件循环里
    while True:
        batch = []                         # 把队列里已到达的全部吃掉
        while True:
            try: batch.append(self._q.get_nowait())
            except queue.Empty: break
        if batch:
            self._on_events(batch)         # 只改控件值
            self.page.update()             # 每轮只 update 一次
        if self._finished.is_set() and self._q.empty(): break
        await asyncio.sleep(0.02)
```

- 终止条件安全：所有事件都在 `run_parallel` 返回（= 所有工作线程 join 完）之后才 `_finished.set()`，
  故「已结束且队列空」⟺ 全部消费完。
- 轮询 20 ms ≈ 50 fps 上限；Phase 1 实测批量比 ≈28:1。

同一纪律也应用到了既有的日志路径：`app.py` 新增 `UiPump`，
把 `_say` / `_log` / `_show_script` 从「后台线程直接 `page.update()`」改为
「投递闭包 → 单个 drainer 协程批量执行」。
这顺带消掉了一个真实隐患：**「转换」线程与并行 drainer 可能同时在改控件树**。

### 3.4 并行 UI：方案 B（可展开列表）

```
┌────────────────────────────────────────────┐
│ AI 并行修复            1/2 完成 · 1 失败     │  ← 聚合计数（始终显示全部）
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓          │  ← ft.ProgressBar
│ 共 2 条：完成 1 / 失败 1 / 跳过 0             │  ← 汇总（基于全部任务）
├────────────────────────────────────────────┤
│ ✓  #1 第 6 行                        ⌃      │  ← 自动展开首条 running
│    ✓ 完成                                   │
│    ┌──────────────────────────────────────┐│
│    │ echo "AI 修复建议 #1：原命令需人工确认" ││  ← 仅在展开时渲染
│    └──────────────────────────────────────┘│
│ ✗  #2 第 7 行                        ⌄      │
│    ✗ 失败：API 调用失败：服务端错误（HTTP 500）│
├────────────────────────────────────────────┤
│ [应用全部]  [取消]                           │
└────────────────────────────────────────────┘
```

三处针对手机的实现要点：

1. **按需渲染**：折叠行只更新一行短字符串（状态 + 详情）；
   流式正文只写进**被展开的那一条**的控件，展开时一次性补齐缓冲
   （`_on_expand` → `streams[idx].value = buffers[idx]`）。
   实测断言：「只有展开行渲染了流式正文」。
2. **自动展开首条 running**：用户一按就能看到流式反馈（满足「逐 chunk 流式显示」的直观要求）；
   之后**不再自动切换**，避免抢走用户正在读的那条。
3. **失败条目就近重试**：`重试这一条` 按钮只在 `failed` 条目上出现，
   单条重跑复用同一套编排（并发 1），错误隔离语义不变。

**聚合应用**：`应用全部` → `merge_replacements`（带 Termux 闸门）→ `fixer.render_diff`
→ `AlertDialog` 展示 diff 并提示被丢弃的条数 → 确认 → 回写产物区 → **重新 `bash -n`** → `runner.stage()` 落盘。

### 3.5 API key 纪律（纪律 6）

| 要求 | 落实 |
| :--- | :--- |
| 不写日志 | `api_bridge.describe()` 只报「已设置(N 字符)」/「未设置」，**绝不回显 key**；实机 logcat 已确认 |
| 界面遮蔽 | 设置对话框用 `password=True, can_reveal_password=True` |
| 错误路径 | `api_bridge.safe_error(msg, cfg)` 统一过 `provider.redact`；`FixJob` 的异常、设置保存失败、合并失败全部经它 |
| 不进 prompt | `build_prompt()` 本身不含 key（已核对）；smoke test 断言「prompt 不含 API key」 |

---

## 4. 验证

### 4.1 桌面 smoke test（构建前先排低级错误）

**A. `api_bridge` 逻辑**（`/tmp/p2-smoke/smoke_bridge.py`）—— 全部通过：

```
[PASS] 配置路径跟随 FLET_APP_STORAGE_DATA -> /tmp/.../config/bat2sh/api.json
[PASS] roundtrip base_url/model / key / max_concurrency,timeout,thinking
[PASS] 文件权限 0600        [PASS] missing_requirements 为空
[PASS] describe() 不含 key 本体        [PASS] safe_error() 把 key 抹成 ***
[PASS] ★ Termux 不可用时返回失败字符串（不是 None）
[PASS] 真实语料 registry-and-wmic.bat -> 3 条 TODO -> plan_tasks 3 条
[PASS] run_parallel：完成 2 / 失败 1（错误隔离）
[PASS] 闸门拒绝时全部 failed        [PASS] merge 改动文本 + diff 非空
```

**B. `ParallelPanel` 跑在真实 Flet 页面上**（`/tmp/p2-smoke/smoke_panel.py`）—— 全部通过：

```
[PASS] begin 后行数 / 计数文案 / 进度条 / 按钮状态
[PASS] 错误隔离：2 done + 1 failed
[PASS] 自动展开了第一条 running 条目 -> expanded=[1]
[PASS] 只有展开行渲染了流式正文（按需渲染） -> 已写入=[1] 展开=[1]
[PASS] 展开后补齐了流式正文（缓冲与控件一致，150 vs 150 字符）
[PASS] 失败条目「重试」可见 / 完成条目「重试」隐藏
[PASS] 汇总基于全部任务（不因单条重试退化）
[PASS] ★ 无工作线程直接 page.update() -> 共 15 次 update，越界 0 次
```

最后一项是**给 `page.update` 装探针、记录每次调用的线程 ident** 得到的：
15 次刷新**全部**来自事件循环线程，工作线程 0 次 —— 纪律 4.2 由仪器守住，不靠自觉。

### 4.2 模拟器实机（`emulator-5554`，Android 14 / x86_64）

链路：`adb install` → 启动自检 → 手输 `.bat` → 转换 → 并行修复 → 展开/重试 → 应用。

| # | 观察点 | 实机结果 |
| :--- | :--- | :--- |
| 1 | 启动自检（Termux / 转换 / `bash -n` / 运行） | ✅ `bash -n：PASS`、`运行 rc=0`、`--- 自检通过 ---` |
| 2 | **语法闸门自检** | ✅ `合法脚本=通过，非法脚本=检出错误` |
| 3 | API 配置读取 + key 不回显 | ✅ `key=已设置(17 字符)` |
| 4 | 转换 | ✅ `转换 0 / 未变 3；错误 0 / 警告 0 / TODO 2` |
| 5 | 隐私提示 | ✅ `将把 2 条 TODO 发送到：http://127.0.0.1:8731/v1` + 橙色离开本机提示 |
| 6 | 明文 HTTP 到 host LLM | ✅ host 侧记录 `POST /v1/chat/completions` 200 |
| 7 | 并行流式（并发 3） | ✅ `0/2 完成 · 2 进行中`，首条自动展开 |
| 8 | 完成态 | ✅ `2/2 完成`，两行 ✓，`应用全部` 启用 |
| 9 | **错误隔离** | ✅ `完成 1 / 失败 1`，失败行红字 `✗ 失败：API 调用失败：服务端错误（HTTP 500）`，另一行照常 ✓ |
| 10 | **单条重试** | ✅ 失败行重试后转 ✓，正文变为重试那次的流式内容 |
| 11 | 聚合 diff → 确认 → 应用 | ✅ `已应用 2 条修复` |
| 12 | 应用后落盘 + 复检 | ✅ `修复后产物已保存：.../work/input.sh`、`修复后 bash -n：PASS` |

失败注入由 host 侧假 LLM 完成（`/tmp/p2-smoke/fake_llm.py --fail-at 2,3`）：
第 2 个请求 500 → provider 内置重试（`max_retries=1`）→ 第 3 个请求**再次 500** → 该条判失败。
这正好同时验证了「provider 内部重试」与「编排层错误隔离」两层。

### 4.3 过程中发现并修掉的 4 个真 bug

| # | 现象 | 根因 | 修法 |
| :--- | :--- | :--- | :--- |
| 1 | `make_syntax_checker` 一构造就 `TypeError` | 工厂函数**提前**求值 `tx.work / name`，此时 tx 可能尚不可用 | 路径延迟到 `checker()` 内取，并捕获 `OSError/TypeError` |
| 2 | 聚合 diff 几乎不可读（深底深字） | diff 的 `ft.Text` **没给 color**，浅色主题下默认前景是深色，落在 `GREY_900` 上 | 显式 `color=ft.Colors.GREY_200`（与产物区一致），字号 10→11 |
| 3 | **失败条目的流式框塌成一条竖线** | `ExpansionTile.controls` 不横向拉伸子元素；失败条目没有 chunk → 正文为空 → Text 宽度 0 → Container 塌缩（与 PoC 报告 §4.6 bug#2 **同型**） | `ft.Column(..., horizontal_alignment=ft.CrossAxisAlignment.STRETCH)`（diff 对话框同样加固） |
| 4 | 单条重试后汇总行退化成「共 1 条」 | `_finish` 直接用了 `ParallelResult` 的汇总，而重试作业只有 1 条任务 | 新增 `_summary()`，**基于面板中全部任务**汇总 |

bug 1 由桌面 smoke test 抓到；bug 2/3/4 都是**实机截图**发现的
（bug 3 尤其隐蔽：成功行因为正文长而"看起来正常"，只有失败行才暴露）。
这正是「仪器先验证 + 实机截图」的价值。

---

## 5. 用户测试指南

### 5.1 安装

```bash
# 手机开启「允许安装未知来源应用」，然后二选一：
adb install -r -t packaging/android/build/apk/bat2sh-android-arm64-v8a.apk
# 或直接把 APK 传到手机点击安装

# 校验完整性
sha256sum bat2sh-android-arm64-v8a.apk
# 期望 525ebdce5df3edf7d319c8da822e68bb0da625d018abdb874ad3cc6597311cd9
```

首次启动会解压 32 MB 的 Termux 运行时（约数秒），状态栏显示「就绪（入口进程：direct）」。
报告区会自动跑一遍启动自检，**其中应包含**：

```
--- 启动自检 ---
...
--- 自检通过 ---
语法闸门自检：合法脚本=通过，非法脚本=检出错误
```

最后一行是本次新增的：它证明设备上的 `bash -n` 闸门真的在工作。
**如果这一行显示「漏检」，请不要使用 AI 修复功能并反馈。**

### 5.2 配置 API

1. 点工具栏最右的 **「设置」**
2. 填写：
   - **API 地址**：OpenAI 兼容的 base_url，例如
     - 云端：`https://api.openai.com/v1`
     - 本地 Ollama：`http://192.168.1.10:11434/v1`（**明文 http 已实测可用**）
     - LM Studio：`http://192.168.1.10:1234/v1`
   - **API key**：本地端点常无鉴权，可留空
   - **模型名**：如 `gpt-4o-mini` / `qwen2.5-coder` / `llama3.1`
   - **并行并发数**：默认 3（本地小模型建议 1–2，云端可 3–8）
   - **超时**：默认 30 秒；本地慢模型建议调到 120
3. 点「保存」→ 状态栏出现「API 配置已保存」，报告区记录
   `API 配置已保存：endpoint=... model=... key=已设置(N 字符) ...`（**不会显示 key 本身**）

### 5.3 转换 → 并行修复

| # | 操作 | 期望 |
| :--- | :--- | :--- |
| 1 | 「选择文件」选一个 `.bat`/`.cmd`/`.ps1`，或直接在源代码框粘贴 | 状态栏显示编码与字节数 |
| 2 | 点「转换」 | 产物区出现彩色 bash；报告区显示 `... TODO N`；下方出现 `报告里 TODO N 条` 且「用 AI 并行修复」变为可点 |
| 3 | 点「用 AI 并行修复」 | 弹出**隐私提示**：`将把 N 条 TODO 发送到：<endpoint>` + 橙色离开本机提示 |
| 4 | 点「确认发送」 | 并行面板出现 N 行；首条 running **自动展开**并逐 chunk 显示模型输出 |
| 5 | 观察面板 | 顶部实时计数（`x/N 完成 · y 进行中 · z 失败`）+ 进度条；点任意行可展开看该条流式正文 |
| 6 | 若某条失败 | 该行红字显示原因；**其他条不受影响**；展开该行点「重试这一条」可单独重跑 |
| 7 | 点「应用全部」 | 弹出 diff 确认框（`--- 当前 / +++ 修复后`），注明「已逐条通过 bash -n 闸门」 |
| 8 | 点「确认应用」 | 报告区显示 `已应用 N 条修复` → `修复后产物已保存：...` → `修复后 bash -n：PASS` |
| 9 | 点「保存」 | 可再导出到系统「另存为」位置 |
| 10 | 中途想停 | 点「取消」；在途请求会被 socket shutdown 打断，其余条目标记为「跳过」 |

> **建议先拿小文件试**：`tests/fixtures/bat-pathologies/registry-and-wmic.bat`（3 条 TODO）
> 适合走通流程；`examples/stress_test.bat`（42 条 TODO）可压测并发与刷新。

---

## 6. 已知限制

| # | 限制 |
| :--- | :--- |
| 1 | **面板列表是固定高度（250）+ 内部滚动**：展开一条后，该条的正文框与「重试」按钮可能需要**在列表内再滑一次**才能看全（页面本身也在滚动 → 嵌套滚动）。功能不受影响，但小屏上略绕。 |
| 2 | **只能修一个文件**：不做批量修复多文件（任务书明确排除）。 |
| 3 | **无连接测试**：设置里没有「测试连通性」按钮（任务书明确排除）；填错 endpoint 只会在第一次修复时报错。 |
| 4 | **不暴露 `context_lines`**：每条发送多少行上下文仍用 core 默认 3（设置里可改的是并发/超时/思考开关）。 |
| 5 | **`enable_thinking` 的实际语义取决于端点**：关闭时才会显式带 `enable_thinking: false`；端点不认该参数时 core 会自动降级并告警（既有行为）。 |
| 6 | **API key 明文存储**（决策 1，用户自担风险）：文件权限 0600 + 应用私有目录隔离实测生效；但见 #7。 |
| 7 | **本应用「运行」会以同 UID 执行任意 bash，因而能读到 api.json**（Phase 1 §4.6.2 已披露，用户已接受）。请只运行可信脚本。 |
| 8 | **`android:allowBackup` 未声明（默认 true）**：理论上 `adb backup` 可导出应用数据。Flet 不暴露该开关；现代 Android 已对 adb backup 加限且需设备端确认。 |
| 9 | **targetSdk 28**：不满足 Google Play 上架要求（侧载无影响），这是 Phase A 拿回完整 shell 能力的硬要求。 |
| 10 | **产物首行 `#!/usr/bin/env bash` 在 Android 上无效**，不能 `./x.sh` 直接跑；应用内一律用 `bash <script>`。 |
| 11 | **APK 87 MB**（Termux bootstrap 占 32 MB）。 |
| 12 | **arm64 真机执行未验证**：本次全部执行验证在 x86_64 模拟器上完成；arm64 只验证了**构建产物**（含 `lib/arm64-v8a/*` 与 `assets/app.zip` 内的 `bootstrap-aarch64.zip`，targetSdk 28，INTERNET 权限）。**请以实机安装测试为准。** |
| 13 | 高亮/大脚本性能、Android 15/16 安装、长时间任务中断等沿用 PoC 报告的未验证项。 |

---

## 7. 偏离与置信度披露（纪律 2 / 3）

| # | 项 | 说明 | 置信度 |
| :--- | :--- | :--- | :---: |
| 1 | **设置里多加了「超时」** | 任务书必填项是 endpoint/key/model/enable_thinking/max_concurrency 五项。加 timeout 的理由：core 的超时错误信息本身就在建议用户「调大超时」，而此前**没有任何 UI 能改它**；本地小模型 30 s 常不够 | A |
| 2 | **新增 `UiPump`，重构了既有 `_say`/`_log`** | 任务书 §4.2 的刷新节流只针对并行路径。但既有代码的 `_say`/`_log` 是**后台线程直接 `page.update()`**，与并行 drainer 并存时会并发改控件树。为让全应用一致地守住纪律，把它们改为「投递闭包 + 单一 drainer」。属**扩大改动范围**，在此披露 | A |
| 3 | **新增 `probe-cleartext/` 工程** | 任务书第 0 步要求「搭最小网络探针」；按 PoC 的 `probe-target28/` 先例单独成目录，不污染主工程。**它会把 `build/` 与源码留在仓库里** | A |
| 4 | **启动自检多了一行「语法闸门自检」** | 不新增按钮、不改布局；让用户一打开就能确认闸门真的在跑，也让 §3.2 的关键不变量可被用户自行复现 | A |
| 5 | **`_summary()` 覆盖了 `ParallelResult` 的汇总** | 修 bug 4 的必然结果；`summarize()` 仍保留在 `api_bridge` 里供 CLI 风格调用 | A |
| 6 | 第 0 步的探针 APK 也装了机 | 与正式应用**不同包名**（`io.github.bat2sh_probe_cleartext`），不互相干扰；验证后未卸载，用户可自行删除 | A |
| 7 | 桌面 UI smoke test 用一次性 venv | `/tmp/p1-fletvenv`（仓库外，含 flet-desktop）。**未污染** `/tmp/flet-termux-poc/.venv` | A |
| 8 | 未改动 `python/bat2sh/` 任何文件 | `git diff HEAD -- python/` = 0 行（纪律 1） | A |
| 9 | 未合并 main、未 bump 版本、未打 tag | 纪律 3 | A |
| 10 | **bug 3 的修法是「症状级」** | `horizontal_alignment=STRETCH` 是对的修法（与 app.py 根 Column 同款），但没有系统性排查其它 `Container` 是否也有同型风险 | B |
| 11 | **实机验证仅覆盖 2 条任务** | 并发 3 但只有 2 条 TODO，因此「并发 > 任务数」与「≥4 条同时流式」的实际刷新压力未在设备上压测（桌面 smoke test 用过 3 条 + 高速假端点） | B |

---

## 8. 复现命令

```bash
# ---- 环境 ----
cd /home/duanjb666/bat2sh
source /tmp/flet-termux-poc/env.sh
export FLET_BIN=/tmp/flet-termux-poc/.venv/bin/flet

# ---- 第 0 步：明文 HTTP 探针 ----
/tmp/flet-termux-poc/.venv/bin/python -u /tmp/p2-smoke/http_server.py &   # host 侧
adb reverse tcp:8731 tcp:8731
cd packaging/android/probe-cleartext
$FLET_BIN build apk --arch x86_64 --yes --no-rich-output
adb install -r -t build/apk/bat2sh-probe-cleartext.apk
adb logcat -c && adb shell monkey -p io.github.bat2sh_probe_cleartext \
    -c android.intent.category.LAUNCHER 1
sleep 20 && adb logcat -d -s flet.python | grep -E "PASS|VERDICT"

# ---- 构建（注意顺序：先 x86_64 验证，arm64 最后）----
cd /home/duanjb666/bat2sh/packaging/android
./build.sh x86_64          # 模拟器验证用
./build.sh arm64-v8a       # ★ 交付；必须最后跑
cp build/apk/bat2sh-android.apk build/apk/bat2sh-android-arm64-v8a.apk
sha256sum build/apk/bat2sh-android-arm64-v8a.apk

# ---- 实机验证（假 LLM，含故障注入）----
/tmp/flet-termux-poc/.venv/bin/python -u /tmp/p2-smoke/fake_llm.py --fail-at 2,3 &
adb reverse tcp:8731 tcp:8731
adb install -r -t build/apk/bat2sh-android.apk
# 预置配置（需 adb root）：
#   <FLET_APP_STORAGE_DATA>/config/bat2sh/api.json
#   base_url=http://127.0.0.1:8731/v1, model=fake-model, max_concurrency=3
adb shell am force-stop io.github.bat2sh_android
adb logcat -c && adb shell monkey -p io.github.bat2sh_android \
    -c android.intent.category.LAUNCHER 1

# ---- 桌面 smoke test ----
/tmp/flet-termux-poc/.venv/bin/python -u /tmp/p2-smoke/smoke_bridge.py     # 无需显示
DISPLAY=:0 /tmp/p1-fletvenv/bin/python -u /tmp/p2-smoke/smoke_panel.py     # 需 X
```

---

## 9. 证据文件

| 位置 | 内容 |
| :--- | :--- |
| `packaging/android/build/apk/bat2sh-android-arm64-v8a.apk` | **交付 APK**（87,247,863 B） |
| `packaging/android/probe-cleartext/` | 第 0 步探针工程（源码） |
| `/tmp/p2-smoke/smoke_bridge.py` / `smoke_panel.py` | 桌面 smoke test（含线程 ident 探针） |
| `/tmp/p2-smoke/fake_llm.py` | 假 OpenAI 兼容端点（含 `--fail-at` 故障注入） |
| `/tmp/p2-smoke/*.png` | 实机截图（隐私提示 / 流式 / 错误隔离 / 重试 / diff / 应用后） |
| `adb logcat -s flet.python` | 启动自检、语法闸门自检、并行修复与应用的完整原始输出 |
| `/tmp/p2-smoke/llm*.log` | host 侧收到的每一条设备请求 |

---

> **结论：Phase 2 完成。** 第 0 步明文 HTTP 实测可达（无需补救）；
> `core/api/` 零改动复用了并行编排，并把 Android 上会「静默假通过」的语法闸门
> 换成 Termux 版（`run_parallel` 与 `merge_replacements` 两处都注入，实机自检可复现）；
> 并行面板按方案 B 落地，工作线程只入队、事件循环批量刷新（实测 15 次刷新 0 次越界）；
> 转换 → 隐私确认 → 并行流式 → 错误隔离 → 单条重试 → 聚合 diff → 应用 → `bash -n` 全链路
> 已在 Android 14 模拟器跑通，过程中修掉 4 个真 bug。
>
> **交付 APK 87,247,863 B（sha256 `525ebdce…1cd9`），等用户安装测试。**
