# bat2sh Android —— API 修复（含并行）Phase 1 只读评估

> 会话：Android API。起点 HEAD（锁定）= `c476e5e`（= `android-poc-v2` tip）；
> 分支 `android-api`，**未合并 main、未 bump 版本、未打 tag**。
>
> 本阶段为**只读评估**：未改动 `python/bat2sh/core/`，未改动 `packaging/android/src/`。
> 所有「实测」结论均由本次真实执行产生，命令与原始输出见 §9。

---

## 0. 结论摘要

| # | 评估项 | 结论 | 是否阻断 |
| :--- | :--- | :--- | :--- |
| 4.1 | `core/api/` 可复用性 | ✅ **4 个模块全部可直接复用，core 零改动** | 否 |
| 4.2 | `XDG_CONFIG_HOME` 注入 | ✅ **实测通过，core 零改动** | 否 |
| 4.3 | Android 网络权限 | ✅ INTERNET 由 Flet **硬编码默认加入**，已在实机 APK manifest 中确认 | 否 |
| 4.3b | **明文 HTTP（cleartext）** | ⚠️ **新发现的风险**，见 §4.3.3 —— 需 Phase 2 首日实测 | **否，但需优先验证** |
| 4.4 | 并行在 Flet 的可行性 | ✅ **实测通过**：816 事件 → 29 次 `page.update()`，0 错误 | 否 |
| 4.4b | **默认语法闸门在 Android 会静默假通过** | ⚠️ **必须注入 Termux 版 `syntax_checker`**，见 §4.4.4 | 否（有解） |
| 4.5 | 并行 UI 方案 | ✅ **推荐方案 B（可展开列表）**，见 §4.5 | 否 |
| 4.6 | API key 安全性 | ⚠️ 私有目录隔离有效；**但有 2 条真实泄露路径**，见 §4.6 | 否（需披露） |
| 4.7 | 工作量 | 约 **9–13 小时**等效工作量，见 §4.7 | 否 |

**一句话**：`core/api/` 的四个模块**开箱即用**，`parallel.py` 已经内置了 UI 需要的
`on_event` 流式回调与 `cancel_event` 取消钩子，Python 侧**零改动**；Flet 侧的
唯一技术风险（跨线程 `page.update()`）已用真实 Flet 应用实测解决 ——
**工作线程 + 队列 + 事件循环内批量刷新**，把 816 次事件压成 29 次真实 UI 更新。

**Phase 1 未发现阻断项。** 但发现 **2 个必须处理的隐患**（§4.3.3 明文 HTTP、§4.4.4 语法闸门假通过），
详见下文章节。

---

## 1. 前置确认（任务书 §一）

| # | 前置 | 结果 |
| :--- | :--- | :--- |
| 1 | 分支 `android-poc-v2` 存在，HEAD = `c476e5e` | ✅ `git rev-parse android-poc-v2` = `c476e5e1e91c15d56b1c1d891c3810f9302bdadf` |
| 2 | `docs/android-poc-v2-report.md` 存在 | ✅ 20,500 B |
| 3 | `/tmp/flet-termux-poc/env.sh` 存在 | ✅ 879 B；`/tmp` 未被清 |
| 4 | 代理可用 | ✅ 连测 3 次 `github.com` → HTTP 200（1.4–1.7 s）；`maven.google.com` → 301 |

补充环境事实（本次实测）：

| 项 | 值 |
| :--- | :--- |
| Flet | **1.0.0**（`/tmp/flet-termux-poc/.venv`） |
| Python | 3.14.7 |
| **Android 模拟器** | ✅ **`emulator-5554` 正在运行**（AVD `poc34`，Android 14 / API 34，x86_64） |
| 上一 session 的 APK | ✅ 仍在 `packaging/android/build/apk/`（arm64 87,179,311 B / x86_64 88,983,582 B） |
| 生成的 Flutter 工程 | ✅ 仍在 `packaging/android/build/flutter/`（可直接读 manifest，见 §4.3） |

> 模拟器在跑，意味着 Phase 2 **不必重新建 AVD**，装机验证可以立刻做。

---

## 2. 分支

```
git checkout android-poc-v2      # HEAD c476e5e
git checkout -b android-api
```

当前：分支 `android-api`，HEAD = `c476e5e1e91c15d56b1c1d891c3810f9302bdadf`。
未合并 main、未 bump 版本、未打 tag。
`docs/flet-migration-assessment.md` 仍为未跟踪（前序 session 遗留，本次同样不动）。

---

## 3. Phase 1 评估

### 4.1 `core/api/` 现状盘点

`python/bat2sh/core/api/` 共 1,495 行 / 5 个文件，**纯标准库，不导入 GUI**：

