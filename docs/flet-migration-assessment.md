# bat2sh —— Flet 迁移可行性评估（只读）

> 会话：Flet 迁移可行性评估。起点 HEAD（锁定）= `905cf16`；**全程只读**（唯一写入 = 本文档）。
> 目标：评估把 GUI 迁移到 Flet、并打包 Android APK（arm64-v8a）的可行性。
>
> **结论摘要：有条件可行。** `core/` 可**零改动复用**（无 Qt 依赖、全标准库、zipimport 安全），
> 但 GUI 需重写（估算 **1,300–1,900 行**），且有两个必须先解决的问题：
> **① Android 上 `bash -n` 校验必然失效且当前会静默报「通过」**（触碰本项目最核心的报告诚实性纪律）；
> **②「运行脚本」功能在 Android 上不可实现**，须移除或降级。

---

## 0. 前置确认

| # | 前置 | 结果 |
| :--- | :--- | :--- |
| 1 | 工作区干净 | ✅ `git status --short` 为空 |
| 2 | HEAD = 最新 main tip | ✅ `905cf16`（本地 main tip 成立） |
| 3 | 已阅读 `docs/PROJECT-OVERVIEW.md` | ✅（含指标口径、层分离、纪律要求） |
| 4 | 版本 | `2.8.1`（`pyproject.toml` 与 `__init__.py` 一致） |

> **偏离披露（纪律 3）**：`origin/main` 落后本地 **7 个提交** —— 前序 session 的
> D-1~D-4 修复与 packaging 工作**尚未 push**。因此「HEAD = 最新 main tip」仅在**本地**成立，
> 远端 main 并不是最新。本评估以本地 `905cf16` 为准。

---

## 1. 核心逻辑复用性 —— **结论：可直接复用，零改动**

### 1.1 分层检查（实测）

| 检查项 | 方法 | 结果 |
| :--- | :--- | :--- |
| `core/` 是否依赖 Qt | `grep -rn "PySide6\|PyQt\|shiboken" python/bat2sh/core/` | **0 处** |
| `core/` 的第三方依赖 | 提取全部 `import` 的顶层包名 | **无**（全部标准库） |
| `core/` 是否反向依赖 `gui/` | `grep -rn "from ..gui" python/bat2sh/core/` | **0 处**（分层干净） |
| `core/api` 的 HTTP 实现 | 查看 `provider.py` 导入 | `http.client` / `urllib.request`（**无 httpx / requests**） |
| `__file__` / `pkg_resources` 数据加载 | 全仓 grep（排除 pycache） | **仅 1 处**：`gui/app.py:53`（图标） |

`core/` 全部导入的顶层包：`codecs collections dataclasses datetime difflib enum http json os
pathlib random re shutil socket stat subprocess tempfile threading time typing urllib`。

**结论**：Flet 应用可直接 `from bat2sh.core.engine import convert_text`，无需任何改造。
GUI 对 core 的依赖面也很小且已枚举（11 条 import：`engine`/`settings`/`types`/`encoding`/
`recent`/`syntax`/`api.config`/`api.fixer`/`api.parallel`/`api.provider`）。

### 1.2 zipimport 安全性（Flet ≥ 0.86 的关键约束）

Flet 0.86.0 起，Android 上**纯 Python 代码（含 site-packages）以 zip 资产形式随包**
（`stdlib.zip` / `sitepackages.zip`），通过 `zipimport` 就地导入；
只有把数据文件按**真实文件系统路径**定位（`__file__` / `pkg_resources`）的包才需要
列入 `extract_packages`，否则会在设备上崩溃。

**bat2sh 不受影响**：`core/` 内 `__file__` 使用为 **0 处**，唯一一处位于 `gui/app.py`
（且 GUI 将被重写，图标改走 Flet `assets/`）。→ **无需 `extract_packages`**。

### 1.3 三个平台敏感点（迁移时必须处理）

#### P1 —— `bash -n` 校验在 Android 上必然失效，且**当前会静默报「通过」**（最高优先级）

`python/bat2sh/core/syntax.py:20-27`：

    bash = shutil.which("bash")
    if bash is None:
        return None          # ← 无 bash 时返回 None，语义 = 「语法通过」

**实测验证**（本机模拟 `shutil.which` 返回 `None`）：

