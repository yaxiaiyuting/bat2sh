# bat2sh Android —— proot 方案 PoC 报告

> 会话：Android proot PoC。起点 HEAD（锁定）= `537a434`（= 当时 main tip）；
> 分支 `android-poc`，**未合并 main、未 bump 版本、未打 tag**。
>
> # 判定：**Phase 1 不通过 —— proot 方案在当前形态下不成立。**
> ## 按任务书 §3.3 / §六，**暂停，不进入 Phase 2**。

---

## 0. 结论摘要

| 项 | 结果 |
| :--- | :--- |
| 运行脚本方案 | proot（termux/proot 5.1.107.92） |
| proot 可执行（入口进程） | **PASS** —— `linker64 <PREFIX>/bin/proot --version` rc=0 |
| rootfs 可用 | **PASS** —— `/bin/ls /` rc=0、`/bin/uname -a` rc=0 |
| **子进程 exec（`/bin/sh -c "ls"`）** | **FAIL** —— guest 内 `fork()` 返回 ENOSYS |
| **Phase 1 总判** | **不通过 → 暂停** |
| Phase 2（最小可用版本） | **未开始**（按 §六 阻断即停） |
| 交付 APK | 诊断探针 `flet-proot-poc-arm64-v8a.apk`（98,543,576 B，sha256 `b70eb8c9…764c`） |

**一句话**：Android 的应用沙箱挡住的不是 `execve`（那一条本次已用 proot loader 绕过并实测跑通），
而是 **proot 的 tracee 无法 `fork()`** —— 于是 proot 里连 `sh -c "ls"` 都跑不起来，
「保留完整 shell 能力」这个前提不成立。

---

## 1. 前置确认（任务书 §一）

| # | 前置 | 结果 |
| :--- | :--- | :--- |
| 1 | `docs/flet-termux-poc-report.md` 存在 | ✅ 15,554 B |
| 2 | `git status` 干净 | ⚠️ 无已跟踪文件改动；仍有前序遗留的未跟踪 `docs/flet-migration-assessment.md`（见 §8 偏离 1） |
| 3 | 起点 HEAD = main tip | ✅ `537a434` = `main` |
| 4 | 磁盘 ≥ 20 GB | ✅ `/home` 750 GB 可用 |
| 5 | 代理可用 | ✅ `curl -x 127.0.0.1:10808 https://github.com` → HTTP 200 |
| 6 | `/tmp/flet-termux-poc/env.sh` 存在 | ✅ |
| 7 | 参考项目已读 | ⚠️ **部分** —— 两个仓库在本机不存在，GitHub API 亦未取到；本次改用 **proot 上游源码**（`termux/proot` master）作为主要依据（见 §8 偏离 2） |

环境：Flet **1.0.0** / Flutter **3.44.8** / Python **3.14.7** / JDK 17 / Android SDK + NDK；
验证设备：**Android 14（API 34）x86_64 模拟器 `poc34`**（`/dev/kvm` 加速）。

---

## 2. 分支

```
git checkout main && git checkout -b android-poc      # HEAD 537a434
```

全程只在该分支提交；**不合并 main、不发 release、不 bump 版本、不打 tag**。

---

## 3. Phase 1：proot PoC

### 3.1 proot 发行版选择

优先级 1（Termux 的 proot）即已可用，未动用优先级 2：

| 组件 | 版本 | 来源 | 大小 |
| :--- | :--- | :--- | ---: |
| proot | 5.1.107.92 | `packages.termux.dev/apt/termux-main` `proot_5.1.107.92_<abi>.deb` | aarch64 244,088 B / x86_64 260,528 B |
| libtalloc | 2.4.3 | 同上 `libtalloc_2.4.3_<abi>.deb` | 31,440 / 30,096 B |
| libandroid-shmem | 0.7 | 同上 | 14,432 / 14,368 B |
| proot loader | — | deb 内 `libexec/proot/loader`（**静态 ELF，ET_EXEC**） | 18,136 / 18,352 B |
| guest rootfs | alpine-minirootfs 3.20.3 | `dl-cdn.alpinelinux.org` | aarch64 3,947,906 B / x86_64 3,490,290 B |
| Termux bootstrap | `bootstrap-2026.09.20-r1+apt.android-7` | termux-packages release | aarch64 **32,806,628 B**，sha256 `65ba5781…3cc69`（与上一 session 报告**逐字节一致**） |

