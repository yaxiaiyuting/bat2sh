# bat2sh —— Flet + 内嵌 Termux 运行时 PoC 报告

> 会话：Flet + Termux PoC。起点 HEAD（锁定）= `01f61b5`；**全程只读仓库**，
> PoC 全部在 `/tmp/flet-termux-poc/` 内完成。
> 目的：验证「Flet APK 内嵌 Termux 运行时 + 调用 bash」的可行性（Q1/Q2/Q3）。
>
> # 判定：**Q1 通过 / Q2 部分通过（bat2sh 关键路径通过）/ Q3 通过**
> ## —— **方案二成立，P1 不再是阻断项。**

---

## 0. 结论摘要（按任务书口径）

| 项 | 结果 |
| :--- | :--- |
| bootstrap zip 来源 + 大小 | `termux/termux-packages` release `bootstrap-2026.09.20-r1+apt.android-7`；aarch64 **32,806,628 字节**（sha256 `65ba5781…3cc69`）/ x86_64 32,718,564 字节 |
| APK 内是否含 bootstrap | **是** —— 位于 `assets/app.zip → assets/bootstrap-aarch64.zip` |
| 解压后 bash 路径 | `/data/user/0/org.example.flet_termux_poc/files/data/usr/bin/bash` |
| **bash 可执行** | **是**（须经 `/system/bin/linker64` 作为入口进程） |
| **`bash -n` 可用** | **是** —— 合法脚本 rc=0；非法脚本 rc=2 且给出正确语法错误 |
| Flet 终端 UI | **可行**（UI 渲染 + 异步回显 + 交互执行均已实机验证） |
| 真机验证 | **是** —— Android 14（API 34）x86_64 模拟器，KVM 加速 |
| APK 体积 | arm64-v8a **82.8 MB**（86,877,015 字节）/ x86_64 **84.6 MB**（88,681,158 字节） |
| **Q1 / Q2 / Q3 判定** | **PASS / 部分通过 / PASS** |

---

## 1. 前置确认

| # | 前置 | 结果 |
| :--- | :--- | :--- |
| 1 | `docs/flet-poc-report.md` 存在，V1 判定「通过」 | ✅ |
| 2 | `git status` 干净 | ⚠️ 无已跟踪文件改动；仍有未跟踪的 `docs/flet-migration-assessment.md`（见 §8 偏离 1） |
| 3 | 起点 HEAD | ✅ `01f61b5`（比任务书写的 `905cf16` 新一个提交，即 V1 报告那次） |
| 4 | 磁盘 ≥ 15 GB | ✅ `/home` 750 GB 可用 |
| 5 | 代理可用 | ✅ `curl -x 127.0.0.1:10808 https://github.com` → HTTP 200 |
| 6 | 参考项目已读 | ✅ 两个仓库均存在并已读取 README（GitHub API 被限流，改用 raw 页面） |

**参考项目关键情报（本次 PoC 直接受益）**：

- `kelai141/dsh-mobile-apk`：内嵌 **Termux 运行时快照**（xz 格式，非标准 bootstrap），WebView UI，内置 bash 控制台。
- `deepcode-lab/deepseek-harness-mobile`：内嵌 **Debian glibc rootfs + proot**，并给出本次最关键的两条工程细节：
  - `SnapshotExtractor`：「xz-tar extraction: **W^X write-bit strip**、**exec-attribute stamp**」；
  - 「If direct exec is denied (`Permission denied`, Android 15+), the process is spawned through **`/system/bin/linker64`** instead.」

---

## 2. Q1：bootstrap 能否作为 Flet asset 打包 —— **PASS**

### 2.1 首次尝试失败（重要教训）

按任务书给的结构（`assets/` 在项目根 + `src/main.py`）首次构建，APK **53 MB**，
与 V1 的 Hello World 一样大 —— `unzip -l | grep bootstrap` **找不到任何条目**。

根因（源码 `flet_cli/commands/build_base.py:2047`）：

    self.package_app_path = python_app_path + pyproject["tool.flet.app.path"]
    self.assets_path = self.package_app_path.joinpath("assets")   # ← 相对 app.path

即 **assets 目录是相对 `[tool.flet.app].path` 解析的**。我把 app.path 设成 `src` 之后，
Flet 找的是 `src/assets/`，而我把 bootstrap 放在了项目根的 `assets/` —— 被静默忽略。

**修正**：bootstrap 放到 `src/assets/`。重构建后 APK 由 53 MB → **83 MB**。

### 2.2 打包形态（与直觉不同）

bootstrap **不是**以独立条目出现在 APK 里，而是被打进 **`assets/app.zip`**（Flet 的 Python 应用包）：

    assets/app.zip  (32,824,441 字节)
      ├── assets/bootstrap-aarch64.zip   (32,806,628 字节)
      └── main.pyc                       (17,813 字节)

