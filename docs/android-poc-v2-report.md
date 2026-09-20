# bat2sh Android —— targetSdk 28 + Termux 本体 + 最小可用版本 报告

> 会话：Android v2。起点 HEAD（锁定）= `51f4327`（= 上一 session 的 `android-poc` tip）；
> 分支 `android-poc-v2`，**未合并 main、未 bump 版本、未打 tag**。
>
> # 判定：**Phase A 通过 / Phase B 完成，APK 可安装。**

---

## 0. 结论摘要

| 项 | 结果 |
| :--- | :--- |
| 路线 | 降 targetSdk 28 + **Termux 本体**（不用 proot） |
| **Phase A：targetSdk 28 是否恢复子进程 exec / fork** | ✅ **PASS** —— 管道、外部命令、脚本内 fork、嵌套脚本调用全部 rc=0 |
| **Phase B：最小可用版本** | ✅ **完成** —— 选择 / 转换 / 高亮 / 保存 / `bash -n` / 运行 / 报告 |
| 实机验证 | ✅ Android 14（API 34）x86_64 模拟器，**启动自检通过** |
| 交付 APK | `packaging/android/build/apk/bat2sh-android-arm64-v8a.apk`（**87,179,311 B**，sha256 `314f14ed…34ed`） |
| `python/bat2sh/core/` | **零改动** |

**一句话**：上一 session 的 proot 路线死在 guest 无法 `fork`；本次把 targetSdk 降到 28，
SELinux 域从 `untrusted_app` 变成 **`untrusted_app_27`**，应用私有目录里的二进制重新可 `execve`，
于是**连 proot 都不需要**就直接拿到了完整 shell 能力 —— `bash -n` 与「运行脚本」都跑通了。

---

## 1. 前置确认（任务书 §一）

| # | 前置 | 结果 |
| :--- | :--- | :--- |
| 1 | `docs/android-poc-report.md` 存在 | ✅ 20,550 B |
| 2 | 分支 `android-poc` 存在，HEAD = `51f4327` | ✅ |
| 3 | `/tmp/flet-termux-poc/env.sh` 存在 | ✅ |
| 4 | `/tmp/flet-termux-poc/` 保留 | ✅ 未被清理，bootstrap-x86_64.zip 与上一 session 的 APK 都在 |
| 5 | 代理可用 | ✅ `curl -x 127.0.0.1:10808 https://github.com` → HTTP 200 |

补充：`/tmp` 没有被清，因此**未重新下载 bootstrap**。
aarch64 的 bootstrap 从 `packaging/android/proot-poc/src/assets/` 复用，sha256 `65ba5781…cc69`，
与上一 session 记录**逐字节一致**。

环境：Flet **1.0.0** / Flutter **3.44.8** / Python **3.14.7** / JDK 17；
设备：**Android 14（API 34）x86_64 模拟器 `poc34`**。

---

## 2. 分支

```
git checkout android-poc && git checkout -b android-poc-v2      # HEAD 51f4327
```

未合并 main、未 bump 版本、未打 tag。

---

## 3. Phase A：targetSdk 28 + Termux 本体（阻断验证）

### 3.1 探针设计

`packaging/android/probe-target28/` 是一个独立的极小 Flet 工程，只做一件事：
解压 Termux bootstrap，然后跑 10 组探针，结果同时进 UI 与 logcat（tag `flet.python`）。

关键是**去掉 proot**：只用 `linker64` / 直执 + Termux bootstrap。

### 3.2 结果（全绿）

