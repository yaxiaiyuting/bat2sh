# 发布流程（tag 顺序纪律）

> 本文档固化 2026-09-20 评估所发现缺陷 D-1 / D-2 的修复流程。
> 相关脚本：`scripts/release-bump.sh`、`scripts/release-preflight.sh`、
> `scripts/release-sync-pkg.sh`、`scripts/release-assets.sh`。

---

## 1. 缺陷 D-1：tag 内版本号不自洽（已修复流程）

### 现象

v2.1.0 至 v2.8.1 **连续 9 个 tag**，其源码树内 `PKGBUILD` 的 `pkgver` 都停留在
**上一版**，而同一棵树的 `python/bat2sh/__init__.py` 已是新版本：

| tag | PKGBUILD pkgver | 源码 __version__ | .SRCINFO pkgver |
| :--- | :--- | :--- | :--- |
| v2.8.1 | **2.8.0** | 2.8.1 | 2.8.0 |
| v2.8.0 | **2.7.0** | 2.8.0 | 2.7.0 |
| v2.7.0 | **2.6.0** | 2.7.0 | 2.6.0 |
| ... | ... | ... | ... |
| v2.1.0 | **2.0.0** | 2.1.0 | 2.0.0 |
| v2.0.0 | 2.0.0 | 2.0.0 | **1.11.0** |

### 根因

旧发布顺序是：

    tag -> 下载 tarball -> 算 sha256 -> commit "chore(pkg): sync PKGBUILD hashes"

版本同步提交**永远落在 tag 之后**，因此 tag 指向的那棵树永远不自洽。

### 后果

任何从 GitHub Release 源码包执行 `makepkg -si` 的用户会构建出**上一个版本**
（或直接失败）。本机之所以未暴露，是因为维护者始终从修好的 `main` 构建。

### 关键区分：哪一半能提前，哪一半不能

- **pkgver / .SRCINFO 的版本号：可以也必须提前。** 它不依赖 tag 内容。
- **sha256sums：客观上无法提前。** 它校验的是
  `archive/refs/tags/v<X.Y.Z>.tar.gz`，而该 tarball 的内容由 **tag 指向的 commit**
  决定 —— 哈希依赖 tag 自身，是**自指约束**。

旧流程的错误不在于"哈希留到 tag 后"，而在于**把版本号也一起留到了 tag 后**。

### 修复后的顺序（不可颠倒）

    1. ./scripts/release-bump.sh <X.Y.Z>          # 版本号写入五处，随提交入库
    2. git add -A && git commit -m "chore: bump version to v<X.Y.Z>"
    3. ./scripts/release-preflight.sh             # 必须通过（含 D-1 门）
    4. git tag -a v<X.Y.Z> -m "v<X.Y.Z>" && git push origin main v<X.Y.Z>
    5. ./scripts/release-sync-pkg.sh <X.Y.Z>      # tag 之后同步 sha256
    6. git commit -m "chore(pkg): sync PKGBUILD hashes for v<X.Y.Z>" && git push
    7. ./scripts/release-assets.sh <X.Y.Z>        # 上传二进制资产（见 D-2）

### 强制执行点

`scripts/release-preflight.sh` 第 2 步调用 `release-bump.sh --check`，
校验 `pyproject.toml` / `python/bat2sh/__init__.py` / `PKGBUILD` / `.SRCINFO` /
**`packaging/android/pyproject.toml`** **五处版本一致**，不一致即 `exit 1`，禁止 tag。

> 第五处是 **v2.9.0 起**纳入的。Android 工程是独立的 Flet 项目，它的 `version`
> 决定 APK 的 `versionName` —— 不同步就是 D-1 的翻版：tag 说 A，而发布出去的 APK 自称 B。

---

## 2. 缺陷 D-2：Release 零二进制资产（已提供发布路径）

### 现象

抽查 v1.0.0 / v1.11.0 / v2.0.0 / v2.4.0 / v2.7.0 / v2.8.1：**每个 Release 的上传资产数
都是 0**，GitHub 只挂了自动生成的 `Source code (zip/tar.gz)`。