**运行时**：Flet 会把 `app.zip` 解压到应用私有目录，实测路径为

    /data/user/0/<pkg>/files/flet/app/assets/bootstrap-x86_64.zip

该路径通过环境变量 `FLET_ASSETS_DIR` 暴露（`flet/app.py:728`），应用内应优先读它。

> **Q1 判定：PASS** —— bootstrap 确实随 APK 分发，且运行时可定位。

---

## 3. Q2：解压并调用 bash —— **部分通过（关键路径通过）**

### 3.1 解压：成功，但必须自己处理 SYMLINKS.txt

首次解压实测：

    解压完成: 文件 3773 / 符号链接 1215 / 设执行位 510

**关键陷阱**：bootstrap zip **不含符号链接**，而是用一个 `SYMLINKS.txt`（1213 行）记录。
若不处理，bash 连自己的依赖库都找不到 —— 例如 `lib/libreadline.so.8` 在 zip 里**不存在**
（只有实体 `libreadline.so.8.2` 之类），全靠符号链接补出来。

格式经 **Termux 官方安装器源码**确证（`termux-app/app/src/main/java/com/termux/app/TermuxInstaller.java`）：

    String[] parts = line.split("←");
    String oldPath = parts[0];                                  // 链接**目标**（readlink 值，相对链接所在目录）
    String newPath = TERMUX_STAGING_PREFIX + "/" + parts[1];    // **链接路径**（相对 $PREFIX）

即 **`<target>←<linkpath>`**。（我最初按 `<linkpath>←<target>` 猜测，实测证伪后改用官方口径。）

**另两个结构要点**：
- zip 的**根目录就是 `$PREFIX`**（含 `bin/ lib/ etc/ libexec/ share/ tmp/ var/`），
  因此必须解压到 `<DATA>/usr`，才会得到 `<DATA>/usr/bin/bash` —— 任务书骨架的假设正确。
- 可执行位需自行设置（W^X：**去写位 + 加执行位**），本次设了 510 个。

### 3.2 执行：直执被拒 → linker64 绕过部分生效

**直接 exec 被拒（实测）**：

    直接执行 被拒: [Errno 13] Permission denied:
      '/data/user/0/.../files/data/usr/bin/bash'

根因：APK 的 `targetSdkVersion=36`（logcat 可见 `target_sdk_version=36`，release 包）。
Android 对 targetSdk ≥ 29 的应用禁止 exec 应用数据目录内的文件（W^X）。

**linker64 绕过（实测部分生效）**：

    [LINKER64, BASH, "-c", cmd]   →  bash 成功启动，rc=126
      stdout: hello                       ← echo 是 bash 内建，**执行成功**
      stderr: .../bin/bash: line 1: .../bin/head: Permission denied
              .../bin/bash: line 1: .../bin/bash: Permission denied

即：**入口进程能跑起来**（内建命令生效），但 **bash 拉起的子进程一律被拒**。

**尝试 termux-exec 钩子：库在，但无效。**
bootstrap 内确实带 exec 钩子（`SYMLINKS.txt` 有 `libtermux-exec-ld-preload.so←./lib/libtermux-exec.so`），
我也注入了 `LD_PRELOAD=<PREFIX>/lib/libtermux-exec.so`，但子进程 exec **仍被拒**。
推断原因是 Android 对高 targetSdk 应用的 `LD_PRELOAD`/`LD_LIBRARY_PATH` 施加了额外限制
（Termux 本体长期维持低 targetSdk 正是为此）。**此项未做进一步验证**，见 §6 V2。

### 3.3 **关键结果：`bash -n` 作为入口进程直接调用 —— 完全可用**

这是 bat2sh 的核心需求，且**不需要任何子进程**（`-n` 只做解析）。实测（截图 screen3）：

| 用例 | 结果 |
| :--- | :--- |
| `linker64 bash -n 合法.sh` | **PASS，rc=0** |
| `linker64 bash -n 非法.sh` | **PASS，rc=2**，stderr：`syntax error: unexpected end of file from \`if' command on line 1` |

> **调用方式的决定性差异**：
> - ❌ `bash -c "bash -n file"` —— 内层 bash 是**子进程**，被拒（rc=126）。
> - ✅ `/system/bin/linker64 <PREFIX>/bin/bash -n file` —— bash 是**入口进程**，成功。
>
> 因此 bat2sh 在 Android 上必须**直接**用 linker64 调用 `bash -n`，不能经由外层 shell。

> **Q2 判定：部分通过** —— bash 可执行、`bash -n` 完整可用（含错误检出）；
> 但 bash 内的**外部命令执行（子进程 exec）不可用**。