| 模块 | 行数 | 职责 | Android 复用结论 |
| :--- | ---: | :--- | :--- |
| `config.py` | 244 | `ApiConfig` 数据类；加载 / 合并（CLI > env > 文件）/ 校验 / 原子写 + `chmod 0600` | ✅ **直接复用**。路径由 `XDG_CONFIG_HOME` 驱动（§4.2 已实测） |
| `provider.py` | 538 | OpenAI 兼容 SSE 流式；`urllib.request` 实现；可注入 `Transport`；错误分类 + 429 退避；`cancel_in_flight()` 打断阻塞读 | ✅ **直接复用**。仅需 `urllib`，Android 网络走 CPython raw socket（见 §4.3.3） |
| `fixer.py` | 254 | `scan_todo_markers` / `build_prompt` / `clean_completion` / `apply_replacement` / `render_diff` | ✅ **直接复用**。纯函数、无 I/O |
| `parallel.py` | 453 | 线程池 + 可收缩限流器 + 429 退避降并发 + 从后往前合并 + 逐步 `bash -n` 闸门 | ✅ **直接复用（本版核心）** |

**关键发现：`parallel.py` 已经是「为 GUI 设计」的接口**，不需要任何 UI 包装层：

| 已有能力 | 位置 | 对 Android UI 的意义 |
| :--- | :--- | :--- |
| `on_event: Callable[[FixEvent], None]` | `run_parallel()` 参数 | 流式 chunk 与状态迁移的**唯一分发出口** |
| `FixEvent(index, status, detail, chunk)` | `parallel.py:65` | `index` 直接就是 UI 列表行号；`chunk` 即增量正文 |
| **内部锁串行化回调** | `emit()` / `event_lock` | **消费者无需自带锁** —— 文档明写，实测 0 apply 错误（§4.4） |
| `cancel_event: threading.Event` | `run_parallel()` 参数 | 「取消」按钮直接 `set()` |
| `syntax_checker: SyntaxChecker` | `run_parallel()` / `merge_replacements()` 参数 | **Android 必须注入 Termux 版**（§4.4.4） |
| `provider.cancel_in_flight()` | `CancelAwareTransport` | 取消时 `socket.shutdown()` 打断阻塞读 |
| `merge_replacements(text, tasks)` | 返回值 `(merged, dropped)` | 聚合 diff 的输入 |
| `render_diff(old, new)` | `fixer.py` | 聚合 diff 直接可显示 |

**结论**：**没有任何一个模块需要 UI 包装层**。Flet 侧只负责
① 收集 markers → `plan_tasks`；② 起工作线程跑 `run_parallel`；
③ 把 `FixEvent` 分发到列表行；④ 收尾调 `merge_replacements` + `render_diff`。

**需要 Flet 侧补的只有 3 件**（都不碰 core）：

1. **Termux 版 `syntax_checker`**（§4.4.4，必需）
2. `ApiConfig` ↔ 设置 UI 的读写绑定（`load_api_config` / `save_api_config` 直接调）
3. 并发 provider 实例：`create_provider(config)` 一个实例被多线程共享 ——
   `OpenAICompatibleProvider` 已自带 `_thinking_lock`（`provider.py:300`），文档明写
   「并发修复下单实例可能被多个工作线程共享」，**直接复用单实例即可**。

---

### 4.2 配置路径验证（实测，任务书要求）

**做法**：复刻 Flet 层的注入顺序（先有 `FLET_APP_STORAGE_DATA`，再据此设 `XDG_CONFIG_HOME`），
然后**直接调用 core**，观察 `api_config_path()` 是否跟随。

```python
os.environ["FLET_APP_STORAGE_DATA"] = "/tmp/p1-fletdata"
os.environ["XDG_CONFIG_HOME"] = os.path.join(os.environ["FLET_APP_STORAGE_DATA"], "config")
from bat2sh.core.api import config as C
```

**实测输出**：

```
XDG_CONFIG_HOME = /tmp/p1-fletdata/config
api_config_path() = /tmp/p1-fletdata/config/bat2sh/api.json
saved. exists: True
file mode: 600
parent mode: 755
roundtrip base_url/model/key-ok: https://example.test/v1 m1 True
max_concurrency: 3 enable_thinking: False
missing_requirements: []

--- 默认(不设 XDG) 时对比 ---
api_config_path() = /home/duanjb666/.config/bat2sh/api.json
```

**判定：✅ 通过。core 零改动。**

依据 `config.py:135-137`：

```python
def api_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "bat2sh" / "api.json"
```

`XDG_CONFIG_HOME` 是 core 已有的第一优先级来源，Flet 层注入即可，**完全不需要改 core**。
同时确认 `save_api_config()` 的 `chmod 0600` 生效（实测 `file mode: 600`）。

**Android 上的实际落点**（`FLET_APP_STORAGE_DATA` 在 Android = 应用私有 files 目录；
由上一 session 实测的工作目录 `/data/user/0/io.github.bat2sh_android/files/data/work` 反推）：

```
/data/user/0/io.github.bat2sh_android/files/data/config/bat2sh/api.json
```

