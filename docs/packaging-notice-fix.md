# LICENSE → NOTICE 打包副作用修复报告

> **commit**：`c0b540a`（`fix(packaging): LICENSE 移出声明后，打包补 NOTICE`，2026-09-21 01:07:38，已推送至 `origin/main`）
> **背景**：为使 GitHub SPDX matcher 能识别，`LICENSE` 现只含 AGPL-3.0 官方正文
> （commit `6ef83a1`），版权人与应用声明移到了 `NOTICE`。三处打包脚本直接使用
> `LICENSE`，因此受影响。
> **本文件来源**：`c0b540a` 的 commit message 正文 + 只读复核证据（**未重跑构建**）。
> 三格式产物为 `c0b540a` 会话实跑所留，本 session 逐项复核其内容。

---

## 0. 起因

| 步骤 | commit | 动作 | 结果 |
| :---: | :--- | :--- | :--- |
| ① | `1222d44` | 删除 `LICENSE` 中 85 行重复残片 | — |
| ② | `6ef83a1` | 15 行应用声明移至 `NOTICE`；`LICENSE` 只留官方正文（676 → **661 行**） | GitHub 识别为 **`AGPL-3.0`** ✅ |

**副作用**：`LICENSE` **不再含版权人**（`Copyright (C) 2026 yaxiaiyuting` 现只在 `NOTICE`）。
三处打包脚本 + README 目录树只引用 `LICENSE` → 随包丢失版权声明。

> 副作用清单最早由 `docs/discoverability-report.md`（第 147–152 行）记录，
> 并给出「最小修法（3 处打包 + 1 处 README，均一行）」。

---

## 1. 修改清单

| 文件 | 改动 | 行数 | 关键行（修改后） |
| :--- | :--- | ---: | :--- |
| `packaging/build-deb.sh` | `copyright` = `NOTICE` + `---` + `LICENSE` 拼接；补 `chmod 644` | **+13/−1** | 注释 `:43–47`，拼接 `:48–54`，chmod `:55` |
| `PKGBUILD` | 装 `NOTICE` 到 `/usr/share/licenses/`（**含 tarball 存在性判断**） | **+10/−0** | `LICENSE` `:28`，守卫 `:36–38` |
| `packaging/bat2sh.spec` | `%install` 加 `NOTICE`；`%files` 加 `%license` 条目 | **+3/−0** | install `:43`/`:45`，`%license` `:65–66` |
| `README.md` | 目录树补 `NOTICE` **并注明两者分工** | **+2/−1** | `:70`（LICENSE）、`:71`（NOTICE） |

**`python/` 零改动**（`c0b540a` 的 numstat 仅上述 4 个文件，diff = 0 行）。
**未改动任何转换逻辑、测试、既有文档。**

### 1.1 逐处改动原文

**`packaging/build-deb.sh`**（Debian policy：`copyright` 必须**同时**含版权声明与分发许可证）

```bash
# Debian policy：copyright 文件必须**同时**含版权声明与分发许可证。
#   NOTICE  —— 版权人（Copyright (C) 2026 yaxiaiyuting）+ FSF 推荐 notice 块
#   LICENSE —— AGPL-3.0 官方正文（**不含**版权人：为让 GitHub SPDX matcher 能识别，
#              该文件必须只含标准许可证文本，见 docs/discoverability-report.md §4）
# 故此处两者拼接，缺一不可。
{
  cat NOTICE
  echo ""
  echo "---"
  echo ""
  cat LICENSE
} > "$STAGE/usr/share/doc/$PKG/copyright"
chmod 644 "$STAGE/usr/share/doc/$PKG/copyright"
```

> 原实现为单行 `install -Dm644 LICENSE "$STAGE/usr/share/doc/$PKG/copyright"` —— 只装 LICENSE
> 会丢掉版权人。

**`PKGBUILD`**