---

## 4. Q3：Flet 终端交互界面 —— **PASS**

已在模拟器上实机验证（截图 screen1/2/4）：

- **UI 渲染正常**：标题、状态行、自检报告区、命令输入框、「执行」按钮、输出区，布局与桌面一致。
- **交互执行正常**：输入 `echo` → 点击「执行」→ 输出区异步追加
  `$ echo` / `[rc=0 via linker64]`，即 `subprocess` + 后台线程 + `page.update()` 的链路可用。
- 自检结果本身就是在 UI 中呈现的（含多行 stderr 换行），说明多行只读 `TextField` 足以承担终端回显。

> **Q3 判定：PASS**。补充：本次用的是「整条命令一次性执行 + 回显」模式；
> 若要真正的**流式**终端（逐行 readline），需 `subprocess.Popen` + 读线程 + 节流 `update()`，本次未做。

---

## 5. 途中发现的 Flet 1.0.0 变更（对迁移有直接影响）

| # | 问题 | 结论 |
| :--- | :--- | :--- |
| 1 | `ft.app(main)` | **Flet 1.0.0 已移除**，正确入口是 **`ft.run(main)`**（`flet/__init__.py` 的 `_LAZY` 表 + `flet/app.py:68`） |
| 2 | `ft.ElevatedButton` | **已移除**，改用 `ft.FilledButton` / `ft.Button` |
| 3 | assets 位置 | 必须在 **`<app.path>/assets`**（本次即 `src/assets/`），放项目根会被静默忽略 |
| 4 | 入口文件 | 默认要求 **项目根**的 `main.py`；用 `src/` 需 `[tool.flet.app] path="src"` |

> ⚠️ **对 V1 报告的重要修正**：V1 的 Hello World 用的也是 `ft.app(main)`，
> 而 V1 **从未真正运行过 APK**（当时无设备）。本次实机证明：**V1 那个 APK 一启动就会崩溃**
> （`AttributeError: module 'flet' has no attribute 'app'`）。
> 这印证了 V1 报告里「能打包 ≠ 能用」的告警 —— **V1 的「通过」仅证明构建链可用，不代表产物可运行。**

---

## 6. 风险清单更新（对照任务书 §四）

| # | 原风险 | 实测结论 |
| :--- | :--- | :--- |
| R1 | bootstrap 解压后路径结构 | ✅ **已确认**：zip 根 = `$PREFIX`，解压到 `<DATA>/usr` 得 `usr/bin/bash`；**但必须另行处理 SYMLINKS.txt** |
| R2 | bash 运行时依赖 | ⚠️ **部分确认**：`LD_LIBRARY_PATH=<PREFIX>/lib` + `PREFIX`/`PATH` 注入后**入口 bash 可跑**；但**子进程 exec 被拒**，termux-exec 钩子无效 |
| R3 | Android 10+ 执行限制 | ⚠️ **确认存在**，`linker64` 绕过对**入口进程**有效、对**子进程无效** |
| R4 | APK 体积 | ✅ **确认**：+30 MB（53 → 83 MB）；arm64 82.8 MB、x86_64 84.6 MB |
| R5 | 无真机 | ✅ **已解除**：本机 `/dev/kvm` 可用，用 Android 14 x86_64 模拟器完成实机验证 |

---

## 7. 对 bat2sh 的意义

### 7.1 P1 不再是阻断项

评估中的 P1 是「Android 无 bash → `bash -n` 静默报通过」。本次实测证明
**内嵌 Termux 的 `bash -n` 在 Android 上完全可用且能正确检出语法错误** ——
P1 的 Android 侧前置条件已满足。

但**实现上有三条硬约束**，必须写进设计：

1. 必须用 `/system/bin/linker64 <PREFIX>/bin/bash -n <file>` 作为**入口进程**调用；
   不可写成 `bash -c "bash -n file"`（子进程会被拒）。
2. 必须自行解压 + **处理 SYMLINKS.txt** + **设执行位（去写位）**；naive `extractall` 必然产出坏运行时。
3. 必须注入 `PREFIX` / `PATH` / `LD_LIBRARY_PATH` / `HOME` / `TMPDIR`。

### 7.2 仍然不可用的能力

- **「运行生成的脚本」**（bat2sh 现有 GUI 的 run 面板）：需要 `sh`/`chmod` 等**子进程**，
  在当前 targetSdk 下不可用。若必须保留，需走 **proot 方案**（参考 deepseek-harness-mobile）
  或**降低 targetSdk**（Termux 路线，需另行验证）。
- **任意 shell 会话**（`ls`/`cat` 等）：同上。

### 7.3 建议的下一步