| 输入 | 有 bash（本机） | 无 bash（模拟 Android） |
| :--- | :--- | :--- |
| `这显然不是合法 bash ((((` | `'<生成脚本>: 行 1: 未预期的记号 "(" 附近有语法错误'` | **`None`（= 通过）** |

**为什么这是问题**：该行为本身是**有意设计**（docstring 写明「通过或环境无 bash 时返回 None」），
在桌面上无关紧要（bash 恒存在）。但在 Android 上 **bash 必然不存在**，于是：

- 语法校验**永久静默失效**，却仍表现为「校验通过」；
- `ConvertReport` **没有任何字段**表示「校验未执行」—— 只有 `warnings/todos/errors` 三个列表
  （`core/types.py:66-90`，实测无 `skipped`/`checked` 状态）；
- 项目立身之本「**绝不输出坏 bash**」与 `degraded_script` 降级路径在 Android 上**永不触发**。

**这与本项目已两次修复的缺陷同类**：v2.6.0 A-1 与 v2.8.1 都是「门禁静默失效、报告与事实不符」。
**迁移到 Android 前必须先解决**，且应当修在 `core/`（CLI 与 GUI 共用），而不是在 Flet 层绕过。
建议方向：给 `ConvertReport` 增加显式的「校验未执行」状态，并在 UI/CLI 上如实显示
（例如「语法未校验（设备无 bash）」），而非计为通过。

#### P2 —— 配置/状态路径假设 `~/.config`

| 位置 | 代码 |
| :--- | :--- |
| `core/settings.py:101,129` | `os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")` |
| `core/recent.py:14` | 同上 |
| `core/api/config.py:136` | 同上（API 密钥持久化，含 0600 权限） |
| `gui/app.py:23` | `XDG_STATE_HOME` → `~/.local/state`（GUI 日志） |

Android 上 `HOME` 通常未设置，`expanduser("~")` 会退化为字面 `~` 或异常，
导致设置/最近文件/API 配置**写入失败或写到相对路径**。
**替代方案**：Flet 提供 `FLET_APP_STORAGE_DATA`（应用私有、持久）与
`FLET_APP_STORAGE_CACHE`（可被系统清理），运行期等价 API 为
`StoragePaths.get_application_data_directory()` / `get_application_cache_directory()`。
core 只需把「基目录」做成可注入（新增环境变量分支即可），**不必改调用方**。

#### P3 —— `os.chmod`（`core/engine.py:90`）

产物写出后 `chmod +x`。Android 应用私有目录下 chmod 基本无意义（且部分路径会抛
`OSError`）。建议在无 POSIX 权限语义的环境下降级为 no-op 并记录 warning。

---

## 2. GUI 重写工作量估算

### 2.1 现有 GUI 规模（实测）

| 文件 | 行数 | 职责 |
| :--- | ---: | :--- |
| `main_window.py` | 1,119 | 三栏布局、动作/工具栏/菜单、文件列表、批量转换、运行面板 |
| `dialogs.py` | 1,081 | 设置/差异/报告/运行确认/API 修复/并行修复/连接测试/关于（8 个对话框 + 3 个 QThread） |
| `highlighter.py` | 163 | 语法高亮（QSyntaxHighlighter） |
| `theme.py` | 143 | 深/浅色调色板 |
| `editor.py` | 97 | 行号编辑器 |
| `app.py` | 90 | 启动、日志重定向、图标 |
| **合计** | **2,694** | （另有 `cli.py` 979 行，不受 GUI 迁移影响） |

**布局**：横向三栏 `QSplitter`（280 / 620 / 620）+ 底部可折叠「运行输出」面板 + 状态栏
（状态文本 / 进度条 / 计数）。设置对话框覆盖 **21** 个控件，对应 `ConvertSettings` 的 **15** 个字段。

### 2.2 功能 → Flet 控件映射