**注入位置**：任务书 §5.3 要求写在 `main.py` 开头。注意一个**顺序陷阱**：
必须在 `import bridge` / `import bat2sh.*` **之前**设置 —— 因为 `config.py` 的路径函数虽然
是调用时求值（不是 import 时求值），但 `ui/app.py` 在 import 阶段就会
`sys.path.insert` 并 import `bridge`（进而 import core）。
**为稳妥，注入放在 `main.py` 的第一条可执行语句**（早于 `import flet`）。
本项在 Phase 2 实现，Phase 1 只给结论。

---

### 4.3 Android 网络权限

#### 4.3.1 `pyproject.toml` 该怎么写

任务书设想的 `permissions = ["android.permission.INTERNET"]` **并不是 Flet 的真实键名**。实测源码：

| 事实 | 证据 |
| :--- | :--- |
| Flet **无条件硬编码** INTERNET 为默认权限 | `flet_cli/commands/build_base.py:1062`：<br>`android_permissions = {"android.permission.INTERNET": True}` |
| pyproject 合并键是 **`tool.flet.android.permission`（单数）** | `build_base.py:1181-1184`：<br>`merge_dict(android_permissions, self.get_pyproject("tool.flet.android.permission") or {})` |
| 另有 CLI 开关 `--android-permissions` | `build_base.py:681-688` |

**判定：✅ INTERNET 已由 Flet 默认保证，无需为它做任何配置。**

本次仍建议在 `pyproject.toml` 里**显式声明**（防御 Flet 未来改默认值，并让意图可读）：

```toml
[tool.flet.android.permission]
"android.permission.INTERNET" = true
```

（键名是 `permission` 单数、表结构，**不是** `permissions = [...]`。这是任务书 §4.3 的写法需要修正的地方。）

#### 4.3.2 构建后 manifest 验证（已有实机产物）

直接反编译上一 session 已构建的 APK：

```bash
aapt2 dump xmltree --file AndroidManifest.xml build/apk/bat2sh-android-x86_64.apk
```

**实测输出**（全部 `uses-permission`）：

```
android.permission.INTERNET
android.permission.ACCESS_NETWORK_STATE
io.github.bat2sh_android.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION
```

`targetSdkVersion = 28` 同时确认。**判定：✅ 网络权限在实机产物中已存在。**

#### 4.3.3 ⚠️ 新发现：明文 HTTP（cleartext）可能被拦

**这是任务书没有列出、但会直接影响「endpoint 可配置」能否用本地模型的风险点。**

事实链：

1. Flet **不暴露** `usesCleartextTraffic` / `allowBackup` 开关
   （`grep -rn "cleartext|CleartextTraffic|networkSecurityConfig" flet_cli/` → 无命中）。
2. 生成的 manifest（`build/flutter/android/app/src/main/AndroidManifest.xml`）**没有**
   `android:usesCleartextTraffic` 属性。
3. Android 规则：该属性**默认值 `false`（targetSdk ≥ 28）**。我们的 targetSdk 恰好 = 28。

**潜在后果**：`http://192.168.x.x:11434/v1`（Ollama / LM Studio / vLLM 的默认形态）可能被拒。

**但有一个重要的反向论据 —— 这条风险很可能不成立**：

> Android 的 cleartext 限制是在 **Java 框架层**执行的
> （`NetworkSecurityPolicy.isCleartextTrafficPermitted()`，由 `HttpURLConnection` / OkHttp /
> WebView / Cronet 主动查询）。它**不是内核级封锁**，**不影响 raw socket**。
> 而 `provider.py` 走的是 `urllib.request` → CPython `socket` → 原生 socket 系统调用，
> **不经过 Java 网络栈**。

**判定：⚠️ 未决，置信度 B。** 两种可能都存在合理解释，**不能靠推理定案，必须实测**。

**处置**：列为 **Phase 2 第 0 步（最高优先）**，在写 UI 之前先做一次最小网络探针
（见 §5 Phase 2 计划）。若实测被拦，补救方案已备好：
* `flet build --template-dir`（`build_base.py:818`）指向 Flet 模板的本地副本，在
  `AndroidManifest.xml` 的 `<application>` 上加 `android:usesCleartextTraffic="true"`；
* 或退一步，在 UI 上明确提示「仅支持 `https://`」，并把该限制写进报告。

**给用户的影响提示**：若最终只能 https，则**局域网内无 TLS 的本地模型不可用** ——
这会影响「endpoint 可配置」的实际价值，因此必须在 Phase 2 第一优先验证。

---

### 4.4 并行在 Flet 的可行性（本 Phase 核心）

#### 4.4.1 `parallel.py` 的并发模型

**是线程池（`threading`），不是 asyncio。** 具体：

