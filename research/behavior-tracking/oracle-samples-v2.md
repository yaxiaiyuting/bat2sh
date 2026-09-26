# oracle 扩样本 —— 样本选取 v2（第二批）

> 时间：本 session · 轨道：`research/behavior-tracking`（研究设施）
> 起点 HEAD：`70a0ddb` → 修复后 `faee2f7`
> 上一批：`oracle-samples.md`（V1–V5，5 个）
> **本批目标：20 个样本**

---

## 0. 关键发现：20 个样本在原定标准下**不可达**（主动披露）

任务书要求「对 **20 个**样本逐个采集」。主 session 先做**样本可行性核查**，结论：

| 项 | 实测 |
| :--- | :--- |
| 可用语料 | `~/下载/非常批处理`（**151** 个 `.bat/.cmd`）+ 其余本地脚本，合计 **246** |
| 同时用 `classify_corpus.py` 对**全集**分类 | **A 类只有 4 个**（238 C / 4 A / 4 B） |
| O1 标准（`oracle-design.md` §9） | **只有 A 类（纯文件操作）的 W/L 差异可以归因** |

> **⇒ 语料里不存在 20 个可归因样本。** 强行凑 20 个 C 类样本只会产出
> 「不可归因但无法归因于 bat2sh」的噪声，**违背 oracle 的设计目的**。

**本 session 的处置（主动披露的偏离）**：把 20 个样本重新定义为
**「4 个真实 A 类 + 4 个真实 B 类 + 4 个仓库内样本 + 8 个定向构造样本」**，
并**显式标注每个样本的归因等级**。定向样本**不是**为了"凑数"，
而是把 Phase A 的安全审查结论**从静态推断提升为真机差分证据**（见 §3）。

> ⚠️ 另一处披露：主 session 起初把语料数报成 **144**（`find -name '*.cmd'` 大小写敏感，
> 漏掉 `.CMD`）。**正确值是 151**，与 `measure.json` 的 `corpus=151` 一致。
> 该更正已由修复 subagent 独立复核。

---

## 1. 样本清单（21 个，含 1 个补充）

| # | guest 名 | 源文件 | 来源 | 类别 | 覆盖 |
| :-: | :--- | :--- | :--- | :-: | :--- |
| 1 | `v1.bat` | `快速创建文件夹.bat` | 非常批处理 | **A** | 创建目录 |
| 2 | `v2.bat` | `生成指定内容的文本文件.bat` | 非常批处理 | **A** | 中文内容落盘 |
| 3 | `v3.bat` | `samples/poc-02-fileops.bat` | 本仓库 | **A** | 写/读/复制/删除 |
| 4 | `v4.bat` | `tools/samples/copy.bat` | 本仓库 | **A** | 复制 + 根外探针 |
| 5 | `v5.cmd` | `以文件夹名为名建立文本文件.cmd` | 非常批处理 | **A** | 递归遍历 + `%%~ni` |
| 6 | `other.bat` | `tools/samples/other.bat` | 本仓库 | A | 辅助样本 |
| 7 | `poc01.bat` | `samples/poc-01-stdout.bat` | 本仓库 | **A** | stdout 通道（阴性对照） |
| 8 | `w1.bat` | `w1-findstr-errorlevel.bat` | **定向构造** | A | **`findstr`+`if errorlevel`**（Phase A R4） |
| 9 | `w2.bat` | `w2-redir-glob.bat` | **定向构造** | A | **重定向目标 glob**（Phase A H8） |
| 10 | `w3.bat` | `w3-dollar-literal.bat` | **定向构造** | A | **字面 `$()` 注入**（Phase A R1） |
| 11 | `w4.bat` | `w4-for-r-dotted.bat` | **定向构造** | A | **含点祖先 + `%%~ni`**（Phase C 主体） |
| 12 | `w5.bat` | `w5-del-recurse.bat` | **定向构造** | A | `del /s` 递归删除 |
| 13 | `w6.bat` | `w6-set-a-percent.bat` | **定向构造** | A | `set /a` 中 `%VAR%*`（Phase A 中危） |
| 14 | `w7.bat` | `w7-tree-copy.bat` | **定向构造** | A | `xcopy /e /i /y` 树复制（H10） |
| 15 | `w8.bat` | `w8-for-d-rd.bat` | **定向构造** | A | `for /d` + `rd /s /q` |
| 16 | `w9.bat` | `卸载瑞星杀毒软件2008批处理版.bat` | 非常批处理 | **A** | 不存在目标的删除（no-op 对照） |
| 17 | `w10.bat` | `合并同名的图片和rar文件.bat` | 非常批处理 | B | 通配符 |
| 18 | `w11.bat` | `指定每天运行的程序.bat` | 非常批处理 | B | 时钟依赖 |
| 19 | `w12.cmd` | `提取两个文件内容的不同之处.cmd` | 非常批处理 | B | `for /f` + `findstr` |
| 20 | `w13.bat` | `运行a.txt中的程序.bat` | 非常批处理 | B | `for /f` |
| 21 | `w14.bat` | `w14-for-r-rd-self.bat` | **定向构造** | A | **`for /r` + `rd` 自删整树**（Phase A H4，最高危） |

