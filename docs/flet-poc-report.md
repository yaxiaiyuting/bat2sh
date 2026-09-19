# bat2sh —— Flet 构建链 PoC 报告（V1，阻断验证）

> 会话：Flet 构建链 PoC。起点 HEAD（锁定）= `905cf16`；**全程只读仓库**，
> 所有构建工作在 `/tmp/flet-poc/` 内完成，**未改动任何仓库代码**。
> 目的：验证本机能否跑通 `flet build apk`（阻断级）。
>
> # 判定：**V1 通过** —— 本机成功构建出 arm64-v8a APK。

---

## 0. 结论摘要（按任务书口径）

| 项 | 结果 |
| :--- | :--- |
| flet 版本 | **1.0.0**（flet-cli 1.0.0；要求 Flutter **3.44.8**） |
| 环境安装耗时 | `flet[cli]` pip 安装 **29 秒**；Flutter/JDK/Android SDK 由首次构建自动安装，**约 5–8 分钟**（含 Dart pub 依赖） |
| 首次构建耗时 | **10 分 39 秒**（03:34:36 → 03:45:15，含 Gradle 首次下载全部依赖） |
| 下载组件体积 | Flutter **2.2 GB** / JDK **316 MB** / Android SDK **3.4 GB**（含 NDK 2.2 GB）/ Gradle 缓存 **3.7 GB** / Dart pub **696 MB**；**合计约 11 GB** |
| **构建结果** | **成功** |
| APK 路径 + 大小 | `/tmp/flet-poc/build/apk/flet-poc.apk`，**53 MB**，sha256 `8da1d96e…42a2` |
| 真机验证 | **否** —— `adb devices` 无设备（Flutter 报的「1 device」是 Linux desktop，非 Android） |
| **V1 判定** | **通过** |

---

## 1. 前置确认

| # | 前置 | 结果 |
| :--- | :--- | :--- |
| 1 | `docs/flet-migration-assessment.md` 存在 | ✅（18,236 字节；**未跟踪**，见 §9 偏离 1） |
| 2 | `git status` 干净 | ⚠️ 无**已跟踪文件**改动；但存在上述未跟踪文档 |
| 3 | 起点 HEAD | ✅ `905cf16`（本地 main tip；`origin/main` 仍落后 7 个提交） |
| 4 | 磁盘 ≥ 10 GB | ✅ `/home` 760 GB 可用（`/tmp` 为 tmpfs 16 GB） |
| 5 | 代理可用 | ✅ `curl -x 127.0.0.1:10808 https://github.com` → **HTTP 200 / 1.34 s** |

**额外连通性预检（构建前主动做的）**：逐一探测构建链全部主机，发现 `dl.google.com` 首次超时但复测正常（瞬时抖动）；后续诊断出真正的网络拓扑，见 §6.1。

---

## 2. 最小 Flet 应用

`/tmp/flet-poc/`：

    /tmp/flet-poc/
    ├── pyproject.toml
    ├── src/
    │   └── main.py          # Hello from Flet
    ├── assets/
    └── .venv/               # 隔离环境（未污染仓库与系统）

`src/main.py` 与任务书一致（Hello World）。

**关于 `src/` 布局的重要发现**：Flet **1.0.0 默认在项目根查找 `main.py`**，
任务书给的 `src/main.py` 结构在默认配置下会直接报错：

> `main.py not found in the root of Flet app directory. Use --module-name option to specify an entry point`

正确做法（源码 `flet_cli/commands/build_base.py:955-980` 确认）是在 `pyproject.toml` 中声明：

    [tool.flet.app]
    path = "src"
    module = "main"

这样既保留 `src/` 结构，又满足 Flet 的入口解析。**这条对 bat2sh 迁移有直接影响**。

---

## 3. 环境安装

| 步骤 | 方式 | 耗时 | 结果 |
| :--- | :--- | :--- | :--- |
| `flet[cli]` | venv 内 pip（经代理） | **29 s** | flet 1.0.0 + 38 个依赖，全部为 wheel，**无编译** |
| Flutter 3.44.8 SDK | 首次 `flet build` **自动下载** | 由首次尝试触发 | `~/flutter/3.44.8`，2.2 GB |
| JDK 17 | 自动安装（本机 JDK 26 不兼容） | 见下 | `~/java/17.0.13+11`，316 MB |
| Android SDK | 自动安装 | 见下 | `~/Android/sdk`，3.4 GB |
| Gradle 8.14 | Gradle wrapper 下载（**受阻，见 §4.2**） | 8 s（预置后） | `~/.gradle`，最终 3.7 GB |

JDK 17 + Android SDK 的自动安装在第二次尝试的日志中可见：`[03:26:09] Installing JDK... / Installing Android SDK...` → `[03:28:31]`，即 **约 2 分 22 秒**。