| 组件 | 实现 | 位置 |
| :--- | :--- | :--- |
| 派发 | `_AdaptiveLimiter`（`threading.Condition` 可收缩限流器，**只降不升**） | `parallel.py:210` |
| 队列 | `_Scheduler`（队列空但在途未完成时等待，避免漏掉 429 重试任务） | `parallel.py:248` |
| 工作线程 | `threading.Thread(daemon=True)`，数量 = 初始并发（默认 3） | `parallel.py:426` |
| 汇总 | 主调线程 `thread.join()` 阻塞直到全部完成 | `parallel.py:433` |
| 回调 | `on_event` 由**多个工作线程**触发，内部 `event_lock` 串行化 | `parallel.py:315` |
| 取消 | `cancel_event`（`threading.Event`）+ `provider.cancel_in_flight()` | `parallel.py:308,439` |
| 阻塞性 | **`run_parallel` 是同步阻塞函数**（会 join 所有线程） | — |

**关键含义**：`run_parallel` **绝不能在 Flet 事件循环线程里直接调用** —— 它会把 UI 冻住
（默认 3 并发、每条最多 30 s 空闲超时，最坏情况冻结数十秒）。

#### 4.4.2 Flet 1.0 提供的迁移原语（已确认存在）

```
Page.run_thread(handler, *args, **kwargs) -> None
    "Run handler function as a new Thread in the executor associated with the current page."
Page.run_task(handler, *args, **kwargs) -> Future
    "Run handler coroutine as a new Task in the event loop associated with the current page."
Page.schedule_update()
    "Queue this page for a deferred batched update."
Page.loop  -> 事件循环
```

**两者都在，正好构成桥的两端。**

#### 4.4.3 实测：两条分发放方案的对照

**仪器**：`/tmp/p1-probe/probe_threads.py` —— 一个**真实的 Flet 1.0 桌面应用**
（`ft.run`，非 mock），跑**真实的 `bat2sh.core.api.parallel.run_parallel`**，
只有 provider 是假的（12 条任务、3 并发，其中第 5 条**故意抛 500** 以验证错误隔离；
前 3 条以无延迟狂吐 200 chunk 模拟高速端点，其余每条 24 chunk × 8 ms）。

- **方案 A（队列 + 事件循环批量刷新）**：worker 经 `page.run_thread` 启动；
  `on_event` 只 `queue.put`；`page.run_task(drainer)` 在事件循环里取队列、
  **一次 update 前把已到达的事件全部吃掉**。
- **方案 B（工作线程直接 `page.update()`）**：即当前 PoC 应用 `_log` / `_say` 的做法。

**实测结果**：

| 指标 | 方案 A（队列+批量） | 方案 B（直接 update） |
| :--- | ---: | ---: |
| 任务结果 | 11 done / **1 failed** | 11 done / **1 failed** |
| 事件总数 | 816（chunk 792 + status 24） | 816（同） |
| **`page.update()` 调用次数** | **29** | **816** |
| `update_errors` | **0** | 0 |
| `apply_errors` | **0** | 0 |
| 队列最大深度 | 607 | —（无队列） |
| 首事件 / 首 chunk 延迟 | 0.01 s / 0.01 s | 0.01 s / 0.01 s |
| 总耗时 | **1.03 s** | 1.37 s |
| UI 控件抽查 | `#1 done` / 流式正文已写入 | 同 |

**取消路径**（方案 A + `cancel_event`，0.30 s 时 `set()`）：

```
MODE=cancel  elapsed=0.78s
  tasks=12 statuses={'done': 6, 'failed': 1, 'skipped': 5}
  events=731 (chunk=709 status=22)
  page.update() calls=16  update_errors=0  apply_errors=0
```

在途与排队任务全部正确落为 `skipped`，**无异常、无卡死**。

**结论**：

1. ✅ **`parallel.py` 的线程模型在 Flet 1.0 里完全可行。**
2. ✅ **错误隔离经实测确认**：1 条 500 失败，其余 11 条照常 done。
3. ✅ **`on_event` 的内部锁有效**：0 apply 错误（3 线程并发回调）。
4. ✅ **方案 A 是明确更优解**：同样 816 个事件，**29 次 vs 816 次 UI 更新（≈28× 削减）**，
   且总耗时更短（1.03 s vs 1.37 s）。
   - 每次 `page.update()` 都要序列化控件树并经本地 socket 送给 Flutter 客户端。
     手机上 CPU 更弱、桥更慢，816 次/秒 的更新量有肉眼可见的卡顿与 ANR 风险。
   - 方案 B 在桌面上「没崩」**不等于安全**：它从 3 个线程并发改控件树且无锁，
     属于**未定义行为**，本次只是没暴露出来。

**因此 Phase 2 采用方案 A**，具体形态：

```python
# 1) 工作线程跑阻塞编排
page.run_thread(worker)                      # worker 内调 parallel.run_parallel(..., on_event=q.put)

# 2) 事件循环内唯一允许碰控件的地方
async def drainer():
    while running:
        try: ev = q.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.02); continue
        apply(ev)                            # 改控件值，不 update
        while True:                          # 把已到达的一次性吃掉
            try: apply(q.get_nowait())
            except queue.Empty: break
        page.update()                        # 每轮只 update 一次
```

**刷新节奏**：20 ms 轮询 ≈ 50 fps 上限，实测批量比 ≈28:1，手机端足够。