| # | 探针 | rc | 说明 |
| :--- | :--- | ---: | :--- |
| A | 直执 `<PREFIX>/bin/bash -c "echo direct-ok; id"` | **0** | **不经 linker64 也能 exec** |
| B | `linker64 bash -c "echo hello; id; uname -a"` | 0 | 上一 session 的老路仍可用 |
| C | `ls $PREFIX/bin \| head -5 \| while read x; do echo L=$x; done` | **0** | 管道 + 外部命令 |
| C2 | `echo abc \| cat \| tr a-z A-Z \| wc -c` | **0** | 三段管道 |
| D | `bash probe-good.sh`（脚本内含 ls/head/tr/wc 与循环） | **0** | **脚本内 fork** |
| D2 | `./probe-good.sh`（直接执行，靠 shebang） | ENOENT | 见 §3.4 |
| D3 | `bash probe-outer.sh`，内层再 `bash probe-good.sh` | **0** | **嵌套 fork** |
| E | `for f in a b c; do echo i=$f; done \| tr a-z A-Z` | **0** | 循环 + 管道 + 外部命令 |
| F | `bash -n probe-good.sh` | 0 | 合法脚本 |
| G | `bash -n probe-bad.sh` | **2** | **能正确检出语法错误**（stderr 给出 `syntax error: unexpected end of file`） |
| H | `echo $PREFIX / $PATH / $LD_LIBRARY_PATH; pwd; id` | 0 | 环境注入正确 |

**判据（任务书 §3.2）**：

| 判据 | 通过条件 | 实测 |
| :--- | :--- | :--- |
| 子进程 + 管道 | rc=0 | ✅ C / C2 / E 全 rc=0 |
| 脚本内 fork | rc=0 | ✅ D / D3 全 rc=0 |

### 3.3 根因：SELinux 域随 targetSdk 变化

两次实测的对照（同一台设备、同一个应用私有目录）：

| targetSdk | 应用 SELinux 域 | `app_data_file` 的 execve |
| :--- | :--- | :--- |
| 36（上一 session） | `u:r:untrusted_app:s0` | **denied** `{ execute_no_trans }` |
| **28（本次）** | **`u:r:untrusted_app_27:s0`** | **granted** `{ execute_no_trans }` |

本次的 AVC 证据（`io.github.bat2sh_android` 启动自检时）：

```
avc:  granted  { execute_no_trans }  path="/data/user/0/io.github.bat2sh_android/files/data/usr/bin/bash"
                                    scontext=u:r:untrusted_app_27:s0:c196,...
                                    tcontext=u:object_r:app_data_file:s0:c196,...  tclass=file
```

注意 `execute_no_trans` 已经是 **granted** —— 与上一 session 的 `denied` 正好相反。
这就是全部差别的来源。

### 3.4 两个顺带确认的事实

1. **直执即可，linker64 不再是必需**。targetSdk 28 下 `<PREFIX>/bin/bash` 可以直接
   `subprocess.run([bash, ...])`。本次实现仍保留 linker64 兜底（`Termux.run()` 在
   `PermissionError` 时自动回退），因为别的设备 / 别的 targetSdk 未必如此。
2. **shebang 在 Android 上不可用**。core 生成的产物首行是 `#!/usr/bin/env bash`，
   而 Android 上没有 `/usr/bin/env`，所以 `./x.sh` 会 ENOENT（探针 D2）。
   **实现上必须恒用 `bash <script>` 显式解释**，不能依赖 shebang。
   （置信度 B：ENOENT 与「解释器不存在」一致，未再单独构造 `#!<PREFIX>/bin/bash` 的对照实验。）

### 3.5 判定

> **Phase A PASS。** 完整 shell 能力（fork / 管道 / 外部命令 / 脚本 / `bash -n`）全部可用，
> 且**不需要 proot**。按任务书 §3.3 进入 Phase B。

---

## 4. Phase B：最小可用版本

### 4.1 项目结构

```
packaging/android/
├── pyproject.toml          # Flet 项目定义（target_sdk_version = 28）
├── build.sh                # 一键构建（sync-core -> flet build apk）
├── sync-core.sh            # 从 python/bat2sh/ 同步 core 到 src/bat2sh/
├── src/
│   ├── main.py             # Flet 入口（ft.run，不是 ft.app）
│   ├── termux.py           # 内嵌 Termux 运行时
│   ├── bridge.py           # core 调用桥
│   ├── ui/{app,highlighter,runner}.py
│   ├── bat2sh/             # 【生成物】sync-core.sh 同步，不入库
│   └── assets/{bootstrap-aarch64.zip,bootstrap-x86_64.zip,icon.png}
├── probe-target28/         # Phase A 探针（独立工程）
└── README.md
```

与任务书 §4.2 的差异：多了 `sync-core.sh` / `build.sh` / `probe-target28/`；
`assets/icon.png` 由 `python/bat2sh/data/bat2sh.svg` 用 rsvg-convert 生成（512×512）。