而项目本地其实为每个版本都构建了 `bat2sh-<ver>.tar.gz`（sdist）与
`bat2sh-<ver>-1-any.pkg.tar.zst`（Arch 包），合计约 24 MB ——
**构建了却从未发布**，外部用户拿不到开箱即用的包。

### 修复

`scripts/release-assets.sh <X.Y.Z>` 把"本地已构建"推进到"已发布"：

    ./scripts/release-assets.sh 2.9.0              # 构建 sdist + Arch 包并上传
    ./scripts/release-assets.sh 2.9.0 --no-build   # 只上传已有产物
    ./scripts/release-assets.sh 2.9.0 --dry-run    # 预览将上传什么

前置：`gh auth login` 通过（脚本会先检查 `gh auth status`），且 GitHub 上已存在该 Release。
上传使用 `gh release upload --clobber`，可重复执行。

> 注意：GitHub Actions 里的自动上传**尚未接入**。本项目对 CI 有"必须全绿"的纪律，
> 未在本机验证过的 workflow 不宜直接提交；如需自动化，建议单独一个 session 做，
> 并在真实 tag 上验证一次。

---

## 3. 缺陷 D-3：测试不得依赖未入仓的外部资源（已改为真失败）

旧 `release-preflight.sh` 第 3 步标题为"校验测试不得依赖仓库外的外部资源路径"，
但脚本内写明"**本步仅提示，不判失败**" —— 因此它拦不住 v1.8.1 那类事故
（测试依赖 `~/下载/非常批处理/`，本地全绿、CI 红，tag 打完后才发现）。

现改为**真失败**：任何 `tests/**.py` 若引用 `Path.home()` / `os.path.expanduser()` /
`~/`，则该文件**必须**含 `pytest.skip` 兜底，否则 `exit 1`。

配套：真实语料形态的覆盖改由 `tests/fixtures/bat-pathologies/`（原创、许可安全）
承担，见该目录 README。

---

## 4. 发布前检查清单

| # | 检查 | 命令 |
| :--- | :--- | :--- |
| 1 | 工作区干净 | `git status --porcelain` |
| 2 | 五处版本一致 | `./scripts/release-bump.sh --check` |
| 3 | 类 CI 环境 pytest 全绿 | `./scripts/release-preflight.sh` |
| 4 | 外部资源依赖有 skip 兜底 | 同上（第 4 步） |
| 5 | PKGBUILD 哈希与 tag tarball 一致 | `./scripts/release-sync-pkg.sh <ver>` |
| 6 | Release 资产已上传（sdist / `.deb` / `.rpm` / Arch 包） | `./scripts/release-assets.sh <ver>` |

以上 1-4 由 `release-preflight.sh` 一次跑完；5-6 必须在 tag 之后。

---

## 5. Release 说明格式（历代对齐）

2026-09-20 评估发现：release 说明的格式在 **v1.10.0a1** 起漂移，
与 v1.2.2–v1.9.2 的既有格式不再一致：

| 项 | v1.2.2 – v1.9.2（基准） | v1.10.0a1 – v2.8.1（漂移） |
| :--- | :--- | :--- |
| 标题 | `## bat2sh vX.Y.Z`（H2） | `# bat2sh vX.Y.Z 发布说明 —— xxx`（H1） |
| Full Changelog 页脚 | 每个版本都有 | **15 个版本全部缺失** |

已把 15 个漂移文档对齐（标题改 H2、补 Full Changelog 页脚），
使 `docs/releases/*.md` 全部以 `## bat2sh vX.Y.Z` 开头。

**刻意未做**：不重排各版本的内部章节编号（如 `## 1. 修复说明` → `## 修复说明`）。
这些编号被其它文档以 `§X.Y` 形式交叉引用，重排会**静默破坏引用**；
且各版本的章节结构反映其真实内容组织，不属于「格式」范畴。

### 基准格式

    ## bat2sh vX.Y.Z

    > **性质**：<major/minor/patch>。<一句话范围与结论。>

    ### New features      （可选）
    ### Fixes             （可选）
    ### 已知限制          （可选）
    ### 验证 / Tests
    ### 后续              （可选）

    **Full Changelog**: https://github.com/yaxiaiyuting/bat2sh/compare/<prev>...<ver>