#### 4.4.4 ⚠️ 必须处理：默认语法闸门在 Android 会「静默假通过」

`core/syntax.py:20-27`：

```python
def bash_syntax_error(script: str) -> str | None:
    bash = shutil.which("bash")
    if bash is None:
        return None          # ← 找不到 bash 就返回 None = 判定「通过」
```

`run_parallel(..., syntax_checker=bash_syntax_error)` 是**默认值**（`parallel.py:290`），
而 `merge_replacements(..., syntax_checker=bash_syntax_error)` 同样（`parallel.py:164`）。

**这正是上一 session 点名的 P1 同型问题**（`docs/android-poc-v2-report.md` §4.2(2)）：
Android 上 `shutil.which("bash")` 找不到 Termux 的 `$PREFIX/bin/bash`（不在 PATH），
于是**每一处「建议未通过 bash -n」的检查都会静默判通过** ——
后果是**坏的合并会被当成好的写进产物**，直接违反 core 的
「never emit broken bash」不变量，而且**用户看不到任何错误**。

**处置（core 零改动）**：`syntax_checker` 本来就是为注入而设计的参数。
Phase 2 在 Flet 侧实现一个基于 `Termux.syntax_check()` 的检查器注入进去：

```python
def termux_syntax_checker(script: str) -> str | None:
    checked, ok, msg = runner.check_text(script)   # 复用 ui/runner.py 的 Termux 路径
    if not checked:
        return "无法执行 bash -n（" + msg + "）"     # ← 关键：未执行 = 失败，不是通过
    return None if ok else msg
```

并**同时注入 `run_parallel` 与 `merge_replacements` 两处**。
`ui/runner.py` 已经有「(是否真的跑了校验, 是否通过, 信息)」三元组的先例，
语义直接沿用：**「未执行」必须判失败，绝不判通过**。

> 这是本 Phase 唯一一处「照默认值写就会出隐性错误」的地方，务必在 Phase 2 落实。

---

### 4.5 并行 UI 设计（手机屏幕约束）

#### 4.5.1 约束

| 约束 | 数值 / 说明 |
| :--- | :--- |
| 屏幕宽 | ~360 dp（典型手机） |
| 典型条目数 | 10–20 条 TODO（§5.2 示意图假设 3 条，实际更多） |
| 并发数 | 默认 3（可配 1–16） |
| 每条内容 | 流式 bash 代码，单条可达数百行 / 数 KB |
| 必须同时可见 | 每条状态（pending/running/done/failed/skipped） |
| 必须可做 | 单条看流式、单条重试、整体取消、看聚合 diff、应用 |

**核心矛盾**：并发 3 路 × 数百行流式 bash，屏幕只有 360 dp 宽。
把 3 路流式正文同时铺开 = 互相挤爆 + 疯狂重排。

#### 4.5.2 候选方案对照

| 方案 | 描述 | 手机端评价 |
| :--- | :--- | :--- |
| A | 同桌面布局：列表一行一条，行内直接显示该条流式 | ❌ 3 路正文同时展开，垂直空间被瓜分，内容互相挤压；每来一个 chunk 就要重排整个列表 |
| B | **可展开列表**：列表只显示状态，点击展开该条流式 | ✅ **推荐**，见下 |
| C | 顶部 Tab，每条一个 tab | ❌ 10–20 条 → tab 栏横向溢出/需要滚动，且**看不到全局进度**（哪条失败了一眼看不到） |
| D | 单条视图 + 进度指示 | ❌ 丢失「全局态势」；失败条目容易被忽略，与「错误隔离 + 单独重试」的需求相冲 |

#### 4.5.3 ✅ 推荐方案 B（可展开列表），并加 3 处针对手机的优化

**结构**：

```
┌──────────────────────────────────────┐
│ 修复进度  4/12 完成 · 1 失败 · 2 进行中 │  ← 聚合计数
│ ▓▓▓▓▓▓▓▓░░░░░░░░░░░░  33%            │  ← ft.ProgressBar
├──────────────────────────────────────┤
│ ▸ #1  第 8 行   ✓ 完成      1.2 KB   │  ← 折叠行：状态 + 字节数
│ ▾ #2  第 12 行  ⟳ 流式中…   0.8 KB   │  ← 展开行（仅当前展开的这条渲染正文）
│     ┌──────────────────────────────┐ │
│     │ echo "fixed-2"               │ │  ← 等宽、自动滚到底
│     │ #part1 #part2 …              │ │
│     └──────────────────────────────┘ │
│     [重试]  [看差异]                  │
│ ▸ #3  第 19 行  ⏸ 等待                │
│ ▸ #4  第 24 行  ✗ 失败：500 …  [重试] │
├──────────────────────────────────────┤
│ [应用全部]  [取消]                     │
└──────────────────────────────────────┘
```

**为什么是 B**：

1. **全局态势与单条细节兼得** —— 折叠行永远显示全部 N 条的状态与计数，
   这是 A/C/D 都给不了的（C 看不到全局、D 只有一条）。