### 4.2 四个关键设计决定（都有实测依据）

#### (1) `targetSdk = 28` 是硬要求

见 §3.3。代价是失去 Google Play 上架资格 —— 对侧载 PoC 无影响。

#### (2) core 零改动，但 `bash_check` 必须关掉（关闭 P1）

`bridge.default_settings()` 里设 `bash_check = False`。理由：
`core/syntax.py::bash_syntax_error()` 用 `shutil.which("bash")` 找 bash，**找不到就 return None**
（静默判通过）。Android 上即便把 `$PREFIX/bin/bash` 放进 PATH，`subprocess.run` 也可能被沙箱拒，
而那个 `OSError` 会被同一个 `except` 吞掉 —— 「校验通过」是假的。

实现：关掉内建校验，改由 `ui/runner.py` 显式经 Termux bash 跑 `bash -n`，
并让 `Termux.syntax_check()` 返回 `(是否真的跑了校验, 是否通过, 信息)` 三元组，
把「未执行」和「通过」严格区分开。**P1 由此关闭。**

#### (3) 运行产物恒用 `bash <script>`

见 §3.4 第 2 点。`ui/runner.py::ScriptRunner.run()` 不接受 shebang 路径。

#### (4) 入口进程必须是 bash 本身

`Termux.argv()` 构造 `[bash, ...]` 或 `[linker64, bash, ...]`，**绝不**是 `bash -c "bash ..."`。

### 4.3 打包 core 的方式（任务书 §4.4）

采用「复制到 `src/bat2sh/`」，但**由脚本在构建时生成**而不是提交一份拷贝：

- `sync-core.sh` 从 `python/bat2sh/` 同步 `__init__.py` + `core/` + `mappings/` + `data/`（29 个文件，608 KB）；
- **不同步** `gui/`（依赖 PySide6）、`cli.py`、`__main__.py`（桌面 CLI 入口）。
- `src/bat2sh/` 在 `.gitignore` 里排除，**单一事实来源始终是 `python/bat2sh/`**，从根上杜绝两份代码漂移。

为什么要 `mappings/`：`core/batch.py` 有 `from ..mappings import output_contracts, windows_names, windows_tools`，
少一个目录就会 ImportError。

### 4.4 功能实现对照（任务书 §4.1）

| # | 必须项 | 实现 |
| :--- | :--- | :--- |
| 1 | 选择文件（.bat/.cmd/.ps1） | `FilePicker.pick_files(with_data=True)`，`allowed_extensions=[bat,cmd,ps1]`；字节流交给 `core.encoding.decode_bytes` 处理 GBK/BOM |
| 2 | 转换 | `bridge.convert()` → `core.engine.convert_text` |
| 3 | 显示产物（只读 + 近似高亮） | `ui/highlighter.py`，逐行扫描，7 类着色（注释/字符串/关键字/命令/变量/数字/普通） |
| 4 | 保存产物 | 写应用工作目录（`files/data/work/`）+ 尽力调 `FilePicker.save_file(src_bytes=...)` 导出 |
| 5 | `bash -n` 校验 | `ui/runner.py` → Termux bash（三元组返回，区分「未执行」） |
| 6 | 运行脚本 | `ui/runner.py` → `bash <script>`，默认超时 60 s |
| 7 | 显示报告 | core 的 `ConvertReport` → 错误 / 警告 / TODO，各限 80 条 |

**不做**（任务书明确排除）：批量转换、API 修复、设置对话框、差异视图。

UI 布局按 §4.5 的上下两栏（工具栏 / 源代码 / 产物 / 报告），未做三栏。

### 4.5 验证（仪器先验证）

#### (a) 桌面 smoke test（构建前，先排除低级错误）

用 Flet venv 的 Python 直接 import 并跑通整条链路：

```
bridge.convert(demo.bat)   -> ok, 6 行 -> 转换 5 / 未变 1；警告 1
bridge.convert(demo.ps1)   -> ok, SourceKind.POWERSHELL
bridge.convert(demo.txt)   -> 正确拒绝：不支持的文件类型
decode_source(GBK 字节)     -> enc=gbk, 中文正确
highlighter.build_spans()  -> 57 spans，5 类颜色都出现
runner.stage + syntax_check -> 合法 PASS / 非法 FAIL（报出 syntax error）
```

