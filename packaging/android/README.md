# bat2sh Android（Flet 最小可用版）

> **状态：可构建、可安装的 PoC。** 完整结论见 [`docs/android-poc-v2-report.md`](../../../docs/android-poc-v2-report.md)。

## 这一版做了什么

把 `python/bat2sh/core/` 直接搬进 Flet APK，加上内嵌 Termux 运行时，
在 Android 上提供 选择 → 转换 → 高亮 → 保存 → `bash -n` 校验 → 运行 的最小闭环。

| 功能 | 实现 |
| :--- | :--- |
| 选择文件 | `ft.FilePicker.pick_files(with_data=True)`，过滤 `.bat/.cmd/.ps1` |
| 转换 | `bridge.py` → `bat2sh.core.engine.convert_text`，**core 零改动** |
| 显示产物 | `ui/highlighter.py`：只读近似高亮（注释/字符串/关键字/命令/变量/数字） |
| 保存产物 | 写应用工作目录 + 尽力调 `FilePicker.save_file` 导出 |
| `bash -n` 校验 | `ui/runner.py` → 内嵌 Termux 的 `bash -n` |
| 运行脚本 | 内嵌 Termux 的 `bash <script>` |
| 显示报告 | 错误 / 警告 / TODO（core 的 `ConvertReport`） |

## 项目结构

```
packaging/android/
├── pyproject.toml          # Flet 项目定义（含 target_sdk_version = 28）
├── build.sh                # 一键构建（先 sync-core，再 flet build apk）
├── sync-core.sh            # 从 python/bat2sh/ 同步 core 到 src/bat2sh/
├── src/
│   ├── main.py             # Flet 入口（ft.run，不是 ft.app）
│   ├── termux.py           # 内嵌 Termux 运行时（解压/SYMLINKS/环境注入/入口进程）
│   ├── bridge.py           # core 调用桥（含 bash_check=False 的理由）
│   ├── ui/
│   │   ├── app.py          # 布局 + 事件 + 启动自检
│   │   ├── highlighter.py  # 只读近似高亮
│   │   └── runner.py       # 落盘 / 校验 / 运行
│   ├── bat2sh/             # 【生成物】sync-core.sh 同步而来，不入库
│   └── assets/
│       ├── bootstrap-aarch64.zip   # 【不入库】Termux bootstrap
│       ├── bootstrap-x86_64.zip    # 【不入库】
│       └── icon.png                # 由 python/bat2sh/data/bat2sh.svg 生成
└── probe-target28/         # Phase A 阻断验证探针（独立小工程）
```

## 构建

```bash
source /tmp/flet-termux-poc/env.sh
export FLET_BIN=/tmp/flet-termux-poc/.venv/bin/flet

cd packaging/android
./build.sh arm64-v8a        # 或 x86_64
```

`build.sh` 会先跑 `sync-core.sh`，再执行等价的：

```bash
flet build apk --arch arm64-v8a --yes --no-rich-output
```

产物在 `build/apk/`。

## 四个关键设计决定（都有实测依据）

### 1. targetSdk 必须是 28

`pyproject.toml` 里 `[tool.flet.android] target_sdk_version = 28`。
这不是保守，是**硬要求**：

| targetSdk | SELinux 域 | 应用私有目录内的二进制 |
| :--- | :--- | :--- |
| 36 | `u:r:untrusted_app` | `execve` 被拒（`execute_no_trans`），`bash` 无法拉起任何子进程 |
| **28** | **`u:r:untrusted_app_27`** | **直执可用，fork / 管道 / 脚本全部正常** |

代价：失去 Google Play 上架资格（侧载 PoC 无影响）。

### 2. core 零改动，但 `bash_check` 必须关掉

`bridge.default_settings()` 里设 `bash_check = False` —— 这是上一 session 点名的 P1：
`core/syntax.py` 用 `shutil.which("bash")` 找 bash，找不到就 `return None`（**静默判通过**）。
Android 上即便把 `$PREFIX/bin/bash` 放进 PATH，`subprocess.run` 也可能被沙箱拒并被同一个
`except` 吞掉，于是「校验通过」是假的。

正确做法：关掉内建校验，改由 `ui/runner.py` 显式经 Termux bash 跑 `bash -n`，
并把**是否真的校验过**如实呈现（`syntax_check()` 返回 `(checked, ok, message)` 三元组）。

### 3. 产物脚本一律用 `bash <script>` 运行，绝不依赖 shebang

core 生成的产物首行是 `#!/usr/bin/env bash`，而 Android 上 `/usr/bin/env` 不存在 ——
直接 `./x.sh` 会 ENOENT（Phase A 探针 D2 实测）。所以 `runner.run()` 恒用显式解释器。

### 4. 入口进程必须是 bash 本身

`termux.run()` 构造的是 `[bash, ...]` 或 `[/system/bin/linker64, bash, ...]`，
**绝不是** `bash -c "bash ..."`（那样内层 bash 变成子进程）。
targetSdk 28 下直执可用，linker64 仅作其他设备的兜底（`run()` 会在 `PermissionError` 时自动回退）。

## 功能范围（最小可用）

**做**：选择 / 转换 / 高亮 / 保存 / `bash -n` / 运行 / 报告。

**不做**（任务书 4.1 明确排除）：批量转换、API 修复、设置对话框、差异视图。

## 已知限制

- 产物高亮在超过 1500 行 / 8000 spans 时截断（完整内容仍会保存与运行）。
- 运行是「一次性执行 + 回显」，不是流式终端；默认超时 60 s。
- 高亮是近似实现，不追求 QSyntaxHighlighter 等价。
- 保存优先写应用私有目录，`FilePicker.save_file` 在部分 Android 版本上可能不可用；
  此时产物仍留在应用工作目录，界面会给出路径。
- 产物写到应用私有目录，其他 App 看不到；需要外传请用系统「另存为」。
- arm64-v8a 只验证了**构建**，执行验证在 x86_64 模拟器上完成（见报告「未验证项」）。