2. **垂直空间有界** —— 列表固定高度（如 240 dp）+ 自身滚动；展开只影响一条，
   不会把「应用全部 / 取消」按钮挤出屏幕。
3. **⭐ 手机上真正的性能优势：按需渲染。**
   折叠行**只更新一个短字符串**（状态 + 字节计数），
   流式正文**只在被展开的那一条上渲染**。相比方案 A 让 3 条正文同时跟着 chunk 重排，
   每轮 `page.update()` 要序列化的控件树小一个量级 ——
   与 §4.4.3 的批量刷新叠加，正好压在手机桥的舒适区。
4. **`ft.ExpansionTile` 是 Flet 内置控件**（本次已确认存在，参数含
   `title/subtitle/leading/trailing/controls/maintain_state`），
   就是 Android/Material 的原生列表惯例，用户零学习成本，且**不用手写折叠动画与状态**。
5. **失败条目的「重试」就近放** —— 直接满足「一条失败不阻塞其他 + 失败条目可单独重试」，
   不必再开一层页面。

**默认展开策略**：自动展开**第一条进入 `running` 的条目**，让用户一按就有流式反馈
（满足「逐 chunk 流式显示」的直观要求），之后**不自动切换** ——
避免用户正在读某条时被抢走焦点。

**`✓/⟳/⏸/✗` 图标映射**（`parallel.py` 的 5 个状态常量）：
`pending→⏸`、`running→⟳`、`done→✓`、`failed→✗`、`skipped→⊘`。

**聚合 diff 与应用**：全部收完后按 `[应用全部]` → `merge_replacements(text, tasks, syntax_checker=…)`
→ `fixer.render_diff(old, merged)` → 弹 `AlertDialog` 显示 diff → 用户确认 → 写回产物区 →
重新 `bash -n` → `runner.stage()` 保存。与桌面 GUI / CLI 的既有流程一致（`cli.py:851`）。

---

### 4.6 API key 安全性

#### 4.6.1 落地位置与隔离性

| 项 | 实测 / 结论 |
| :--- | :--- |
| 路径 | `/data/user/0/io.github.bat2sh_android/files/data/config/bat2sh/api.json` |
| 文件权限 | `chmod 0600` —— **实测生效**（`file mode: 600`，§4.2） |
| 父目录 | `/data/user/0/<pkg>/` 由 Android 以 **0700、应用专属 UID** 创建 |
| 跨应用隔离 | ✅ **有效**。其他 App 无法读取（无 root 时）；文件级 SELinux 标签为 `app_data_file`，仅同 UID 域可访问 |

**`chmod 600` 在 Android 上是否有效？**
**有效，但基本是冗余的。** Android 的 ext4/f2fs 支持 POSIX 权限位，`os.chmod` 会成功
（本次实测 600 已写入）；但应用私有目录**本来就是 0700 且属主是应用 UID**，
所以 600 并没有增加多少实际防护 —— 真正的隔离来自 **UID + SELinux**，不是这 600。
（对比桌面：桌面上 600 是**必需**的，因为 `~/.config` 可能是 755 且同机多用户可读。）

#### 4.6.2 ⚠️ 两条真实的泄露路径（必须向用户披露）

**(1) 本应用自己会执行任意 bash —— 同一 UID，可直读 key。**
「运行」按钮会把产物交给内嵌 Termux 的 `bash` 执行，而该进程的 UID **就是这个 App 的 UID**，
因此**它能读到 `api.json`**。一段被投毒的 `.bat`（或转换错误导致的行为）完全可以
`cat` 出 key 并外发。这是「明文存储 + 应用内执行任意脚本」组合的**固有**风险，
不是实现 bug，但**必须写进报告的限制章节**。
（缓解：提醒用户只运行自己信任的脚本；或后续版本把 key 放到不参与执行的工作目录之外。）
置信度 **A**（同一 UID，权限必然可读）。

**(2) `android:allowBackup` 未声明 → 默认为 `true`。**
实测：生成的 manifest（`build/flutter/android/app/src/main/AndroidManifest.xml`）
**没有** `android:allowBackup` 属性，Flet 也不暴露该开关
（`grep allowBackup flet_cli/` → 无命中）。Android 该属性默认值 = `true`，
理论上 `adb backup` 可导出应用私有数据（含 api.json）。
**缓解**：现代 Android（12+）对 `adb backup` 已加限制且需设备端确认；
本设备是 Android 14。且该攻击前提是**攻击者已能物理接触并开启 USB 调试**。
置信度 **B**（属性缺失是实测的 A；实际可利用性未实机验证）。
可选加固：若 Phase 2 因 §4.3.3 需要走 `--template-dir`，**顺手加上
`android:allowBackup="false"`**，零额外成本。

#### 4.6.3 纪律 6 的落实要求（Phase 2 必须做）

