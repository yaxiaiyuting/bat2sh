# Android 打包

> **状态（2026-09-20）：Android 路线在 Phase 1 被阻断，未产出 bat2sh 应用 APK。**
> 完整结论、根因与后续建议见 [`docs/android-poc-report.md`](../../docs/android-poc-report.md)。

## 目录导航

| 路径 | 内容 | 状态 |
| :--- | :--- | :--- |
| `proot-poc/` | **本轮成果**：proot 阻断验证的 Flet 探针工程 + 构建脚本 | 阻断（判定不通过） |
| `build/apk/` | 交付的探针 APK `flet-proot-poc-arm64-v8a.apk` | 构建产物，不入库 |
| `legacy-pyside6-README.md` | 前序 PySide6 Android 路线评估（上游无 Android wheel） | 已废弃，原文保留 |
| `legacy-pyside6-main.py` | 同上，`pyside6-android-deploy` 要求的入口 stub | 已废弃，原文保留 |

## 两条已排除的路线

| 路线 | 阻断点 | 出处 |
| :--- | :--- | :--- |
| **PySide6** | 上游不发布 PySide6 / shiboken6 的 Android wheel | `legacy-pyside6-README.md` |
| **Flet + proot** | guest 内 `fork()` 恒返回 ENOSYS，拿不到 shell 能力 | [`docs/android-poc-report.md`](../../docs/android-poc-report.md) |

## 当前最有证据支撑的下一步

**降 targetSdk 到 28 + Termux 本体路线（不用 proot）。**

本轮实测确认了两件事：

1. `[tool.flet.android] target_sdk_version = 28` 在 Flet 1.0.0 上确实生效（模板直接读该项目配置）。
2. targetSdk 28 下，应用私有数据目录里的二进制**恢复可 execve**
   （同一探针在 targetSdk 36 下是 `execve: Permission denied`，在 28 下成功起 shell）。

而 proot 的问题（fork ENOSYS）**与 targetSdk 无关** —— 所以「降 targetSdk」应当配合
**不用 proot 的 Termux 本体路线**，而不是用来救 proot。

## 环境（沿用上一 session 的 Flet PoC）

```bash
source /tmp/flet-termux-poc/env.sh
# Flet 1.0.0 / Flutter 3.44.8 / Python 3.14.7 / JDK 17 / Android SDK + NDK
```

> `.gitignore`（本目录）做了一件事：仓库根 `.gitignore` 的 `src/` 规则会连坐
> `packaging/android/**/src/`，这里把它重新纳入；同时把大体积二进制资产排除在外。