#### (b) 模拟器实机（x86_64，Android 14）

应用的**启动自检**（复用按钮走的同一条链路：`bridge.convert` → `runner.stage` →
`runner.check` → `runner.run`）实测输出：

```
[11:57:30] Termux 运行时：runtime ready
[11:57:30] 入口方式：direct  rc=0
[11:57:30] READY
GNU bash, version 5.3.15(1)-release (x86_64-pc-linux-android)
uid=10196(u0_a196) ... context=u:r:untrusted_app_27:s0:c196,c256,c512,c768
[11:57:30] 工作目录：/data/user/0/io.github.bat2sh_android/files/data/work
[11:57:30] --- 启动自检 ---
[11:57:30] 转换 OK：转换完成：Windows 批处理  4 行 -> 转换 3 / 未变 1；错误 0 / 警告 0 / TODO 0
[11:57:30] bash -n：PASS bash -n 通过（direct）
[11:57:30] 运行 rc=0 via direct
[11:57:30] hello from bat2sh
[11:57:30] item 1
[11:57:30] item 2
[11:57:30] item 3
[11:57:30] --- 自检通过 ---
```

即：**转换 → `bash -n` → 运行（含 `for` 循环，需要 fork）在同一次启动内全部成功**。
UI 渲染与布局已用截图确认（工具栏 / 源代码 / 产物 / 报告四区，产物区为深色高亮面板）。

### 4.6 过程中修掉的三个真 bug（都是靠上面这套仪器发现的）

| # | 现象 | 根因 | 修法 |
| :--- | :--- | :--- | :--- |
| 1 | 应用启动即 TypeError | `ft.TextField` **没有** `font_family` 字段（Flet 1.0） | 改用 `text_style=ft.TextStyle(font_family=MONO)` |
| 2 | 产物面板塌成一条竖线 | `Container(expand=True)` 在 Column 里只作用于主轴，交叉轴收缩到子元素宽度；而空产物时 Text 宽为 0 | 去掉 `expand`，并把整页包进 `Column(horizontal_alignment=STRETCH)`（Flet 1.0 的 `Page` 没有 `horizontal_alignment`） |
| 3 | 日志两行首尾相连 | `_log` 把分隔用 `chr(10)` 加在了**新行之后**而不是之前 | 改成 `old + chr(10) + line` |

---

## 5. 交付物

### 5.1 APK

| 项 | arm64-v8a（交付） | x86_64（模拟器验证用） |
| :--- | :--- | :--- |
| 路径 | `packaging/android/build/apk/bat2sh-android-arm64-v8a.apk` | `packaging/android/build/apk/bat2sh-android-x86_64.apk` |
| 大小 | **87,179,311 字节**（83.1 MiB） | **88,983,582 字节**（84.9 MiB） |
| sha256 | `314f14edf07fd3f503106b714fc420986c44612329fd5e49ec8c3620680134ed` | `e0452df7c9da9a354605a57ffba839daca992bcba10f14d516a7725a3b5c24b8` |
| ABI | arm64-v8a | x86_64 |
| targetSdk | 28 | 28 |
| 包名 / 版本 | `io.github.bat2sh_android` / versionName 2.8.1 | 同 |
| 签名 | debug 签名 | debug 签名 |

APK 里只带**本 ABI 的 bootstrap**（`build.sh` 用 `--exclude` 排掉另一份 32 MB），
否则体积会翻到 119 MB。

### 5.2 代码

`packaging/android/`：完整 Flet 工程 + `build.sh` / `sync-core.sh` + Phase A 探针。
另有 `packaging/android/proot-poc/`（上一 session 的 proot 探针，保留）。

### 5.3 文档

本文件 `docs/android-poc-v2-report.md`。

---

## 6. 用户测试指南

### 6.1 安装

```bash
# 手机开启「允许安装未知来源应用」，然后二选一：

# (a) adb
adb install -r -t packaging/android/build/apk/bat2sh-android-arm64-v8a.apk

# (b) 直接把 APK 传到手机点击安装
```

校验下载完整性：