| 要求 | 落实点 |
| :--- | :--- |
| **不写日志** | 不打印 `config.api_key`；设置界面用 `password=True` + `can_reveal_password` |
| **错误信息不泄露** | core 已提供 `provider.redact(text, *secrets)`（`provider.py:273`），且 `ProviderError` 文档明确「消息不得包含 API key」；Flet 侧所有错误路径**再套一层 `redact(msg, api_key)` 兜底**（`cli.py:855` 就是这个用法） |
| **不进 prompt / 不进 diff** | key 只在 `Authorization` 头；`build_prompt()` 不含 key（已核对 `fixer.py:116-174`） |

---

### 4.7 工作量估算

按「等效工作量」估（含实测与文档，不含 Phase 1 已完成的评估）：

| # | 工作项 | 估时 | 风险 |
| :--- | :--- | ---: | :--- |
| 0 | **明文 HTTP 探针**（§4.3.3，Phase 2 首步，阻断后续决策） | 0.5–1 h | **中**（未决） |
| 1 | API 设置 UI（endpoint/key/model/enable_thinking/max_concurrency）+ 读写 `api.json` | 1.5 h | 低 |
| 2 | Termux 版 `syntax_checker` 注入（§4.4.4） | 1 h | 低 |
| 3 | 并行编排桥：`plan_tasks` + `run_thread` + queue + `drainer`（§4.4.3 方案 A） | 2 h | 低（已实测） |
| 4 | 并行面板 UI：聚合头 + `ExpansionTile` 列表 + 状态图标 + 进度条（§4.5 方案 B） | 2.5–3 h | 低 |
| 5 | 隐私提示 `AlertDialog`（发送 N 条到 endpoint，不记忆） | 0.5 h | 低 |
| 6 | 聚合 diff → 确认 → 应用 → 重新 `bash -n` → `runner.stage()` 保存 | 1.5–2 h | 低 |
| 7 | 错误隔离 / 单条重试 / 取消 收尾 | 1 h | 低 |
| 8 | 桌面 smoke test + 模拟器实机验证（含截图、logcat 证据） | 1.5–2 h | 中（§4.3.3 可能连锁） |
| 9 | 报告 `docs/android-api-report.md` | 1 h | 低 |
| | **合计** | **13–15 h** | |

**若 §4.3.3 实测「明文 HTTP 被拦」**，追加 1.5–3 h（`--template-dir` 或网络
安全配置 + 重新验证），并需向用户披露「本地 http 端点」的可用性结论。

**关键路径**：第 0 步 → (若需) 第 0' 步 → 第 3 步 → 第 4 步 → 第 8 步。
第 1/2/5/6 步可与第 3/4 步并行推进。

**风险总评：低。** 唯一真正的未知量是 §4.3.3，且已备好两条补救路径。

---

## 4. Phase 2 计划（待用户确认后执行）

严格按任务书 §五，并按本评估的发现做 3 处**必要修正**：

| # | 任务书原文 | 本评估的修正 | 理由 |
| :--- | :--- | :--- | :--- |
| 1 | §4.3 `permissions = ["android.permission.INTERNET"]` | 改为 `[tool.flet.android.permission]` 表结构（或干脆不写，Flet 已默认） | 实测键名不符（§4.3.1） |
| 2 | §5.3 未提语法闸门 | **增加**：向 `run_parallel` 与 `merge_replacements` 注入 Termux 版 `syntax_checker` | 默认值在 Android 静默假通过（§4.4.4） |
| 3 | §5.3 未提刷新节流 | **明确**：工作线程 → queue → `run_task` drainer 批量刷新，**禁止**工作线程直接 `page.update()` | 实测 28× 更新量差异（§4.4.3） |

**执行顺序**：

1. **第 0 步（阻断）**：搭最小网络探针，在 `emulator-5554` 上实测
   `http://` 端点连通性 → 决定是否需要 manifest 加固。**结果先报告用户。**
2. `pyproject.toml`：加 `[tool.flet.android.permission]`；若第 0 步需要，同时加 cleartext 处理。
3. `main.py`：首条语句注入 `XDG_CONFIG_HOME`。
4. 新增 `src/api_bridge.py`：`ApiConfig` 读写 + `create_provider` + Termux `syntax_checker`
   + `plan_tasks` / `run_parallel` / `merge_replacements` 的薄封装（**不碰 core**）。
5. 新增 `src/ui/api_panel.py`：设置对话框 + 并行面板（方案 B）。
6. `src/ui/app.py`：接入按钮与状态，**保持既有四区布局不变**，并行面板插在报告区之下。
7. 桌面 smoke test（先排低级错误）→ 模拟器实机验证（截图 + logcat）。
8. 构建 arm64-v8a APK → sha256 + 大小。
9. 写 `docs/android-api-report.md`；commit 留在 `android-api` 分支。

**不做**（任务书明确排除）：批量修复多文件、连接测试。

---

## 5. 偏离与置信度披露（纪律 2 / 3）