```bash
install -Dm644 LICENSE "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
# NOTICE 持有版权人与应用声明（LICENSE 为纯 AGPL-3.0 官方正文），两者应同装。
# …（见 §3 回归说明）
if [[ -f NOTICE ]]; then
  install -Dm644 NOTICE "${pkgdir}/usr/share/licenses/${pkgname}/NOTICE"
fi
```

**`packaging/bat2sh.spec`**（RPM 惯例：`%license` 段）

```spec
install -Dm644 %{repo}/LICENSE  %{buildroot}%{_datadir}/doc/bat2sh/LICENSE
# NOTICE 持有版权人与应用声明（LICENSE 为纯 AGPL-3.0 官方正文），两者必须同装
install -Dm644 %{repo}/NOTICE   %{buildroot}%{_datadir}/doc/bat2sh/NOTICE
…
%files
%license %{_datadir}/doc/bat2sh/LICENSE
%license %{_datadir}/doc/bat2sh/NOTICE
```

**`README.md`**

```diff
-├── LICENSE
+├── LICENSE                      # AGPL-3.0 官方正文（纯许可证文本）
+├── NOTICE                       # 版权与许可声明（版权人 + FSF notice 块）
```

---

## 2. 验证证据（三格式**实跑**，非仅脚本审查）

### 2.1 Debian（**必须项**）

| 项 | 值 |
| :--- | :--- |
| 构建 | `./packaging/build-deb.sh` ✅ 通过 |
| 产物 | `dist/bat2sh_2.9.0-1_all.deb`（**181 896 B**，2026-09-21 01:06） |
| `copyright` 行数 | **684** = 20（`NOTICE`）+ 3（空行/`---`/空行）+ 661（`LICENSE`） |
| 含版权人 | `Copyright (C) 2026 yaxiaiyuting` × **1** ✅ |
| 含完整 AGPL | `GNU AFFERO GENERAL PUBLIC LICENSE` × **1** ✅ |
| 分隔符位置 | `---` 在第 **22** 行（NOTICE 之后、LICENSE 之前）✅ |

**Debian policy 两项要求（版权声明 + 完整许可证文本）均满足。**

复核命令（只读）：

```bash
dpkg-deb -c dist/bat2sh_2.9.0-1_all.deb | grep -E "copyright|NOTICE|LICENSE"
dpkg-deb -x dist/bat2sh_2.9.0-1_all.deb /tmp/deb-check
wc -l /tmp/deb-check/usr/share/doc/bat2sh/copyright
grep -c "Copyright (C) 2026 yaxiaiyuting" /tmp/deb-check/usr/share/doc/bat2sh/copyright
grep -c "GNU AFFERO GENERAL PUBLIC LICENSE" /tmp/deb-check/usr/share/doc/bat2sh/copyright
```

### 2.2 RPM

| 项 | 值 |
| :--- | :--- |
| 构建 | `./packaging/build-rpm.sh` ✅ 通过（从**工作树**构建） |
| 产物 | `~/rpmbuild/RPMS/noarch/bat2sh-2.9.0-1.noarch.rpm`（**199 280 B**，01:06） |
| `rpm -qlp` | `/usr/share/doc/bat2sh/LICENSE` **与** `/usr/share/doc/bat2sh/NOTICE` ✅ |

### 2.3 Arch

| 项 | 值 |
| :--- | :--- |
| 构建 | `makepkg -f` ✅ 通过 |
| 产物 | `bat2sh-2.9.0-1-any.pkg.tar.zst`（**224 990 B**，01:07） |
| `tar -tf` | `usr/share/licenses/bat2sh/LICENSE` **与** `usr/share/licenses/bat2sh/NOTICE` ✅ |

### 2.4 汇总

| 格式 | 构建 | 版权人 | 完整许可证 |
| :--- | :---: | :---: | :---: |
| deb（`copyright`） | ✅ | ✅ | ✅ |
| rpm（`%license`） | ✅ | ✅ | ✅（同目录 `LICENSE`） |
| Arch（`licenses/`） | ✅ | ✅ | ✅（同目录 `LICENSE`） |

---

## 3. 过程中发现并修复的**真实回归**（PKGBUILD × tag tarball）