```bash
sha256sum bat2sh-android-arm64-v8a.apk
# 期望 314f14edf07fd3f503106b714fc420986c44612329fd5e49ec8c3620680134ed
```

首次启动会解压 32 MB 的 Termux 运行时（约数秒），状态栏会显示
「就绪（入口进程：direct）」。

### 6.2 五分钟验收清单

| # | 操作 | 期望 |
| :--- | :--- | :--- |
| 1 | 打开应用，看「报告 / 运行输出」面板 | 看到 `--- 启动自检 ---` … `--- 自检通过 ---`，其中 `bash -n：PASS`、`运行 rc=0` |
| 2 | 点「选择文件」，选一个 `.bat` 或 `.ps1` | 状态栏显示「已载入 xxx（N 字节，编码 utf-8/gbk）」 |
| 3 | 点「转换」 | 产物区出现彩色 bash 代码；报告区显示「错误 x / 警告 y / TODO z」 |
| 4 | 点「校验」 | 状态栏「bash -n 通过」 |
| 5 | 点「运行」 | 报告区追加脚本的真实输出与 `[rc=0 via direct]` |
| 6 | 点「保存」 | 报告区给出应用目录路径；若系统另存为可用，会再导出到你选的位置 |

### 6.3 复现 Phase A（可选）

`packaging/android/probe-target28/` 是独立的探针工程，装到手机上会打印 A–H 十组探针结果：

```bash
cd packaging/android/probe-target28
$FLET_BIN build apk --arch arm64-v8a --yes --no-rich-output
adb install -r -t build/apk/*.apk
adb logcat -d | grep flet.python
```

---

## 7. 已知限制

| # | 限制 |
| :--- | :--- |
| 1 | **targetSdk 28** —— 不满足 Google Play 上架要求（侧载无影响） |
| 2 | 产物高亮超过 1500 行 / 8000 spans 会截断（完整内容仍会保存与运行） |
| 3 | 运行是「一次性执行 + 回显」，不是流式终端；默认超时 60 s |
| 4 | 高亮是近似实现，不追求 QSyntaxHighlighter 等价 |
| 5 | 产物默认写在应用私有目录（`files/data/work/`），其他 App 看不到；外传需用系统「另存为」 |
| 6 | 产物脚本的 `#!/usr/bin/env bash` 在 Android 上无效，**不能** `./x.sh` 直接跑；应用内运行已用 `bash <script>` 规避 |
| 7 | 无批量 / 无 API 修复 / 无设置对话框 / 无差异视图（任务书明确排除） |
| 8 | `FilePicker.save_file` 在部分 Android 版本可能不可用，此时只有应用目录副本 |
| 9 | APK 体积 87 MB（Termux bootstrap 占 32 MB） |

---

## 8. 待验证项

| # | 项 | 状态 |
| :--- | :--- | :--- |
| 1 | **arm64-v8a 真机执行** —— 本次执行验证全部在 x86_64 模拟器上完成；arm64 只验证了**构建**（APK 含 `lib/arm64-v8a/*` 与 `assets/bootstrap-aarch64.zip`，targetSdk 28） | **未验证** |
| 2 | `FilePicker.pick_files` / `save_file` 在真机（Android 13/14/15 SAF）上的实际行为 | 未验证（模拟器未点选文件） |
| 3 | shebang ENOENT 的根因（推断为 `/usr/bin/env` 不存在） | 置信度 B |
| 4 | 大脚本（数千行）的转换耗时与高亮性能 | 未验证 |
| 5 | Android 15/16 是否仍允许 targetSdk 28 安装 | 未验证（Android 14 已确认可装） |
| 6 | 长时间运行的脚本（>60 s）与中断行为 | 未验证 |

---

## 9. 偏离与置信度披露（纪律 3 / 7）