| 现有（Qt） | 用途 | Flet 对应 | 风险 |
| :--- | :--- | :--- | :--- |
| `QFileDialog` | 打开文件/文件夹 | `FilePicker` | 低（Android 原生选择器） |
| `QListWidget` | 待转换文件列表（多选/右键菜单） | `ListView` + `ListTile` + `PopupMenuButton` | 低 |
| `QPlainTextEdit` + `QSyntaxHighlighter` | 源码/产物编辑器（**含高亮**） | `TextField(multiline=True)` | **中：Flet 无逐行富文本，高亮丢失** |
| `QSplitter` | 三栏可拖拽 | `Row` + `expand` | 低（失去拖拽调节宽度） |
| `QDialog` / `QMessageBox` | 设置/报告/差异/关于 | `AlertDialog` / `BottomSheet` | 低 |
| `QComboBox`/`QCheckBox`/`QSpinBox` | 设置项（21 个） | `Dropdown`/`Checkbox`/`TextField` | 低 |
| `QProgressBar` | 批量进度 | `ProgressBar`/`ProgressRing` | 低 |
| `QStatusBar` | 状态 + 计数 | 底部 `Row` / `SnackBar` | 低 |
| `QThread` 工作者（3 个） | API 修复/连接测试/并行修复 | `asyncio.to_thread` / `page.run_thread` | 低–中 |
| 差异视图（`DiffDialog`） | 并排/行内差异 | `Text` + `TextSpan`（只读富文本） | 中（需自绘） |
| `QProcess` **「运行脚本」+ stdin** | 执行生成的 .sh 并回传输出 | **无对应** | **高：Android 上不可实现** |

### 2.3 两个必须正视的功能损失

1. **「运行脚本」面板（`main_window.py:725-922`，约 200 行）在 Android 上不可实现。**
   Android 应用沙箱内没有 `/bin/bash`，也不允许任意 spawn 进程。该功能
   （运行、stdin 输入、停止、强杀、超时、输出流）只能：桌面保留 / Android 移除或标记为不可用。
2. **语法高亮丢失。** `highlighter.py` 的 163 行在 Flet 中无等价物（`TextField` 不支持逐行着色）。
   可选替代：只读的 `Text` + `TextSpan` 做**只读**高亮预览，但可编辑的高亮编辑框做不到。

### 2.4 工作量估算（**估算，非实测**，置信度 B）

| 模块 | Qt 行数 | Flet 估算 | 依据 |
| :--- | ---: | ---: | :--- |
| 启动/主题 | 233 | 100–160 | Flet `Theme`/`ColorScheme` 更声明式 |
| 主界面（布局/动作/列表/批量） | 1,119 | 550–800 | 声明式布局更短，但批量/状态机逻辑等量 |
| 设置/报告/差异/关于对话框 | ~600 | 300–450 | 表单类控件映射直接 |
| API 修复/并行/连接测试 | ~480 | 250–400 | 线程模型改 async，网络层复用 core |
| 高亮 | 163 | 0–120 | 原生不支持，仅只读近似 |
| Android 适配（存储/权限/降级提示） | — | 100–250 | **新增**（P1/P2/P3 的 UI 侧） |
| **合计** | **2,694** | **约 1,300–1,900 行** | 约为现有的 50–70%，另加适配 |

> 口径说明：以上为**静态代码量估算**，不含调试、真机联调与 Flet 1.0.0 的 API 试错成本。
> 参考量级：一次性重写约 **8–15 人日**；若要求桌面与移动双端体验对齐，需再叠加。

---

## 3. 依赖与打包风险

### 3.1 依赖现状

`pyproject.toml` 当前仅一个运行时依赖：`dependencies = ["PySide6>=6.5"]`。
**这正是本次迁移动因** —— 前次评估已实测确认 Qt 未公开发布匹配 6.11.x 的 Android wheel。

### 3.2 迁移后依赖评估

| 项 | 结论 |
| :--- | :--- |
| `flet` 版本 | **1.0.0**（PyPI 最新），`requires_python >=3.10` |
| flet 自身依赖 | `oauthlib` / `httpx` / `repath` / `msgpack` / `typing-extensions`（py<3.11） |
| 是否有二进制包 | **`msgpack` 需重点验证** —— 含 C 扩展（有纯 Python 回退），需确认 Android wheel 可得；其余（httpx/oauthlib/repath）为纯 Python |
| bat2sh 自身 | **纯 Python，无 C 扩展** → 符合 Flet「非纯包必须有 Android wheel」的要求 |
| `requires-python = ">=3.12"` | **开放区间有歧义**：Flet 的 `--python-version` 默认「取最新支持版本，或从 `project.requires-python` 解析」。建议显式固定（文档示例为 `3.13`），避免解析出不受支持的版本 |
| `extract_packages` | **不需要**（见 §1.2） |
| 打包体积 | Flet 默认产出「胖 APK」（含全部 ABI）；应用 `--split-per-abi` 或 `--arch arm64-v8a` 可显著减小 |