**本机 JDK 26 未造成问题**：Flet 检测到版本不兼容后自动并行安装了 JDK 17（`~/java/17.0.13+11`），二者共存互不干扰。

---

## 4. 构建过程：3 次尝试与诊断

| # | 时间 | 耗时 | 结果 | 失败原因 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | （被主动终止） | — | 中止 | `dart pub` 经代理**挂起**（连接空闲 955 s，0% CPU） |
| 2 | 03:26:09 → 03:28:31 | 2 m 22 s | 失败 | ① `main.py` 不在根；② `maven.google.com` 直连超时 |
| 3 | 03:29:42 → 03:32:30 | 2 m 48 s | 失败 | Gradle wrapper 下载 Gradle 发行版**连接超时** |
| 4 | **03:34:36 → 03:45:15** | **10 m 39 s** | **成功** | — |

### 4.1 尝试 1：Dart pub 经代理挂起 → 代理范围收窄

现象：`dart pub` 进程 CPU 时间 `00:00:00`、`wchan=futex_wait`，
与代理的 TCP 连接 **空闲 955 秒**；`~/.pub-cache` 停在 500 MB 不增长。

根因：**代理对长连接不可靠**。实测网络拓扑（直连 vs 代理）：

| 主机 | 直连 | 代理 | 结论 |
| :--- | :--- | :--- | :--- |
| `github.com` | ✗ 超时 | ✓ 200 | **必须走代理** |
| `maven.google.com` | ✗ 超时 | ✓ 301 | **必须走代理** |
| `pub.dev` | ✓ 200 (0.46 s) | ✓ 200 | 直连更快 → 绕过代理 |
| `dl.google.com` | ✓ 200 | ✓ 200 | 直连 |
| `storage.googleapis.com` | ✓ 200 | ✓ 200 | 直连 |
| `repo1.maven.org` | ✓ 200 | ✓ 200 | 直连 |
| `services.gradle.org` | ✓ 200 | ✓ 200 | 直连（但重定向后需代理，见 4.3） |

修复：用 `no_proxy` 把**除 github / maven.google.com 之外**的主机全部改为直连。
**已验证 Dart pub 确实遵守 `no_proxy`**（最小 `dart pub get` 测试：**1 秒**完成）。

### 4.2 尝试 2：两个独立问题

1. **入口点** —— Flet 1.0.0 要求 `main.py` 在 app 根目录；已用 `[tool.flet.app] path = "src"` 解决（§2）。
2. **`flutter doctor` 报 `maven.google.com` 超时** —— 因为我错误地把它放进了 `no_proxy`。
   实测它**直连超时、必须走代理**，已从 `no_proxy` 移除。
   同时 Flutter 提示需要 **Android SDK 36**（自动装的是 35），我主动用 `sdkmanager` 补装了
   `platforms;android-36` + `build-tools;36.0.0`（**8 秒**，直连 dl.google.com）。

### 4.3 尝试 3：Gradle wrapper 下载失败 —— **本次最关键的环境发现**

现象：

    Exception in thread "main" java.net.ConnectException: 连接超时
        at org.gradle.wrapper.Install.createDist(Install.java:48)
        Gradle task assembleRelease failed with exit code 1

根因链（已完全定位）：

1. Gradle wrapper 从 `https://services.gradle.org/distributions/gradle-8.14-all.zip` 下载；
2. 该 URL 返回 **307 重定向到 `github.com/gradle/gradle-distributions/releases/download/…`**；
3. **GitHub 必须走代理**（见 4.1）；
4. **而 JVM 不读取 `https_proxy` / `http_proxy` / `no_proxy` 环境变量** ——
   Java 需要显式系统属性，因此 wrapper 只能直连 → 超时。

修复（**这一条对任何需要 Gradle 的构建都适用**）：

    export JAVA_TOOL_OPTIONS="-Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=10808 \
                             -Dhttp.proxyHost=127.0.0.1  -Dhttp.proxyPort=10808 \
                             -Dhttp.nonProxyHosts=localhost|127.0.0.1"

另加保险：用 `curl -x` 预先把 `gradle-8.14-all.zip`（**214 MB，8 秒，27 MB/s**）放入
wrapper 缓存目录并校验 zip 完整性（27,264 条目，无损）。

### 4.4 尝试 4：成功

    [03:34:36] Installing JDK...
    [03:34:37] Installing Android SDK...
               Packaging Python app...
               Packaged Python app OK
               Building .apk for Android...
    [03:45:15] Built .apk for Android OK
               Copied build to build/apk directory OK
      Successfully built your .apk for Android!