proot 是 **NDK r29 构建的 Bionic 二进制**，`PT_INTERP = /system/bin/linker64`，
`DT_NEEDED = libtalloc.so.2, libandroid-shmem.so, libc.so`，`DT_RUNPATH` 硬编码 Termux 路径 ——
所以必须自备这三个 .so 并注入 `LD_LIBRARY_PATH`。

### 3.2 PoC 工程

`packaging/android/proot-poc/`（结构见该目录 README）。核心是一个**探针电池**：
一次启动跑完 A–J 十组探针，结果同时写 UI 和 stdout（logcat tag `flet.python`）。

关键工程决定：

1. **assets 必须在 `<app.path>/assets`**（即 `src/assets/`）—— 沿用上一 session 的教训。
2. Termux bootstrap 解压必须处理 **`SYMLINKS.txt`**（`<target>←<linkpath>`）+ 设执行位。
3. `PROOT_TMP_DIR` 必须显式设置：proot 编译期 TMP 路径是 `/data/data/com.termux/files/usr/tmp`，
   在本应用里不存在，不设会让 proot 连 f2fs 探测都做不了。
4. 入口进程恒用 `/system/bin/linker64 <PREFIX>/bin/proot`（直执被拒）。

### 3.3 判据结果（任务书 §3.3）

| 判据 | 通过条件 | 实测 | 判定 |
| :--- | :--- | :--- | :---: |
| proot 可执行 | 能启动，无 permission denied | 探针 B：`linker64 proot --version` rc=0，打印 5.1.107.92 banner | **PASS** |
| **子进程 exec** | proot 内能执行 `/bin/sh -c "ls"` | 探针 E/E3/E4/E5/E7/E8：shell 起来了、`echo` 内建生效，但**任何需要 fork 的动作**都是 `/bin/sh: can't fork: Function not implemented` | **FAIL** |
| rootfs 可用 | 能读取 rootfs 内文件 | 探针 E2 `/bin/uname -a` rc=0；探针 E6 `/bin/ls /` rc=0（完整列目录） | **PASS** |

> **总判：不通过。** 探针 E 的 stdout 恰好是任务书写的那条命令的残骸：
> `echo hi-E` 成功（内建），`id` / `ls` 全部倒在 fork 上。

### 3.4 根因（逐层定位，均有证据）

#### 第 1 层：Android 到底拦了什么 —— `execute_no_trans`，不是 `execute`

`adb logcat` 里的 audit 行（同一次 exec 尝试，两条并列）：

```
avc:  granted { execute }           ... tcontext=u:object_r:app_data_file  tclass=file
avc:  denied  { execute_no_trans }  path=".../data/rootfs/bin/busybox"
                                    tcontext=u:object_r:app_data_file  tclass=file
                                    scontext=u:r:untrusted_app  permissive=0
```

即：**mmap(PROT_EXEC) 允许**（所以 linker64 能加载），**execve 被拒**。
这比上一 session 的推断更精确 —— 上一 session 猜的是「W^X 禁 exec 应用数据目录」，
本次拿到的是确切的 SELinux 拒绝项 `app_data_file:file execute_no_trans`。

#### 第 2 层：proot 其实**不需要** execve guest 程序

读 `termux/proot` 源码（`src/execve/enter.c`）：

```c
/* Execute the loader instead of the program.  */
loader_path = get_loader_path(tracee);
status = set_sysarg_path(tracee, loader_path, SYSARG_1);
```

`translate_execve_enter()` 对**每一次** execve（包括 guest 内的后续 execve）都把 `SYSARG_1`
改写成 loader 路径 —— `$PROOT_LOADER` > `<prefix>/libexec/proot/loader` > 临时文件
`/proc/self/fd/N`。由 loader 去 mmap guest ELF。

**所以整条链上只有一个文件需要可执行：loader。**