| # | 项 | 说明 | 置信度 |
| :--- | :--- | :--- | :---: |
| 1 | **评估中安装了 `flet-desktop` 到一次性 venv** | `/tmp/p1-fletvenv`（仓库外）。为真实运行 Flet 应用做 §4.4 实测；**未污染** `/tmp/flet-termux-poc/.venv`，未改动仓库任何文件 | A |
| 2 | **§4.4 的实测在桌面 Linux 上完成，非 Android** | Flet 的 Python 侧线程/事件循环语义与平台无关，故结论可迁移；但**手机上的绝对刷新性能未实测**，已列入 Phase 2 实机验证项 | B |
| 3 | **§4.5 的方案 B 是设计建议，未做真机可用性测试** | 依据是控件可用性（已实测 `ExpansionTile` 存在）+ 屏幕约束推理 + §4.4 的刷新量数据 | B |
| 4 | **§4.3.3 明文 HTTP 未定案** | 两个方向都有合理解释；**已列为 Phase 2 第 0 步阻断验证**，不靠推理定案 | **B** |
| 5 | **§4.6(2) `allowBackup` 的实际可利用性未实机验证** | 「属性缺失」是实测 A；「能否真的 backup 出数据」未验证 | B |
| 6 | Phase 1 全部为只读 | 未改动 `python/bat2sh/core/`，未改动 `packaging/android/src/`；仅新增本文档 | A |
| 7 | 任务书 §4.3 的 `permissions = [...]` 写法有误 | 已用源码证据修正为 `tool.flet.android.permission` | A |
| 8 | 发现任务书未列出的 2 个隐患 | §4.3.3 明文 HTTP、§4.4.4 语法闸门假通过；均**未回避**，已给出处置 | A/B |

---

## 6. 仪器与证据（可复现）

| 位置 | 内容 |
| :--- | :--- |
| `/tmp/p1-probe/probe_threads.py` | §4.4 的 Flet 线程模型探针（真实 `ft.run` + 真实 `run_parallel`） |
| `/tmp/p1-probe/queue.log` | 方案 A 原始输出（816 事件 → 29 update） |
| `/tmp/p1-probe/direct.log` | 方案 B 原始输出（816 事件 → 816 update） |
| `/tmp/p1-probe/cancel.log` | 取消路径原始输出（6 done / 1 failed / 5 skipped） |
| `/tmp/p1-fletvenv/` | 一次性 venv（flet 1.0.0 + flet-desktop），**仓库外** |
| `$HOME/.flet/client/flet-desktop-light-1.0.0/` | 探针用的 Flet 桌面客户端（下载缓存） |

**复现命令**：

```bash
# §4.2 配置路径
/tmp/flet-termux-poc/.venv/bin/python -c "
import os,sys
os.environ['FLET_APP_STORAGE_DATA']='/tmp/p1-fletdata'
os.environ['XDG_CONFIG_HOME']='/tmp/p1-fletdata/config'
sys.path.insert(0,'/home/duanjb666/bat2sh/python')
from bat2sh.core.api import config as C
print(C.api_config_path())"

# §4.3 manifest
AAPT=$HOME/Android/sdk/build-tools/36.0.0/aapt2
$AAPT dump xmltree --file AndroidManifest.xml \
  packaging/android/build/apk/bat2sh-android-x86_64.apk | grep -i "uses-permission\|targetSdk"

# §4.4 线程模型（三个模式）
export DISPLAY=:0 && source /tmp/flet-termux-poc/env.sh
cd /tmp/p1-probe
/tmp/p1-fletvenv/bin/python -u probe_threads.py queue    # 方案 A
/tmp/p1-fletvenv/bin/python -u probe_threads.py direct   # 方案 B
/tmp/p1-fletvenv/bin/python -u probe_threads.py cancel   # 取消
```

---

## 7. 待用户确认的问题

1. **§4.3.3 明文 HTTP**：是否同意把它作为 Phase 2 的**第 0 步阻断验证**（在写 UI 之前先测）？
   —— 若被拦，本地 `http://` 模型将不可用，需要 manifest 加固或改用 https。
2. **§4.6.2(1)**：「应用内『运行』会以同 UID 执行任意 bash，从而能读到 API key」
   这一固有风险，是否接受并写入报告的「已知限制」即为足够？
   （决策 1 已选明文存储，用户自担风险；此处只是把它说清楚。）
3. **§4.5 方案 B** 是否为最终 UI 方案？

---

> **Phase 1 结论：无阻断项，可以进入 Phase 2。**
> `core/api/` 四模块零改动可复用；`XDG_CONFIG_HOME` 注入实测通过；
> INTERNET 权限已由 Flet 默认保证并在实机 manifest 确认；
> 并行线程模型在真实 Flet 应用中实测通过（816 事件 → 29 次 UI 更新，0 错误，错误隔离与取消均验证）。
> 两个新发现的隐患（明文 HTTP、语法闸门假通过）均已给出零 core 改动的处置方案。
>
> **按任务书 §七「Phase 1 评估完成 → 必须暂停」，此处暂停，等用户确认后再进入 Phase 2。**