> 这是本次修复中**唯一超出「补一行」范围**的发现，独立记录。

**机制**：`PKGBUILD` 从 **tag tarball** 构建（见 `source=` 行），而 `NOTICE` 是在
**v2.9.0 之后**才加入仓库的 —— **v2.9.0 的 tarball 里没有该文件**。
若按最简写法无条件 `install NOTICE`，则当前版本（v2.9.0）下：

```
install: 对 'NOTICE' 调用 stat 失败: 没有那个文件或目录
```

→ `makepkg -si`（**README §3.1 记载的安装方式**）**直接失败**。

**修法**：加存在性判断 `if [[ -f NOTICE ]]; then … fi`。

**双向实测**：

| 场景 | 结果 |
| :--- | :--- |
| tarball **无** `NOTICE`（当前 v2.9.0 情形） | ✅ 构建成功，包内只有 `LICENSE` |
| tarball **有** `NOTICE`（下一版情形） | ✅ 构建成功，包内含 `LICENSE` + `NOTICE` |

> `deb` 与 `rpm` 从**工作树**构建，无此问题（均已实测通过）。
> 下一次版本 bump（tag tarball 含 `NOTICE` 后）本判断自然恒真，**可保留亦无害**。
> `PKGBUILD:29–35` 有一段注释专门防止后人把这个判断「清理」成无条件 install。

---

## 4. 附加只读扫描（确认**无第四处遗漏**）

| 位置 | 结论 |
| :--- | :--- |
| `.SRCINFO` / `pyproject.toml` | 用 SPDX 声明 `license = AGPL-3.0-or-later`，**不安装文件** → 无需 NOTICE |
| `packaging/build-rpm.sh` | 委托 `bat2sh.spec` → **已覆盖** |
| `install.sh`（免打包装到 `~/.local`） | 本就不安装任何许可文件，**非发行包路径** → 不在范围 |
| `packaging/android/` | 无许可安装逻辑（仅遗留构建产物） |

**扫描方法**：`grep -rn "LICENSE\|NOTICE"` 覆盖 `*.sh` / `PKGBUILD` / `*.spec` / `*.toml` /
`*.cfg` / `*.in` / `*.yml` / `.SRCINFO` / `*.md`（排除 `dist/`、`src/`、`packaging/android/build/`）。

---

## 5. 已知限制

1. **`lintian` 未安装**，未跑 `lintian` 检查（非阻塞项）。替代验证：`copyright` 已按
   Debian policy 两项要求人工逐项核对（§2.1）。
2. **产物为 v2.9.0 版本号**：本次修复未 bump 版本，包内版本仍为 `2.9.0`；三个产物是
   **验证产物**（`dist/` 与 `~/rpmbuild/`），未作为 Release 资产发布。
3. **Arch 包按 tarball 场景验证**：留在仓库根的 `bat2sh-2.9.0-1-any.pkg.tar.zst` 是
   §3「tarball 有 NOTICE」那一轮双向实测的产物，故包内**同时含** `LICENSE` 与 `NOTICE`。
4. **本地构建 ≠ CI**：三格式均在本机实跑，CI（`.github/workflows/test.yml`）只跑 pytest，
   不覆盖打包脚本。

---

## 6. 结论

> **修复完成，三格式验证通过。授权效力未受影响。**

- `LICENSE` 保持**纯 AGPL-3.0 官方正文**（661 行）→ GitHub SPDX 识别为 `AGPL-3.0` **不回归**。
- `NOTICE`（20 行，含版权人）随三种发行格式**一并分发** → 版权声明不再丢失。
- Debian `copyright` 满足 policy 的两项要求。
- 顺带修掉了 `PKGBUILD` × tag tarball 的真实回归（§3），且做了双向实测。
- `python/` 与转换逻辑**零改动**。

---

> **本文件为 `c0b540a` 的修复报告（补写）。** 起因清单见 `docs/discoverability-report.md`；
> 打包脚本见 `packaging/build-deb.sh`、`PKGBUILD`、`packaging/bat2sh.spec`。