#### 第 3 层：loader 放到 `nativeLibraryDir` 就通了

- 原生 so 目录（`/data/app/~~…/lib/<abi>/`）属于 `apk_data_file`，**execve 允许**。
  证据：探针 H 直执 `nativeLib/lib_asyncio.so` 得到 **SIGSEGV（rc=-11）而不是 EACCES** ——
  内核/linker 真的把它跑起来了，只因它不是程序才崩。
- 把 loader 以 `libprootloader.so` 之名塞进 APK `lib/<abi>/`，再用
  `--android-legacy-packaging` 让它被解压到 nativeLibraryDir，然后
  `PROOT_LOADER=<nativeLibraryDir>/libprootloader.so`。
- **实测通了**（探针 E2/E6）：

```
E2  /bin/uname -a   -> rc=0  Linux localhost 6.1.23-android14-4-… x86_64 Linux
E6  /bin/ls /       -> rc=0  bin dev etc home lib media mnt opt proc root run sbin srv sys tmp usr var
```

#### 第 4 层：真正的墙 —— guest 内 `fork()` 返回 ENOSYS

```
E   proot … /bin/sh -c "echo hi-E; id; ls /"
    out: hi-E                                   <- 内建命令 OK
    err: /bin/sh: can't fork: Function not implemented
```

fork 失败 ⇒ 外部命令、管道、重定向、子 shell、脚本里的任何一条真实命令全部不可用。

**这不是 Android 拦的**，证据：

| 探针 | 内容 | 结果 |
| :--- | :--- | :--- |
| I | 不经 proot，`linker64 <PREFIX>/bin/bash -c "echo a \| while read x; do echo got=$x; done"`（两次 fork、零 exec） | **rc=0，out=`got=a`** |

同样是 `untrusted_app` 域、同样的 seccomp policy、同样的 targetSdk，
**应用进程自己 fork 完全正常** —— 问题被限定在 proot 的 tracee 内部。

### 3.5 已尝试的变通（全部无效）

| # | 变通 | 结果 |
| :--- | :--- | :--- |
| V1 | `PROOT_NO_SECCOMP=1`（关掉 proot 的 seccomp 加速器，退回 PTRACE_SYSCALL） | ❌ fork 仍 ENOSYS（探针 E4–E8） |
| V2 | **targetSdk 36 → 28** | ⚠️ **部分有效**：loader 直执恢复（探针 D 从 `execve("/bin/sh"): Permission denied` 变成能起 shell），**但 fork 仍 ENOSYS** |
| V3 | `-q /system/bin/linker64` 把 bionic linker 当 loader 用 | ❌ 源码层面即不可行：`expand_runner()` 对 host-arch ELF 整段跳过；且 bionic linker 只认 `--list`/`--help`/`<path>`，**不支持 proot 需要的 `-0`** |
| V4 | memfd + `execve("/proc/self/fd/N")` | ➖ 未得出结论：Python 3.14 在 Android 上 `os.memfd_create` 不可用（探针报 `NO-MEMFD-API`） |

补充：`PROOT_TMP_DIR` 未设置时 proot 会直接 `execve("/bin/sh"): No such file or directory`（探针 C），
这是**配置问题不是阻断**，设为 `<PREFIX>/tmp` 后即消失。

### 3.6 为什么就此打住（而不是继续调）

1. **判据已明确不通过**：任务书 §3.3 的「子进程 exec」这一条是硬判据，且 §六 写死「Phase 1 被拒 → 暂停，报告」。
2. **阻断性质不同**：上一 session 的阻断（execve 被拒）是**沙箱策略**，本次已定位并可绕；
   现在这条是 **proot 的 ptrace/seccomp 与 Android 应用进程的交互**，属于需要另立专题的深水区，
   不是「再试一个环境变量」能收敛的。已按纪律 7「仪器先验证」跑了 4 组变通，全部无效。
3. **继续做 Phase 2 没有意义**：用户的决策是「proot —— 保留完整 shell 能力」。
   一个**不能 fork 的 proot** 提供不了任何 shell 能力，Phase 2 的「运行脚本」按钮永远不可能工作，
   做出来只会是一个必然失败的 APK。