**无错误、无警告输出**。Gradle 首次运行把依赖缓存从 0 涨到 **3.7 GB**（AGP / Kotlin / AndroidX 等），
并额外下载了 **NDK 2.2 GB** 与 `cmake` 60 MB。

---

## 5. 产物验证

### 5.1 APK 结构检查（实测）

| 检查项 | 结果 |
| :--- | :--- |
| 路径 / 大小 | `/tmp/flet-poc/build/apk/flet-poc.apk` / **53 MB** |
| sha256 | `8da1d96ec6d8c2f40b6e8870480c736da4a2a21b85a201f1570c532ef4a142a2` |
| **arm64-v8a 原生库** | ✅ **63 个 `.so`** |
| **ABI 隔离** | ✅ **只有 `lib/arm64-v8a/`**，无 armeabi-v7a / x86_64（`--arch arm64-v8a` 生效） |
| **Python 运行时** | ✅ `lib/arm64-v8a/libpython3.14.so`（5.8 MB） |
| 标准库 | ✅ `assets/stdlib.zip`（10.9 MB） |
| site-packages | ✅ `assets/sitepackages.zip`（5.5 MB） |
| 应用代码 | ✅ `assets/app.zip`（779 字节） |
| 其他 | `classes.dex` 2.3 MB、MaterialIcons 字体、`flutter_assets/` |

**两点对迁移评估的直接印证**：

1. **Python 3.14 被打进 APK** —— 与本机 Python 版本一致，说明 Flet 的 Android CPython 构建覆盖 3.14。
2. **`sitepackages.zip` 确认存在** —— 印证了评估 §1.2 的判断：Flet ≥0.86 以 **zipimport** 方式
   装载纯 Python 代码。bat2sh 的 `core/` 无 `__file__` 数据加载，因此**无需 `extract_packages`**
   这一结论在真实产物上得到确认。

### 5.2 真机验证：**未做**

    $ adb devices -l
    List of devices attached          # 空

本机 **无 Android 设备连接**（Flutter 报的「1 connected device」是 Linux desktop）。
按任务书约定跳过真机安装，记录为**未真机验证**。

因此**尚不能断言**「APK 能在设备上启动并正常渲染」—— 这属于已知未覆盖项（见 §9）。

---

## 6. 关键发现（可复用）

### 6.1 网络拓扑：代理只对两个域名必需

本机**并非「全部需要代理」**：只有 `github.com` 与 `maven.google.com` 直连超时，
其余构建主机（pub.dev / dl.google.com / storage.googleapis.com / repo1.maven.org 等）**直连即可且更快**。
把不需要的域名也塞进代理，反而引入了「长连接挂起」风险。

**推荐配置**（本次成功构建所用，完整可复制）：

    export JAVA_HOME=$HOME/java/17.0.13+11
    export ANDROID_HOME=$HOME/Android/sdk
    export ANDROID_SDK_ROOT=$HOME/Android/sdk
    export PATH="$HOME/flutter/3.44.8/bin:$JAVA_HOME/bin:$PATH"

    export https_proxy=http://127.0.0.1:10808
    export http_proxy=http://127.0.0.1:10808
    # 注意：不要把 maven.google.com 放进 no_proxy（它必须走代理）
    export no_proxy="pub.dev,.pub.dev,pub.dartlang.org,storage.googleapis.com,dl.google.com,\
    repo1.maven.org,repo.maven.apache.org,plugins.gradle.org,services.gradle.org,\
    api.adoptium.net,download.flutter.io,localhost,127.0.0.1,::1"

    # 关键：JVM 不读上面三个环境变量
    export JAVA_TOOL_OPTIONS="-Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=10808 \
                             -Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=10808 \
                             -Dhttp.nonProxyHosts=localhost|127.0.0.1"

### 6.2 Flet 1.0.0 的入口点约定

Flet 1.0.0 **不再默认支持 `src/main.py`**（与早期文档/教程不同），
需显式写 `[tool.flet.app] path = "src"`。若沿用旧认知会得到一个**看似成功但立即报错**的构建。

### 6.3 体积与耗时基线（实测）

| 项 | 实测值 |
| :--- | ---: |
| 工具链 + 缓存总计 | **约 11 GB** |
| 首次成功构建（依赖已就绪前） | **10 m 39 s** |
| 纯下载带宽（经代理） | 27 MB/s（214 MB / 8 s） |
| 产物 APK | 53 MB |

---

## 7. 对 bat2sh 迁移的影响

