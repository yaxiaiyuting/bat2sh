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

    1. ./scripts/release-bump.sh <X.Y.Z>          # 版本号写入四处，随提交入库
    2. git add -A && git commit -m "chore: bump version to v<X.Y.Z>"
    3. ./scripts/release-preflight.sh             # 必须通过（含 D-1 门）
    4. git tag -a v<X.Y.Z> -m "v<X.Y.Z>" && git push origin main v<X.Y.Z>
    5. ./scripts/release-sync-pkg.sh <X.Y.Z>      # tag 之后同步 sha256
    6. git commit -m "chore(pkg): sync PKGBUILD hashes for v<X.Y.Z>" && git push
    7. ./scripts/release-assets.sh <X.Y.Z>        # 上传二进制资产（见 D-2）

### 强制执行点

`scripts/release-preflight.sh` 第 2 步调用 `release-bump.sh --check`，
校验 `pyproject.toml` / `__init__.py` / `PKGBUILD` / `.SRCINFO` **四处版本一致**，
不一致即 `exit 1`，禁止 tag。

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
| 2 | 四处版本一致 | `./scripts/release-bump.sh --check` |
| 3 | 类 CI 环境 pytest 全绿 | `./scripts/release-preflight.sh` |
| 4 | 外部资源依赖有 skip 兜底 | 同上（第 4 步） |
| 5 | PKGBUILD 哈希与 tag tarball 一致 | `./scripts/release-sync-pkg.sh <ver>` |
| 6 | Release 资产已上传 | `./scripts/release-assets.sh <ver>` |

以上 1-4 由 `release-preflight.sh` 一次跑完；5-6 必须在 tag 之后。