### 3.3 Android 打包风险清单

| # | 风险 | 等级 | 说明 |
| :--- | :--- | :--- | :--- |
| R1 | `bash -n` 校验失效且静默报通过 | **高** | 见 P1；触碰报告诚实性纪律，须先修 core |
| R2 | 「运行脚本」功能不可实现 | **高** | 见 §2.3；需产品决策（移除/降级） |
| R3 | `msgpack` 等 flet 依赖的 Android wheel | 中 | 需实测；若缺失可尝试 `extract_packages` 或替换 |
| R4 | 配置持久化路径（`~/.config`） | 中 | 见 P2；Flet 有现成存储 API，改造成本低 |
| R5 | 文件访问范围 | 中 | Android 分区存储下，能否读取用户「下载」目录里的 .bat/.ps1 需实机验证（`FilePicker` 应可，但后台/批量访问受 SAF 限制） |
| R6 | 双栈维护成本 | 中 | 若保留 Qt 桌面版则需维护两套 GUI；若全量切 Flet 则桌面体验回退（高亮、run 面板） |
| R7 | Flet 1.0.0 稳定性 | 中 | 刚发布的大版本，API 与构建链仍在演进；建议锁定版本 |

---

## 4. 环境配置检查

### 4.1 本机现状（实测）

| 组件 | 现状 | Flet 要求 | 处置 |
| :--- | :--- | :--- | :--- |
| Flutter SDK | **缺**（`flutter`/`dart` 均无） | 需要 | Flet **首次构建时自动下载**到 `$HOME/flutter/{version}` |
| Dart | 缺 | 随 Flutter | 同上 |
| JDK | **有，但为 26** | **17** | 版本不兼容 → Flet 会**自动安装 JDK 17** 到 `$HOME/java/17.x` |
| Android SDK | **缺**（`ANDROID_HOME` 未设，无 `~/Android/sdk`；`sdkmanager`/`gradle`/`aapt2` 均无） | 需要 | Flet **首次构建时自动安装**到 `~/Android/sdk` |
| `flet` CLI | **缺** | `flet build` 需要 | `pip install "flet[cli]"` |
| 磁盘 | **763 GB 可用** | — | 充足 |
| 网络 | 直连 GitHub 超时；**需代理 `127.0.0.1:10808`** | 构建需联网 | 构建前必须 `export https_proxy/http_proxy` |

**平台矩阵**：Flet 官方文档确认 **Linux 可构建 apk/aab** ✅；
**Android 目标架构**支持 `arm64-v8a` / `armeabi-v7a` / `x86_64` ✅（`--arch arm64-v8a`）。

### 4.2 需要安装的组件与预计耗时（**估算**）

| # | 组件 | 体积（估） | 说明 |
| :--- | :--- | ---: | :--- |
| 1 | `flet[cli]`（pip） | ~50 MB | 最快 |
| 2 | Flutter SDK（含 Dart） | ~1 GB | 自动下载，受代理带宽限制 |
| 3 | JDK 17 | ~200 MB | 自动安装（本机 26 不兼容） |
| 4 | Android SDK（cmdline-tools + platform + build-tools + platform-tools） | ~1–2 GB | 自动安装 |
| — | **合计** | **约 2.5–3.5 GB** | **首次构建准备约 20–60 分钟**（视代理带宽）；首次 `flet build apk` 另需 10–30 分钟 |

> 注：以上均为**官方文档所述「自动安装」行为**，本机**尚未实测**。实际耗时/成功率需一次真实构建验证（见 §6 V1）。

---

## 5. 初步结论

> # **有条件可行**

**判定依据**：

- ✅ **核心零改动可复用**：`core/` 无 Qt 依赖、全标准库、无 `__file__` 数据加载 →
  既可直接 import，也对 Flet ≥0.86 的 zipimport 安全。这是本方案最大的有利条件。
- ✅ **工具链在 Linux 上可行**：Flet 官方支持 Linux 构建 APK，且 **arm64-v8a 在支持列表内**；
  Flutter/JDK17/Android SDK 均可自动安装。