| # | 项 | 说明 | 置信度 |
| :--- | :--- | :--- | :---: |
| 1 | `docs/flet-migration-assessment.md` 仍为未跟踪 | 前序 session 遗留，本次同样未提交 | A |
| 2 | **`probe-target28/` 是任务书没要求的** | 但 §3.2 要求「最小探针」，且 Phase A 是阻断门，需要一个可复现的仪器；已单独成目录，不污染主工程 | A |
| 3 | **core 用脚本同步而不是提交拷贝** | 任务书 §4.4 给了「复制到 src/bat2sh/」与「Flet 依赖机制」两个选项；本次取「复制」，但由 `sync-core.sh` 在构建时生成并 gitignore，以确保单一事实来源 | A |
| 4 | **启动自检会写进报告面板** | 不是任务书要求的功能，但它让用户一打开就能确认运行时是否可用，也让本报告的证据可被用户自行复现。无 UI 变更（不新增按钮） | A |
| 5 | `--exclude` 另一 ABI 的 bootstrap | 任务书没提；纯粹为把 APK 从 119 MB 降到 87 MB | A |
| 6 | 探针 D2（`./x.sh`）**失败**但 Phase A 仍判 PASS | 因为它是 shebang 解析问题，不是 fork/exec 能力问题；判据（§3.2）只要求管道的 rc=0 与脚本内 fork 的 rc=0，二者都满足 | A |
| 7 | 首次 Phase A 判据表曾误判 FAIL | 初版探针用了 `ls /` 与 `ls /bin`（沙箱外路径，Permission denied），是我的探针设计错误；改用沙箱内路径重跑后全绿。**报告以重跑结果为准**，此处如实披露 | A |
| 8 | 未修改 `python/bat2sh/core/` | 纪律 1 | A |
| 9 | 只依赖 Flet + 标准库 | 纪律 2（`core` 本身零第三方依赖；UI 层只用 flet 与 stdlib） | A |

---

## 10. 复现命令

```bash
# 0) 环境
source /tmp/flet-termux-poc/env.sh
export FLET_BIN=/tmp/flet-termux-poc/.venv/bin/flet      # Flet 1.0.0

# 1) bootstrap（若 /tmp 被清才需要；aarch64 的 sha256 应为 65ba5781…cc69）
TAG='bootstrap-2026.09.20-r1%2Bapt.android-7'
curl -sSL -o packaging/android/src/assets/bootstrap-aarch64.zip \
  "https://github.com/termux/termux-packages/releases/download/$TAG/bootstrap-aarch64.zip"

# 2) 构建（sync-core -> flet build apk，自动只带本 ABI 的 bootstrap）
cd packaging/android
./build.sh arm64-v8a          # 或 x86_64

# 3) 装机 + 看启动自检
adb install -r -t build/apk/bat2sh-android-arm64-v8a.apk
adb logcat -c && adb shell monkey -p io.github.bat2sh_android -c android.intent.category.LAUNCHER 1
sleep 30 && adb logcat -d | grep flet.python

# 4) 确认 SELinux 已放行 execve（本次的关键证据）
adb logcat -d | grep -iE 'avc:.*(execute|execute_no_trans)'
#   期望看到 granted { execute_no_trans } ... scontext=u:r:untrusted_app_27
```

模拟器（x86_64）：

```bash
$ANDROID_HOME/emulator/emulator -avd poc34 -no-window -no-audio -no-boot-anim \
    -gpu swiftshader_indirect -accel on &
adb wait-for-device && adb install -r -t build/apk/bat2sh-android-x86_64.apk
```

---

## 11. 证据文件

| 位置 | 内容 |
| :--- | :--- |
| `packaging/android/build/apk/bat2sh-android-arm64-v8a.apk` | 交付 APK（87,179,311 B） |
| `packaging/android/build/apk/bat2sh-android-x86_64.apk` | 模拟器验证用 APK |
| `packaging/android/probe-target28/` | Phase A 探针工程（源码） |
| `/tmp/bat2sh-app4.png` / `/tmp/bat2sh-final.png` | 应用界面截图（布局 + 日志格式修复后） |
| `adb logcat` tag `flet.python` | 启动自检与探针的完整原始输出 |

---

> **结论：Phase A 通过，Phase B 完成。** targetSdk 降到 28 后 SELinux 域变为
> `untrusted_app_27`，应用私有目录内的二进制恢复 `execve`，
> **Termux 本体（不用 proot）就提供了完整 shell 能力**：
> 转换 → `bash -n` → 运行 的闭环已在 Android 14 模拟器上实测跑通。
> **交付 APK 87,179,311 B（sha256 `314f14ed…34ed`），等用户安装测试。**