4. 时间盒：Phase 1 任务书给的是 30 分钟，实际已显著超支。

---

## 4. Phase 2：未开始

按 §3.4 / §六，Phase 1 不通过即不进入 Phase 2。因此：

- **没有** `packaging/android/src/main.py` 应用（bridge / highlighter / runner / UI 均未编写）
- **没有** bat2sh 应用 APK
- `python/bat2sh/core/` **零改动**（纪律 2 满足）

作为替代，本次交付的是 **Phase 1 诊断探针 APK**（见 §5）—— 可在真机上原样复现本报告的全部结论。

### 4.1 顺带确认的两条 Phase 2 前置事实（供后续使用）

1. **`python/bat2sh/core/` 纯标准库**，无 PySide6 依赖（`codecs/collections/dataclasses/datetime/enum/json/os/pathlib/re/shutil/stat/subprocess/tempfile/typing`），
   可以直接整目录打进 Flet 包。
2. **`ConvertSettings.bash_check` 在 Android 上必须置 False**：`core/syntax.py::bash_syntax_error()` 用
   `shutil.which("bash")` 找 bash，找不到就 `return None`（静默判通过）。
   在 Android 上即使把 `$PREFIX/bin/bash` 放进 PATH，`subprocess.run([bash, …])` 也会因 execve 被拒抛 OSError
   并被同一个 `except` 吞掉 —— 这正是上一 session 点名的 P1。正确做法是 `bash_check=False` + 自己经 proot 跑 `bash -n`。
3. **Flet 支持降 targetSdk**：模板读 `[tool.flet.android].target_sdk_version`（`build.gradle.kts` 里
   `targetSdk = <值>`），本次已实测生效。

---

## 5. 交付物

### 5.1 APK

| 项 | 值 |
| :--- | :--- |
| 路径 | `packaging/android/build/apk/flet-proot-poc-arm64-v8a.apk` |
| 大小 | **98,543,576 字节**（93.98 MiB） |
| sha256 | `b70eb8c987d214e997102de978402fd6e6f655e2bb9ac724a04bfa6fbaa9764c` |
| ABI | arm64-v8a（仅此一个） |
| targetSdk | 28（探针需要暴露 targetSdk 变量，见 §3.5 V2） |
| 签名 | debug 签名 |

> ⚠️ **这不是 bat2sh 应用**，是 Phase 1 的诊断探针：启动后自动跑 A–J 十组探针，
> 把 PASS/FAIL 与原始 stderr 打在屏幕上（同内容也进 logcat tag `flet.python`）。
> 它在真机上的价值是：**复现本报告的核心结论（fork ENOSYS）**。

> x86_64 探针 APK 未保留（构建目录被 arm64 构建覆盖）；重建命令见 §9。

### 5.2 代码

`packaging/android/`：

```
packaging/android/
├── README.md                     # 本目录导航 + Phase 1 结论
├── .gitignore                    # 让 src/ 能入库，同时排除大体积资产
├── build/apk/                    # 交付 APK（不入库）
├── legacy-pyside6-README.md      # 前序 PySide6 路线评估（原文保留，已废弃）
├── legacy-pyside6-main.py
└── proot-poc/
    ├── README.md                 # PoC 设计说明 + 探针清单
    ├── pyproject.toml            # Flet 项目定义（含 target_sdk_version = 28）
    ├── fetch-assets.sh           # 拉取 proot/libtalloc/shmem/alpine/bootstrap
    ├── make-template.sh          # 生成打了 jniLibs 补丁的 Flet 构建模板
    ├── build.sh                  # 一键构建
    └── src/
        ├── main.py               # 探针电池 A–J
        └── assets/               # 二进制资产（不入库，见 fetch-assets.sh）
```

### 5.3 文档

本文件 `docs/android-poc-report.md`。

---

## 6. 已知限制与未验证项

