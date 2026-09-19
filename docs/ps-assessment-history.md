# PS 解冻评估 · 历史回顾（只读）

> 会话：PS 解冻只读评估。**全程只读，零代码改动。**
> 起点 HEAD（锁定）= `46d5d21`（v2.8.0 发布回填后 `main` tip）；`git status` 干净；pytest **1554 passed**。
> 本文件为交付物之一；配套 `ps-assessment-reality.md` / `ps-assessment-blockers.md` / `ps-assessment-verdict.md`。

---

## 一、冻结的由来与时间线

| 时间 | 事件 | 证据 |
| :--- | :--- | :--- |
| v1.3 | PS 定位为**实验性支持**（产物「高级草稿」，不保证行为等价） | `docs/PROJECT-OVERVIEW.md` §0.2、`docs/v2.3.0-2x-closure.md` §6 |
| v1.7.0 | PS 侧宣称「语法通过率 100%」——实为**降级口径**（15/60 整体降级仍计通过）；**原始口径实为 75.0%** | `docs/v1.8.0-roi.md` §2.1、§6、`docs/releases/v1.8.0.md` 已知限制 |
| **v1.8.0** | **PS 最后一次能力改动**：块结构加固 + 7 类发射缺陷修复（D1–D7）；原始口径 75.0% → **93.3%** | `docs/releases/v1.8.0.md`、`docs/v1.8.0-design.md` §2.2 |
| v1.8.0 起 | **PS 冻结**：其后 1.x / 2.x 全部精力在 bat 侧；PS 维持实验性、不再新增能力 | `docs/v1.11.0-1x-closure-final.md`、`docs/v2.3.0-2x-closure.md` §5/§6 |
| v2.3.0 | 2.x 收尾；明确 **3.x 唯一大方向 = PS 解冻**，但**需求驱动、未触发**；建议先做「PS 侧只读评估 session」 | `docs/v2.3.0-2x-closure.md` §5/§6/§8 |
| v2.8.0（当前） | 2.x 已收尾；本 session = 上述「PS 侧只读评估」的**执行** | `docs/pipeline-report.md` |

> **「冻结」的准确含义**：不是「PS 被禁用」，而是**停止向 PS 侧投入能力开发**。
> PS 路径始终可用（`convert_text(..., SourceKind.POWERSHELL, ...)`），产物为「可转换的转换、
> 不可转换的显式 TODO」，定位「高级草稿」。

---

## 二、冻结原因（v1.8.0 时的判定）

v1.8.0 的 ROI 裁定书（`docs/v1.8.0-roi.md`）与真实语料报告（`docs/real-corpus-report.md`）给出：

| 原因 | 内容 | 证据 |
| :--- | :--- | :--- |
| **原理性缺失（D 档）** | 对象模型（`$obj.Prop`）、`.NET` 静态调用、CIM/WMI、注册表、远程会话在 bash **无等价物** | `docs/real-corpus-report.md` §4（PS 侧 D 档 = 56%）、`docs/PROJECT-OVERVIEW.md` 已知限制 |
| **「完美转换」不可达** | 真实语料 D 档 > 40% → 按判据「完美转换」不成立 | `docs/real-corpus-report.md` §4 |
| **系统性发射缺陷**（当时） | 12 个真实 ps1 **全部降级**（>=1 个语法缺陷触发 never-emit-broken-bash） | `docs/real-corpus-report.md` §2 |
| **静默错误高** | 「看起来对、实际错」的语义偏离集中在 D 档 | `docs/releases/v1.8.0.md` PS 状态 |

**v1.8.0 冻结时的状态（任务书 §2.1 口径）**：

| 项 | 值 | 来源 |
| :--- | :--- | :--- |
| CC0 fleschutz PS 语料 | **约 664 文件**（`~/下载/PowerShell-1.6/scripts`；repo fixture 取其中 60） | 本 session 实测（`ls ... \| wc -l` = 664） |
| 语法通过率（原始口径） | **75.0%**（45/60，v1.8.0 修复前） | `docs/v1.8.0-roi.md` §2.1 |
| 运行时语义（实验口径） | **73.7%**（14/19，bwrap + pwsh 对照） | `docs/releases/v1.8.0.md` PS 状态 |
| D 档缺失 | 对象 / `.NET` / 注册表 / 远程 | `docs/real-corpus-report.md` §4 |

> **口径校正（纪律 4/10）**：任务书 §2.1 写「语法通过率 75.0%」= **v1.8.0 修复前**的数字；
> v1.8.0 修复后同口径为 **93.3%**（60 子集）。冻结「能力线」停在 93.3%，而非 75.0%。
> 本 session 以**实测**为准（见 `ps-assessment-reality.md`）。

---

## 三、冻结后 bat 侧做了什么（v1.8.0 → v2.8.0）

> 目的：判断 bat 侧积累的**共享基础设施**能否服务 PS。