| 评估中的判断 | PoC 后的状态 |
| :--- | :--- |
| Linux 可构建 APK | ✅ **实测确认** |
| arm64-v8a 受支持 | ✅ **实测确认**（产物仅含该 ABI） |
| Flutter/JDK/SDK 可自动安装 | ✅ **实测确认**（JDK 26 不兼容也自动处理） |
| 环境需约 2.5–3.5 GB（评估 §4.2 估算） | ⚠️ **低估**：实测 **约 11 GB**（含 Gradle 缓存 3.7 GB + NDK 2.2 GB） |
| `sitepackages.zip` zipimport → core 无需 `extract_packages` | ✅ **产物确认** |
| 首次构建 20–60 分钟（评估 §4.2） | ⚠️ **高估**：实测首次成功构建 **10 m 39 s**（但前置工具链下载另需 5–8 分钟） |
| P1（`bash -n` 在 Android 失效且静默报通过） | ❌ **仍为阻断项**，本次未涉及（PoC 不打包 bat2sh） |
| run 功能 / 语法高亮损失 | ❌ 仍待产品决策 |

---

## 8. 下一步建议（V1 通过后）

按任务书要求给出：

1. **P1 修复（core 诚实性）作为 v2.9.0** —— 建议优先。理由：它是 Android 迁移的**硬前置**，
   且触碰项目已被修复两次的同类缺陷（v2.6.0 A-1 / v2.8.1 报告诚实性）。
   改动局限在 `core/syntax.py` + `ConvertReport` 增加「校验未执行」显式状态，
   对既有 CLI/桌面行为应是**零回归**（可用 151 语料指标 + 全量 pytest 守护）。
2. **GUI 重写作为 v3.0.0（或独立 track）** —— 前置是 P1 + run/高亮的产品决策。
3. **建议补做 V2/V3/V4**（评估 §6 的待验证项）：
   - V2：`msgpack` 等依赖的 Android wheel（本次 APK 已含 `sitepackages.zip`，可直接查证）
   - V3：在 APK 内 import `bat2sh.core` 并跑一次真实转换
   - V4：真机验证（本机无设备，需接入）

**推荐验收方式**：把本次的 `/tmp/flet-poc` 作为**构建链基线**保留（已保留），
后续 bat2sh APK 直接复用同一套环境变量与已缓存的 11 GB 工具链，避免重复下载。

---

## 9. 偏离与置信度披露（纪律 3/4）

| # | 项 | 说明 | 置信度 |
| :--- | :--- | :--- | :---: |
| 1 | `docs/flet-migration-assessment.md` 仍为**未跟踪**状态 | 上一 session 留下，本 session 按「唯一 commit = 报告」未提交它 | A |
| 2 | `origin/main` 落后本地 **7 个提交** | 前序工作仍未 push；「HEAD = main tip」仅本地成立 | A |
| 3 | **未做真机验证** | 无 Android 设备连接；**「能打包」≠「能用」** | A |
| 4 | PoC 打包的是 **Hello World**，不是 bat2sh | 未验证 `bat2sh.core` 在 Android 上的 import 与运行；`msgpack` 等依赖打包情况亦未单独验证 | A |
| 5 | 尝试 1 被我**主动终止**（非自然失败） | 终止依据是「连接空闲 955 s + 0% CPU」的实测证据，非拍脑袋 | A |
| 6 | 环境耗时「5–8 分钟」为**区间估计** | 工具链下载横跨被终止的尝试 1 与尝试 2，无法精确切分 | **B** |
| 7 | 构建第 4 次即成功，**含 2 次失败的诊断修复** | 失败全部可定位、可复现、已给出修复；非偶然成功 | A |
| 8 | 本次**未修改任何仓库代码** | 全部工作位于 `/tmp/flet-poc/`；唯一仓库写入 = 本报告 | A |

---

## 10. 复现命令（从零到 APK）

    # 0) 前置：代理可用（github.com 与 maven.google.com 必须经代理）
    curl -x 127.0.0.1:10808 -sS -o /dev/null -w "%{http_code}\n" https://github.com

    # 1) 建最小应用
    mkdir -p /tmp/flet-poc/src /tmp/flet-poc/assets && cd /tmp/flet-poc
    #   src/main.py  : Hello from Flet
    #   pyproject.toml: 含 [tool.flet.app] path="src" / module="main"

    # 2) 环境（§6.1 的完整变量）
    python3 -m venv .venv && .venv/bin/pip install "flet[cli]"

    # 3) 构建
    .venv/bin/flet build apk --arch arm64-v8a --yes --no-rich-output

    # 4) 验证
    unzip -l build/apk/flet-poc.apk | grep -c "lib/arm64-v8a/.*\.so"   # -> 63
    unzip -l build/apk/flet-poc.apk | grep -E "libpython|sitepackages"

---

> **V1 通过：本机具备 `flet build apk` 的完整能力。**
> 项目可以继续，但 P1（core 诚实性）仍是 Android 迁移的硬前置，建议作为下一步。
> **本次暂停，等待审阅。**
