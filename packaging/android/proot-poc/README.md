# proot PoC（Phase 1 诊断探针）

> **结论：不通过。** 本目录是 bat2sh Android 计划的 **Phase 1 阻断验证**产物，
> 不是可用的 bat2sh 应用。完整结论见 [`docs/android-poc-report.md`](../../../docs/android-poc-report.md)。

## 它回答了什么

| 问题 | 答案 |
| :--- | :--- |
| proot 能在 Flet APK 里启动吗？ | ✅ 能，但必须经 `/system/bin/linker64` 作入口进程 |
| proot 能读 guest rootfs 吗？ | ✅ 能（`/bin/ls /`、`/bin/uname -a` 均 rc=0） |
| **proot 内能跑 `/bin/sh -c "ls"` 吗？** | ❌ **不能** —— guest 内 `fork()` 返回 ENOSYS |

## 为什么 proot 需要特殊处理（本 PoC 的核心发现）

1. **Android 拦的是 `execve`，不是 `mmap(PROT_EXEC)`。**
   SELinux 对 `app_data_file` 是 `granted { execute }` + `denied { execute_no_trans }`。
2. **proot 从不 execve guest 程序。** `src/execve/enter.c::translate_execve_enter()` 把每一次
   `execve` 的路径改写成 **loader**（`$PROOT_LOADER` > `<prefix>/libexec/proot/loader` > `/proc/self/fd/N`），
   由 loader 去 mmap guest ELF。
   ⇒ 整条链上只有一个文件需要落在**可执行**位置。
3. **`nativeLibraryDir`（`apk_data_file`）是可执行的。** 所以把 loader 以 `libprootloader.so` 之名
   塞进 APK 的 `lib/<abi>/`，再用 `--android-legacy-packaging` 解压出来，proot 就能跑。
   `make-template.sh` 做的就是这一步。

## 文件

| 文件 | 作用 |
| :--- | :--- |
| `fetch-assets.sh` | 拉取 proot / libtalloc / libandroid-shmem / alpine-minirootfs / Termux bootstrap 到 `src/assets/` |
| `make-template.sh` | 由官方 Flet 构建模板生成带 `jniLibs/libprootloader.so` 补丁的模板 |
| `build.sh` | `fetch + template + flet build apk` 一条龙 |
| `src/main.py` | 探针电池 A–J；结果同时进 UI 和 logcat tag `flet.python` |
| `src/assets/` | 二进制资产（**不入库**，由 `fetch-assets.sh` 生成） |
| `pyproject.toml` | Flet 项目定义；含 `[tool.flet.android] target_sdk_version = 28` |

## 构建

```bash
source /tmp/flet-termux-poc/env.sh          # JAVA_HOME / ANDROID_HOME / flutter / 代理
export FLET_BIN=/tmp/flet-termux-poc/.venv/bin/flet   # Flet 1.0.0

cd packaging/android/proot-poc
./fetch-assets.sh both        # 约 72 MB 下载
./build.sh arm64-v8a          # 或 x86_64
```

## 探针清单（`src/main.py`）

| # | 探针 | 目的 |
| :--- | :--- | :--- |
| A | 直执 `<rootfs>/bin/busybox` | 基线：确认 app 数据目录 execve 被拒 |
| B | `linker64 proot --version` | proot 能否作入口进程启动 |
| C | 裸 proot（loader 走编译期默认路径） | 默认路径不存在 → ENOENT |
| D | `PROOT_LOADER=<app 数据目录>/loader` | **决定性**：证明 loader 本身被 execve 拒绝 |
| E / E2 / E3 | `PROOT_LOADER=<nativeLibraryDir>/libprootloader.so` | **决定性**：绕过后 guest 能不能跑 |
| E4–E8 | 同上 + `PROOT_NO_SECCOMP=1` | 排除 proot seccomp 加速器 |
| F | 裸 proot 直跑 `/bin/echo` | 无 shell 时的行为 |
| G | `linker64 <rootfs>/bin/busybox` | bionic linker 能否直接跑 musl 二进制（不能：COPY relocations） |
| H | 直执 `nativeLib/lib_asyncio.so` | 证明 `nativeLibraryDir` 可执行（SIGSEGV ≠ EACCES） |
| I | `linker64 <PREFIX>/bin/bash -c "echo a \| while read x; …"` | **对照**：不经 proot 时 fork 正常 |
| J | proot `-v 4` | 取 proot 逐 syscall 日志 |

## 已知限制

- 结论在 **x86_64 模拟器（Android 14 / API 34）** 上取得；arm64 只验证了构建，**未真机验证**。
- fork ENOSYS 的**上游根因未确证**：已排除「Android 拦 fork」（探针 I）与「proot 的 seccomp 加速器」（E4–E8），
  但没做 proot 全量 syscall 日志的逐行分析。
- 本目录的资产（约 72 MB）**不入库**；`libprootloader.so` 由 `make-template.sh` 从 `loader-<abi>` 现取现用。