要点：

- 标题固定 `## bat2sh vX.Y.Z`；描述性文字放 `性质` 引用块，**不写进标题**。
- 结尾必须有 `**Full Changelog**` 行，`<prev>` 取**上一个 Release** 的 tag
  （预发布版同样适用，如 `compare/v1.9.2...v1.10.0a1`）。
- 预发布版（a1/b1/rc1）与正式版使用同一格式。

### 同步到 GitHub Release

    ./tools/publish/sync-release-notes.sh --dry-run   # 预览将同步哪些版本
    ./tools/publish/sync-release-notes.sh             # 同步全部有文档的版本
    ./tools/publish/sync-release-notes.sh v2.8.1      # 只同步指定版本

v1.2.2 / v1.2.3 两个 Release **没有**仓库文档（它们本就是基准格式本身），
脚本会跳过 —— 不从渲染后的 HTML 反向重建正文，避免杜撰内容。

---

## 6. 发行包（deb / rpm / Arch / Android）

### 6.1 已支持的格式

| 格式 | 脚本 | 架构 | 说明 |
| :--- | :--- | :--- | :--- |
| Arch | `PKGBUILD`（makepkg） | any | 原有路径 |
| Debian/Ubuntu | `packaging/build-deb.sh` | `all` | 纯 Python，同一包在 amd64/arm64 通用 |
| RPM | `packaging/build-rpm.sh` | `noarch` | 同上 |
| Android APK | `packaging/android/build.sh` | `arm64-v8a` / `x86_64` | Flet + 内嵌 Termux 运行时；见 6.3 |

三个脚本都会把产物写到 `dist/`（已在 .gitignore 中忽略）。

### 6.2 依赖声明口径

转换核心仅依赖 Python 标准库，**CLI 无需 PySide6 即可运行**（Graphical 界面才需要）。
因此两个新包的声明是：

- `Depends/Requires: python3 >= 3.12`（与 `pyproject.toml` 的 `requires-python` 一致）
- `Recommends: python3-pyside6`（**弱依赖**）

放在 Recommends 而非 Depends，是为了避免在**未打包 PySide6 的发行版**（如 Debian 12）
上直接无法安装 —— 那种情况下包仍可安装，CLI 可用，GUI 需自行 `pip install PySide6`。

### 6.3 Android APK（arm64-v8a）：**可行**，v2.9.0 起随 Release 发布

> **本节结论于 v2.9.0 更新。** 原文结论「不可行，原因在上游」针对的是
> **PySide6** 路线（`pyside6-android-deploy` 需要 PySide6/shiboken6 的 Android wheel，
> 而 Qt 未公开发布与 6.11.x 匹配的 android wheel）。该判断对 PySide6 仍然成立，
> 但**不再是本项目的 Android 路线**。
>
> 现行路线是 **Flet + 内嵌 Termux bootstrap**，已实际产出可安装 APK。

| 项 | 值 |
| :--- | :--- |
| 构建 | `cd packaging/android && ./build.sh arm64-v8a`（或 `x86_64`） |
| 依赖 | Flet 1.0.0 / Flutter 3.44.8 / JDK 17 / Android SDK；环境见 `/tmp/flet-termux-poc/env.sh` |
| 关键配置 | `target_sdk_version = 28`（**硬要求**：SELinux 域变为 `untrusted_app_27`，应用私有目录内二进制才可 `execve`） |
| 体积 | 约 87 MB（Termux bootstrap 32 MB） |
| 签名 | debug 签名（侧载 PoC；**不适合上架**） |
| 资产 | 作为 GitHub Release 资产上传（`gh release upload --clobber`） |

**构建顺序陷阱**：`flet build` 会清空 `build/apk/`。
若同时构建两个 ABI，**交付的那个 ABI 必须最后构建**，否则会被后续构建删掉。
`build.sh` 只带本 ABI 的 bootstrap（`--exclude` 掉另一份 32 MB）。

**仍未建立**：多 ABI 分发策略、release 签名、CI 自动构建。
如需长期维护，建议单独一个 session 处理。

详见 `docs/android-api-report.md`、`packaging/android/README.md`。