| 优先级 | 事项 |
| :--- | :--- |
| P0 | 把 `bash -n` 的 linker64 调用方式与 SYMLINKS 解压逻辑固化为 `core/` 的 Android 适配层（并加「校验未执行」显式状态，彻底关闭 P1） |
| P1 | **V2 验证**：降低 targetSdk（或 proot）能否恢复子进程 exec —— 这决定 run 功能与终端体验能否保留 |
| P2 | per-ABI bootstrap 分发策略（当前一次构建只含一个 ABI 的 bootstrap，arm64 包无法在 x86_64 上跑，反之亦然） |

---

## 8. 偏离与置信度披露（纪律 3/4）

| # | 项 | 说明 | 置信度 |
| :--- | :--- | :--- | :---: |
| 1 | `docs/flet-migration-assessment.md` 仍为**未跟踪** | 前序 session 遗留；按「唯一 commit = 报告」未一并提交 | A |
| 2 | 起点 HEAD 为 `01f61b5`（非 `905cf16`） | 任务书写「或最新」，取最新 | A |
| 3 | **Q2 用 x86_64 而非 arm64-v8a 验证执行** | 模拟器为 x86_64；arm64 的**打包**已单独验证（Q1，83 MB APK），但**arm64 上的执行未验证** | **A（已知限制）** |
| 4 | `libtermux-exec.so` 无效的**根因未最终确证** | 推断为高 targetSdk 对 `LD_PRELOAD` 的限制，未做降 targetSdk 对照实验 | **B** |
| 5 | Flet 终端为「一次性执行 + 回显」，非真正流式 | 流式需 `Popen` + 节流刷新，本次未实现 | A |
| 6 | 交互测试中 `input text` 只输入了 `echo`（空格后截断） | 属 adb 测试手法的瑕疵，非应用缺陷；因为 `echo` 无参输出空行是正确行为 | A |
| 7 | `bootstrap-aarch64.zip` 原件已被构建过程消费（现仅存于 arm64 APK 内） | 可自 `termux/termux-packages` 重新下载，sha256 已记录 | A |
| 8 | 本次**未修改任何 bat2sh 仓库代码** | 唯一仓库写入 = 本报告；HEAD 全程锁在 `01f61b5` | A |

---

## 9. 复现命令

    # 1) bootstrap
    TAG='bootstrap-2026.09.20-r1%2Bapt.android-7'
    curl -sSL -o src/assets/bootstrap-aarch64.zip \
      "https://github.com/termux/termux-packages/releases/download/$TAG/bootstrap-aarch64.zip"

    # 2) 项目结构（assets 必须在 app.path 之下）
    #    src/main.py  +  src/assets/bootstrap-<abi>.zip
    #    pyproject.toml: [tool.flet.app] path="src" / module="main"

    # 3) 构建（环境变量见 V1 报告 §6.1，关键是 JAVA_TOOL_OPTIONS 代理）
    source ./env.sh
    .venv/bin/flet build apk --arch arm64-v8a --yes --no-rich-output

    # 4) 在模拟器上验证（本机 /dev/kvm 可用）
    avdmanager create avd -n poc34 -k "system-images;android-34;google_apis;x86_64" -d pixel_6
    emulator -avd poc34 -no-window -no-audio -no-boot-anim -gpu swiftshader_indirect -accel on &
    adb wait-for-device && adb install -r -t build/apk/*.apk
    adb shell monkey -p org.example.flet_termux_poc -c android.intent.category.LAUNCHER 1
    adb logcat -d | grep flet.python

    # 5) 直接 bash -n（bat2sh 的关键路径）
    adb shell "/system/bin/linker64 <PREFIX>/bin/bash -n <file.sh>; echo rc=\$?"

---

## 10. 证据文件（`/tmp/flet-termux-poc/`，已保留）

| 文件 | 内容 |
| :--- | :--- |
| `apk-arm64-v8a.apk` | 交付验证物，82.8 MB，含 aarch64 bootstrap |
| `apk-x86_64.apk` | 模拟器验证用，84.6 MB，含 x86_64 bootstrap |
| `screen1.png` / `screen2.png` / `screen3.png` | 首启自检、修正后自检、滚动到底部（含 `bash -n` 两条 PASS） |
| `screen4.png` | 交互执行回显 |
| `build-arm64*.log` / `build-x86*.log` | 构建日志 |
| `env.sh` | 复用的构建环境变量 |

---

> **结论：方案二（Flet + 内嵌 Termux）成立。**
> Q1、Q3 完全通过；Q2 在 **bat2sh 的关键路径（`bash -n`）上通过**，
> 但通用子进程执行受限 ——「运行脚本」类功能仍需 proot 或降 targetSdk 才能保留。
> **本次暂停，等待审阅。**