| # | 项 | 状态 |
| :--- | :--- | :--- |
| 1 | **arm64 上未真机验证** —— 所有执行结论来自 **x86_64 模拟器**；arm64 只验证了构建（APK 含 `lib/arm64-v8a/libprootloader.so` 18,136 B = aarch64 loader） | **未验证** |
| 2 | fork ENOSYS 的**上游根因未确证** —— 已排除「Android 拦 fork」（探针 I）与「proot seccomp 加速器」（V1），但没拿到 proot 的逐 syscall 日志 | **置信度 C** |
| 3 | 探针 J（proot `-v 4` 全量日志）拿到了输出，但报告格式化只截了前 240 字符，**未做逐行分析** | 未分析 |
| 4 | memfd 逃生通道未测（Python 在 Android 无 `os.memfd_create`） | 未验证 |
| 5 | 参考项目 `deepcode-lab/deepseek-harness-mobile` / `kelai141/dsh-mobile-apk` **本次没读到**（本机无、GitHub API 被限流）。§7 的建议因此完全基于本次实测 + proot 上游源码 | 置信度 B |
| 6 | 探针 APK 首次启动要解压 33 MB bootstrap + 4 MB rootfs（模拟器上约 1 s，真机预计数秒），期间 UI 无进度提示 | 已知体验问题 |
| 7 | proot 性能未测（本轮根本没能跑起来需要 fork 的负载） | 未验证 |

---

## 7. 对后续路线的建议（按证据强度排序）

### 建议 1（首选）：降 targetSdk 到 28 + **Termux 本体路线**，不用 proot

本次已把这条路线的**关键未知量验证掉一半**：

| 问题 | 结论 |
| :--- | :--- |
| targetSdk 28 能否恢复 `app_data_file` 的 execve？ | ✅ **能** —— 探针 D 在 targetSdk 28 下从 `Permission denied` 变为成功起 shell |
| targetSdk 28 能否让 proot 可用？ | ❌ **不能** —— fork 仍 ENOSYS（与 targetSdk 无关） |

也就是说：**proot 不是 targetSdk 问题，但「直接 exec Termux 二进制」是。**
上一 session 里「`bash -c "ls"` 的子进程 exec 被拒」这条，在 targetSdk 28 下应当直接消失，
从而拿到完整的 shell 能力 —— 而这**不需要 proot**。
上一 session 的报告本身就把这条列为 fallback（「评估降 targetSdk 方案（Termux 本体路线）」）。

代价与风险：

- 一行配置：`[tool.flet.android] target_sdk_version = 28`（本次已实测 Flet 支持）。
- Android 14 允许安装 targetSdk ≥ 23 的应用，28 安全。
- 副作用：失去 Play 商店上架资格（targetSdk 28 早已不满足 Google Play 要求）—— 对 PoC/侧载无影响。
- 目标 ABI 上的执行仍需真机验证。

### 建议 2：若坚持 proot，先做一次「对照实验」而不是继续调参

关键对照：**Termux 本体（targetSdk 28）+ proot-distro 能不能 fork？**

- 若能 → 差异点在 Flet/Flutter 应用进程的环境（zygote 属性、seccomp 继承、`NO_NEW_PRIVS` 等），
  而不是 ABI、也不是 Android 版本。届时应抓 proot `-v 9` 全量日志 + `strace -f` 定位那一次 `clone`。
- 若不能 → proot 在现代 Android 上普遍不可用，直接放弃该路线，回到建议 1。

### 建议 3（不建议）：继续在 x86_64 模拟器上深挖

在拿到 arm64 真机的同一现象之前，继续在模拟器上挖 fork ENOSYS 的收益很低 ——
本轮已交付 arm64 探针 APK（§5.1），真机复现的成本只有一次安装。

---

## 8. 偏离与置信度披露（纪律 3 / 4）