**合计**：真实语料 9（A 5 + B 4，含 w9）· 仓库样本 4 · 定向构造 8 ⇒ **21 个**。

> **w9 是本批唯一"新"的真实 A 类样本** —— 语料的 A 类只有 4 个，其中 3 个已在第一批用过。

---

## 2. 定向样本的设计约束

### 2.1 必须**自包含**（否则差分无意义）

oracle 的 W 侧**只上传样本文件本身**（`known_artifacts = [harness upload]`，实测确认）。
⇒ 定向样本必须**自己造前置条件**。例：

```bat
@echo off
> haystack.txt echo needle      & rem 自造前置：haystack 确实含 needle
> keep.txt echo PRECIOUS
findstr "needle" haystack.txt >nul
if errorlevel 1 del keep.txt
echo done
```

若不自造，W/L 两侧都因缺文件而失败 ⇒ **测不到目标缺陷**（第一版设计即犯此错，已修正）。

### 2.2 不得破坏 VM

- 全部限定在 `C:\poc\samples` 内（scope 见 §4）
- 不用交互式命令（`copy` 无 `/y` 会提示 ⇒ 排除）
- `w14` **故意**会删掉工作树 —— 靠 overlay 回滚保证可重复（这正是它的测试点）

### 2.3 归因等级显式标注

B 类样本（`w10`–`w13`）**天生可能不可归因**（时钟 / 外部依赖 / 解析风险），
在结果表中**单独标注**，不与 A 类混算缺陷密度。

---

## 3. 定向样本与 Phase A 的对应

| 样本 | 对应 Phase A 结论 | 目的 |
| :--- | :--- | :--- |
| `w1` | **R4**（`errorlevel` 恒真） | 用真机差分证明「W 不删 / L 删」 |
| `w3` | **R1**（字面 `$()` 注入） | 用 W 产物文件内容证明「W 写字面量 / L 执行」 |
| `w14` | **H4**（`for /r` 首值 = CWD） | 用真机确认 **cmd 是否也自删**（A-3 标 `[cmd 侧未实测]`） |
| `w4` | **Phase C**（`%%~n` 顺序倒置） | 修复前后的差分对照 |
| `w7` | **H10**（`xcopy` 覆盖语义） | 真机确认 xcopy 是否提示 |
| `w6` | 中危（`%VAR%*`） | 真机确认是否中止脚本 |

> **这是本批最重要的设计意图**：Phase A 的高危结论**全部建立在 Linux 侧推断上**，
> 且 subagent 主动标注了「cmd 侧未实测」。定向样本把其中 **6 条**转成**真机差分证据**。

---

## 4. 仪器口径（含一次**主 session 自查纠正**）

| 项 | 值 | 说明 |
| :--- | :--- | :--- |
| W scope | `C:\poc\samples` | **与第一批一致** |
| L run-name | `samples` | 必须与 W 的 basename 一致 |
| 网络 | `isolated` | 两侧结构性零出网（实测 `egress_frames=0`） |
| L 转换器 | `/tmp/b2s-bin/bat2sh` → 本仓库工作树 | 指纹记录 `l_head=faee2f78` |

### 4.1 ⚠️ 主 session 自查发现的仪器错误（已纠正）

**第一次 W 采集误用 `--scope 'C:\poc'`**（而非文档口径 `C:\poc\samples`）。
后果：`C:\poc` 下的 **QEMU guest-agent 安装残留**
（`INSTALL-LOG.txt` / `ga-install.log` / `ga.log` / `gt.log` / `qemu-ga-x86_64.msi` / `virtio-win-gt-x64.msi`）
被计入 `fs_content.only_in_w` ⇒ **`poc01` 等样本被误判为「不可归因」**。

**证据（实测对比）**：

| 口径 | `filesystem.scope` | `baseline_manifest` 条数 |
| :--- | :--- | ---: |
| 第一批（正确） | `['C:\\poc\\samples']` | **0** |
| 主 session 首次（错误） | `['C:\\poc']` | **6** ← 全是设施残留 |

**处置**：**丢弃**首次全部 W 指纹，用 `C:\poc\samples` **重采全部 15 个**。
本文件与 `oracle-result-v2.md` 的所有数据均来自**重采后**的口径。

> 这条正是纪律 6「**仪器先验证**」的价值：`poc01` 是**阴性对照**
> （纯 stdout、不碰文件系统），它被判「不可归因」本身就是**仪器坏了的信号**。

---

## 5. 与第一批的关系

| | 第一批（V1–V5） | 本批 |
| :--- | :--- | :--- |
| 样本数 | 5 | **21** |
| 选取依据 | 手工 + A 类 | **`classify_corpus.py` 全量分类 + 定向构造** |
| W 口径 | `C:\poc\samples` | 同 |
| 目的 | 找未知缺陷（探索） | 找未知缺陷 **+ 验证 Phase A/C 结论**（确认） |

**可比的 5 个**（v1–v5）用**同一 W 指纹口径**重跑 L ⇒ 支持**跨批对照**。
