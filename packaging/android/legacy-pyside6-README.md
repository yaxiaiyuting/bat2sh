# Android APK（arm64-v8a）构建评估

> 结论（2026-09-20 实测）：**当前不可行**。原因不是配置问题，而是**上游不提供所需的
> PySide6 Android wheel**。本文记录已核实的事实与可推进的路径，避免重复踩坑。

## 1. 目标

构建 arm64-v8a（aarch64）的 Android 安装包（.apk），使 bat2sh 可在 Android 上运行。

## 2. 官方工具链与其硬性要求

PySide6 自带 `pyside6-android-deploy`（内部使用 buildozer + python-for-android）。
其 `--help` 与源码文档串（`PySide6/scripts/android_deploy.py`）明确要求：

| 要求 | 状态 |
| :--- | :--- |
| 主入口必须命名为 `main.py` | 本目录已提供（见 `main.py`） |
| `--wheel-pyside`：**PySide6 Android wheel** | **拿不到（见第 3 节）** |
| `--wheel-shiboken`：**shiboken6 Android wheel** | **拿不到** |
| Android SDK（命令行工具） | 工具可自动下载（dl.google.com） |
| Android NDK **r26b** | 工具可自动下载 |
| JDK | 本机已有 |
| buildozer / python-for-android / cython | 需 pip 安装 |

## 3. 实测：Android wheel 不可得

| 检索位置 | 结果 |
| :--- | :--- |
| PyPI `PySide6/6.11.2` | 仅 5 个 wheel：macOS universal2 / manylinux x86_64 / manylinux aarch64 / win_amd64 / win_arm64。**无 android** |
| PyPI `PySide6-Android` / `pyside6-android` / `shiboken6-android` | 全部 **HTTP 404**（包不存在） |
| `download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/` | **只有源码** tarball，无 wheel |
| `download.qt.io/snapshots/ci/pyside/6.11.2/` | 仅 `latest/`（404 跳转）与 commit 目录，**无 Android wheel** |
| 全网检索 | 仅见 2023 年的 `PySide6-6.6.0a1-...-android_aarch64.whl` **CI 快照**（非稳定发布） |

即：**Qt 未公开发布与 6.11.x 匹配的 Android wheel**。

## 4. 若坚持推进，需要什么

按代价从低到高：

1. **改用 CI 快照 wheel（不推荐）**：找 6.6.x 时代的 `android_aarch64` wheel，
   但与本项目依赖的 PySide6 6.11 API **不匹配**，且属未发布快照，不适合随 Release 分发。
2. **自行交叉编译 PySide6 for Android（重）**：
   - Qt for Android（aarch64）约 2–3 GB
   - shiboken6 + PySide6 交叉编译，数小时量级
   - 另需 Android SDK + NDK r26b 约 2 GB
   - 参考 `pyside-setup-everywhere-src-6.11.2`（源码包在 official_releases 可取）
3. **等上游发布**：关注 Qt for Python 的 Android wheel 发布渠道。

## 5. 另一个独立问题：桌面 GUI 在 Android 上的可用性

即使 wheel 可得，本项目 GUI 是**桌面形态**（`QMainWindow` + 三栏 `QSplitter` +
菜单/工具栏 + `QFileDialog` 文件选择 + 拖放）。在 Android 上：

- 文件选择、拖放、多窗口等交互模型与桌面差异很大；
- 触屏与高 DPI 需要专门的布局适配（当前为桌面 KDE Breeze 视觉优化）；
- CLI 形态在 Android 上无终端入口，价值有限。

因此「能打出 APK」与「APK 能用」是两件事，后者还需要一轮 GUI 适配工作。

## 6. 结论与建议

- **本次不产出 APK**，也不提交任何未经验证的 Android 构建产物。
- 已保留 `main.py`（工具链第一项硬性要求），使后续推进可直接从 wheel 问题开始。
- 若确有 Android 需求，建议作为独立任务立项，并先确认 wheel 来源（第 4 节路径 2 或 3）。