| # | 项 | 说明 | 置信度 |
| :--- | :--- | :--- | :---: |
| 1 | `docs/flet-migration-assessment.md` 仍为未跟踪 | 前序 session 遗留，本次同样未提交 | A |
| 2 | **未读参考项目** | 两个仓库本机不存在，GitHub API 未取到。改用 **proot 上游源码**（`termux/proot` master）作依据，这反而是更硬的一手证据，但与任务书 §一.7 有出入 | A（事实） |
| 3 | **偏离任务书 §4.2 的项目结构** | Phase 2 未启动，故未建 `packaging/android/src/{main.py,ui/,bridge.py}`。改为交付 `packaging/android/proot-poc/` | A |
| 4 | **主动扩大 Phase 1 范围** | 任务书只要求测「proot 能否跑」，本次额外做了 loader / nativeLibraryDir / targetSdk 三组变通。理由是：只报「不行」不可行动，而 §六 的下一句正是「评估降 targetSdk 方案」 | A |
| 5 | **交付 APK 不是 bat2sh 应用** | 它是诊断探针。Phase 2 未启动，没有应用 APK 可交 | A |
| 6 | 前序 `packaging/android/{README.md,main.py}` | 被移到 `legacy-pyside6-*`，内容原样保留（未删） | A |
| 7 | `-v 4` 探针日志被报告层截断到 240 字符 | 是我的报告格式化问题，不是 proot 的问题；原始日志仍在 `adb logcat` | A |
| 8 | 未 bump 版本 / 未 tag / 未合并 main | 按 §二 执行 | A |
| 9 | 本次**未修改** `python/bat2sh/core/` | 纪律 2 | A |

---

## 9. 复现命令

```bash
# 0) 环境（沿用上一 session 的 Flet PoC 环境变量）
source /tmp/flet-termux-poc/env.sh
FLET=/tmp/flet-termux-poc/.venv/bin/flet      # Flet 1.0.0

# 1) 资产（proot / libtalloc / libandroid-shmem / alpine rootfs / Termux bootstrap）
cd packaging/android/proot-poc
./fetch-assets.sh both

# 2) 构建（自定义模板 = 官方模板 + jniLibs/libprootloader.so + keepDebugSymbols）
./build.sh arm64-v8a        # 或 x86_64
# 等价于：
#   ./make-template.sh build/template
#   $FLET build apk --arch arm64-v8a --android-legacy-packaging \
#         --template build/template --yes --no-rich-output

# 3) 装机 + 跑探针（真机用 adb；模拟器见下）
adb install -r -t build/apk/flet-proot-poc-arm64-v8a.apk
adb shell am force-stop org.example.flet_proot_poc
adb logcat -c && adb shell monkey -p org.example.flet_proot_poc -c android.intent.category.LAUNCHER 1
sleep 30 && adb logcat -d | grep flet.python

# 4) 看 SELinux 到底拒了什么（本次根因就是这么拿到的）
adb logcat -d | grep -iE "avc:.*(execute|execno_trans)"
```

模拟器（x86_64，本机 `/dev/kvm` 可用）：

```bash
$ANDROID_HOME/emulator/emulator -avd poc34 -no-window -no-audio -no-boot-anim \
    -gpu swiftshader_indirect -accel on &
adb wait-for-device && adb install -r -t build/apk/<x86_64 apk>
```

---

## 10. 证据文件

| 位置 | 内容 |
| :--- | :--- |
| `packaging/android/build/apk/flet-proot-poc-arm64-v8a.apk` | 交付探针 APK（98,543,576 B） |
| `/tmp/flet-proot-poc/build/apk/` | 同一份 APK（构建目录） |
| `/tmp/flet-proot-poc/src/assets/` | 本轮实际使用的全部二进制资产 |
| `/tmp/proot-src/proot-master/` | proot 上游源码（loader / seccomp / clone 分析的依据） |
| `/tmp/proot-dl/ex_{aarch64,x86_64}/` | proot / libtalloc / libandroid-shmem 解包结果 |
| `adb logcat` tag `flet.python` | A–J 十组探针的完整原始输出（含 proot 的 stderr） |

---

> **结论：Phase 1 不通过。** proot 本身能在 APK 里启动、能读 rootfs、能让 guest 程序跑起来，
> 但 **guest 内 `fork()` 恒返回 ENOSYS**，因此拿不到任何 shell 能力，
> 「proot 保留完整 shell 能力」这一前提不成立。
> 按任务书 §3.3 / §六 **暂停，不进入 Phase 2**，等待用户决策。
> 下一步最有证据支撑的方向是 **降 targetSdk 到 28 + Termux 本体路线（不用 proot）**（§7 建议 1）。