- ⚠️ **但 GUI 必须重写**（约 1,300–1,900 行），且**必然损失两个功能**：
  语法高亮（Flet 无逐行富文本）与「运行脚本」面板（Android 不可实现）。
- ❌ **一个硬前置**：`bash -n` 校验在 Android 上必然失效，**且当前会静默报「通过」**。
  这直接违反本项目「绝不输出坏 bash」与「报告诚实」的立身纪律，**必须先修 core 才能谈迁移**。

**「有条件」的三个条件**：

1. **先修 P1**（`core/syntax.py` + `ConvertReport` 增加「校验未执行」显式状态），
   使 Android 上如实显示「语法未校验」而非「通过」；
2. **对「运行脚本」与「语法高亮」做出产品决策**（Android 移除/降级 + 在发布说明中如实披露）；
3. **接受 GUI 重写成本**（约 8–15 人日量级），或先以 PoC 验证再决定。

---

## 6. 待验证项（进入实现前必须先做的实测）

| # | 待验证 | 方法 | 阻断级别 |
| :--- | :--- | :--- | :--- |
| V1 | 本机能否真正跑通 `flet build apk` | 装 `flet[cli]` → 建最小 Flet 应用 → `flet build apk --arch arm64-v8a`（需下载 ~3 GB） | **阻断**：不通过则一切免谈 |
| V2 | `msgpack`（及 flet 其余依赖）是否有 Android wheel | 构建后看日志；或在设备上导入验证 | 高 |
| V3 | `bat2sh.core` 能否在 Android 真机上 import 并完成一次转换 | PoC APK 内调用 `convert_text` | 高 |
| V4 | Flet 应用能否读取用户「下载」目录中的 .bat/.ps1 | 真机 `FilePicker` 实测（SAF 限制） | 中 |
| V5 | P1 修复方案对既有 CLI/桌面行为无回归 | 151 语料指标 + 全量 pytest | 中 |
| V6 | Flet `TextField` 在多行大文件（如 14,724 行语料）下的性能 | 真机/桌面实测 | 中 |

---

## 7. 证据与复现命令

    # 1) 分层与依赖
    grep -rn "PySide6\|PyQt\|shiboken" python/bat2sh/core/          # -> 0 处
    grep -rn "from ..gui" python/bat2sh/core/                          # -> 0 处
    grep -rn "__file__\|pkg_resources" python/bat2sh/ --include="*.py" # -> 仅 gui/app.py:53

    # 2) bash -n 在无 bash 时的静默通过（实测）
    python3 -c "
    import sys, shutil; sys.path.insert(0,'python')
    from bat2sh.core import syntax
    shutil.which = lambda n: None
    print(syntax.bash_syntax_error('这显然不是合法 bash (((('))   # -> None（= 通过）
    "

    # 3) GUI 规模
    wc -l python/bat2sh/gui/*.py                                       # -> 2,694 行

    # 4) 配置路径假设
    grep -rn "XDG_CONFIG_HOME\|expanduser" python/bat2sh/core/

---

## 8. 偏离与置信度披露（纪律 3/4/5）

| # | 项 | 说明 | 置信度 |
| :--- | :--- | :--- | :---: |
| 1 | `origin/main` 落后本地 7 个提交 | 前序 session 工作未 push；「HEAD = main tip」仅本地成立 | A |
| 2 | GUI 工作量 1,300–1,900 行为**静态估算** | 非实测；未含调试、真机联调与 Flet 1.0.0 API 试错 | **B** |
| 3 | 环境耗时 20–60 分钟为**估算** | Flet 文档称自动安装，本机**尚未实测**；受代理带宽影响大 | **B** |
| 4 | `msgpack` 的 Android wheel 状态**未实测** | 仅从依赖列表推断，需 V2 验证 | **C** |
| 5 | P1 的「静默通过」为**实测**（本地模拟 `which` 返回 None） | 但**未在真实 Android 设备**上验证 | A（本机）/ B（Android） |
| 6 | 本 session **零代码改动** | 唯一写入 = 本文档；**未 commit**，等待用户过目 | A |

---

> **评估完成，暂停等待审阅。** 不进入实现。
> 若决定推进，建议顺序：**V1（构建链 PoC）→ P1 修复（core 诚实性）→ 产品决策（run/高亮）→ GUI 重写**。