| 版本 | bat 侧交付 | 对 PS 的潜在复用 |
| :--- | :--- | :--- |
| v1.9.0 | rc==0 严格口径（功能完好 / degraded 分离）+ 丢失检测 | 口径框架可直接套 PS |
| v1.10.0 | 四个只读子系统（名称映射 / 输出契约 / 控制流台账 / 词法残余额账） | 台账/校验器方法论可借鉴 |
| v1.11.0 | C2 收窄子集 + 1.x 收尾 | 需求驱动 T1/T2/T3 纪律 |
| v2.0.0 | 解析层 / 词法层硬化 | **PS 解析层正交**（PS 有独立 `core/powershell.py`） |
| v2.1.0 | CFG 只读数据模型 | bat 专用，PS 不可直接复用 |
| v2.2.0 | `sc` 结构化诚实 TODO | 「诚实 TODO」范式与 PS 一致 |
| v2.3.0 | 2.x 收尾（逐项实测） | 评估方法论 |
| v2.4.0 | goto CFG 可证安全子集 | bat 专用 |
| v2.5.0 | CFG 标签分派状态机（默认开启） | bat 专用 |
| v2.6.0 | 新语料验证 + 修 A-1（子报告丢弃） | **语料验证方法论**；A-1 与 PS 的「报告少计」同域（见 reality §4） |
| v2.7.0 | CLI 色彩/报告美化 | **PS 侧同样受益**（CLI 对所有源类型一致） |
| v2.8.0 | GUI 视觉优化 | 同上，GUI 对所有源类型一致 |

### 3.1 共享基础设施现状（可服务 PS）

| 设施 | 状态 | 对 PS 可用性 |
| :--- | :--- | :--- |
| `tools/corpus-analysis/measure.py` | bat 语料仪器（可复现） | bat 专用；PS 需 `ps_silent_check.py` |
| `tools/corpus-analysis/ps_silent_check.py` | **PS 语料仪器**（v1.8.0，可复现；bash-only 模式） | ✅ 可用（本 session 验证：56/60 与 pytest 一致） |
| bwrap 沙箱 | ✅ 就绪 | ✅ 可复现运行产物 |
| wine 黄金对照 | bat oracle | ❌ 不适用 PS |
| CI（3.12/3.13/3.14） | ✅ 就绪 | ✅ PS 语法口径已在 `test_real_corpus_metrics.py` 常驻 |
| **pwsh 运行时 oracle** | ❌ **本机未安装**（无 pwsh / dotnet / 便携副本） | ❌ **PS 语义对照不可复现**（见 reality §5） |

### 3.2 PS 的原始障碍有没有缓解？

| 维度 | v1.8.0 时 | 现在 | 变化 |
| :--- | :--- | :--- | :--- |
| PowerShell on Linux | PS 7.x 已跨平台 | 同上 | 生态成熟，但**与本项目无关**（我们要转的是 **bash**，不是跑 pwsh） |
| 对象模型 / `.NET` / CIM / 注册表 / 远程 | bash 无对应 | **仍无对应** | **未缓解** |
| pwsh 作为 oracle | v1.8.0 用便携 pwsh 7.4.6（`/tmp/opencode/b1/pwsh`） | **本机已无 pwsh** | **退化**（运行时验证设施缺失） |
| PS 解析层 | `core/powershell.py` 块结构 | 未再改动 | 持平（4/60 语法失败原样保留） |

> **结论**：bat 侧积累了可复用的**仪器/口径/纪律/CI 框架**，但 PS 的**原理性障碍（bash 无对象模型）
> 未发生任何缓解**；且**运行时 oracle（pwsh）反而缺失**。

---

## 四、冻结触发条件（原定）与当前状态

沿用 `docs/v1.11.0-1x-closure-final.md` §6 的**需求驱动**触发器：

| 触发 | 定义 | 当前 |
| :--- | :--- | :--- |
| **T1 真实需求（非理论）** | 有明确真实语料 / 用户目标要求 PS 侧支持 | **未触发**（本 session 无具体迁移目标） |
| **T2 维护期回归** | 维护期发现由该方向导致的回归/高危缺陷 | **未触发**（PS 自 v1.8.0 未改动，无回归） |
| **T3 外部触发** | 生态变化或 PS 侧出现**刚需**（明确 PS 目标/语料） | **未触发**（有 CC0 语料，但**无「刚需」需求**） |

> **本 session 的定位（任务书 §2.3）**：它是 **T3 判定的「输入」，不是输出**。
> 本 session 不制造需求；只提供是否具备解冻条件的事实基础。

---

## 五、历史回顾小结

1. **PS 冻结 = 停止投入能力开发**，非禁用；路径仍可用（高级草稿 + 诚实 TODO）。
2. 冻结判据是 **D 档原理性缺失（bash 无对象模型）** + 「完美转换不可达」。
3. v1.8.0 已把语法（原始口径）从 75.0% 提升到 93.3%（60 子集），此后**未再改动**。
4. bat 侧 v1.8.0→v2.8.0 积累的**仪器/口径/CI/纪律**可服务 PS；但**原理性障碍未缓解**，
   且 **pwsh 运行时 oracle 缺失**。
5. **T1/T2/T3 均未触发**。本 session 提供事实，不解冻。

---

> **本文件为只读历史回顾。** 实测见 `ps-assessment-reality.md`；障碍评估见 `ps-assessment-blockers.md`；
> 判定见 `ps-assessment-verdict.md`。
