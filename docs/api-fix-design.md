# bat2sh v1.4 阶段 6a：用户 API 修复 TODO —— 设计诊断（只读）

> 诊断对象：HEAD = `8529755`（原始诊断基线为 `386ccb3`；P0 四提交后行号已全文刷新，见附录 B），最新 tag `v1.3.0`
> 基线：`pytest -q` = **711 passed**（刷新时重跑；原始基线 386ccb3 时为 689 collected）
> 运行环境：Python 3.14.7（`tomllib` 可用），PySide6 已装
> 本文为**只读诊断设计稿**：未改任何代码、未实现任何功能、未 commit、未建 PR。
> 文中所有行号均指当前 HEAD 的实际文件；所有"建议/推荐"均先给方案对比再结论。

---

## 0. 结论速览（供拍板）

1. **现有 TODO 机制：数据结构健全，但"逐条唯一定位到输出行"的能力不足。**
   `Diagnostic`（源行号 + message + original + category）是**源文件侧**的语义记录；
   生成脚本里的 `# TODO` 注释与 `report.todos` **不是 1:1**（有诊断无注释、有注释无诊断、多诊断合一注释、注释非行首）。已用探针实证（§1.4）。
   → **决策 5（逐条发送）与决策 7（diff 后写入）对"定位"的要求，现有结构不能直接满足**，需要一个明确的"TODO 锚点"方案（§1.5）。这是本阶段最大的技术风险。

2. **配置系统：项目已有 XDG + JSON 的成熟先例**（`settings.json` / `presets.json` / `recent.json`）。
   任务提示里的"TOML"是可选项而非既定决策；本文对比后**推荐 JSON 新文件 `~/.config/bat2sh/api.json`**，理由见 §2.2（核心是：不新增依赖、与既有三份 JSON 一致、密钥与 GUI 频繁改写的 settings 分离）。

3. **Provider 抽象可保持"薄"**（决策 2）：`Provider.complete(prompt) -> str` 用 `Protocol` 表达，OpenAI 兼容实现基于 **stdlib `urllib.request`**（保持"核心引擎只依赖标准库"，README:5 / `__init__.py:3`）。可注入 transport 以便无网络测试。

4. **9 条既定决策之间未发现互相冲突**；但有 **3 处"实现现实 vs 决策/任务建议"的落差**必须由人拍板：
   - `--fix-todos` 的**非交互**场景与决策 8（每次提示、不记忆）如何共存（§4.2 / §9-Q1）；
   - 决策 9（API 只服务 C 档）与代码里**没有 A/B/C/D 分档器**的现实（§3.4 / §9-Q2）；
   - 任务提示的 **TOML** 建议与项目既有 **JSON** 惯例（§2.2，属偏离说明，不违反 9 条）。

5. **反对方最需要听的一点**：本项目第一纪律是"保守 TODO 优于激进转换"，而 LLM 最擅长的恰恰是产出"看起来对、实际错"的 bash。本设计因此把 **绝不自动写盘、逐条人确认、结果强制 `bash -n`、失败保留原 TODO** 作为硬边界（§4、§5、§10-R1）。

---

## 1. 现有 TODO 机制梳理

### 1.1 TODO 产生路径（`_convert_*` → `report`）

所有 TODO 都经由两个转换器内的私有方法写入 `ConvertReport`：

**批处理**（`python/bat2sh/core/batch.py`）
| 方法 | 位置 | 作用 | 写入的 report 列表 |
|---|---|---|---|
| `_todo(lineno, original, hint, category)` | `batch.py:619-627` | 生成 `# TODO: 手动检查: <original>`，message 附 `（hint）` | `report.todos` |
| `_error(lineno, original, hint, category)` | `batch.py:629-641` | 同上注释文本，但语义为"必须处理" | `report.errors` |
| `_todo_block_line(...)` / `_error_block_line(...)` | `batch.py:651-655` | 包裹 `_manual_block_line`（不配对括号时挂起块） | 转发上面两者 |
| `_pipeline_todo(lineno, text, hint)` | `batch.py:657-664` | 有建议时输出 `# TODO: 复杂管道需手动重写` + `#` 注释建议行 | `report.todos`（经 `_todo`） |
| 内联条件 TODO | `batch.py:1554-1560`、`1573-1574` | 输出 **行内** `( # TODO: 手动检查条件: <expr> )` 替代条件 | `report.todos`（仅 1554 分支调用 `_todo`；1574 只 `_warn`！） |

调用点（节选）：`batch.py:1214, 1314, 1316, 1337, 1382, 1480, 1760, 2043, 2145-2151, 2206, 2254, 2265, 2283, 2339, 2770-2776, 2869, 2918-2997`。
`batch.py:6` 与 `batch.py:634` 明确约定：**生成脚本中的 `# TODO: 手动检查` 注释约定保持不变，便于用户统一检索**（重要：这条内部约定限制了"给 TODO 加唯一 id"的改法）。

**PowerShell**（`python/bat2sh/core/powershell.py`）
| 方法 | 位置 | 说明 |
|---|---|---|
| `_todo(lineno, original, hint, category)` | `powershell.py:140-147` | 与批处理同形：`report.todos` + `# TODO: 手动检查: <original>` |
| `_emit_last_exit_code_warn` | `powershell.py:519-544` | 行尾追加 `  # TODO: 手动检查 $LASTEXITCODE 条件`（**行内**，`533`） |
| `$LASTEXITCODE` map/warn 兜底 | `powershell.py:546-601` | 部分只 `_warn` |
| 其它 `_todo` 调用 | `powershell.py:909, 912, 965, 969, 971, 984` | 多行注解 / attribute / 类型转换 / 嵌套 try 等 |

**语法降级**（`python/bat2sh/core/syntax.py`）
- `record_syntax_error`（`syntax.py:58-60`）：把 `bash -n` 失败记入 **`report.errors`**，`category="syntax"`，**`line=0`**。
- `degraded_script`（`syntax.py:63-76`）：整份脚本降级为注释，并在头部写
  `# TODO: 生成脚本未通过 bash -n 语法检查，已降级为注释`（`syntax.py:71`）——**这条 `# TODO` 不对应任何 `report.todos` 条目**。
- 触发点：`batch.py/powershell.py` 的 `convert()` 末尾（`powershell.py:118-122`）。

### 1.2 TODO 数据结构（`python/bat2sh/core/types.py`）

```python
# types.py:50-62
@dataclass
class Diagnostic:
    line: int          # 源文件行号（不是输出行号！）
    message: str       # "手动检查: <original>（<hint>）"
    original: str = "" # 源命令原文
    category: str = "" # command/control_flow/errorlevel/glob/path/pipeline/params/objects/strings/variables

    def format(self) -> str:
        if self.original:
            return f"第 {self.line} 行: {self.message} ｜ 原命令: {self.original}"
        return f"第 {self.line} 行: {self.message}"
```

```python
# types.py:65-89
@dataclass
class ConvertReport:
    ...
    warnings: list[Diagnostic] = field(default_factory=list)
    todos:    list[Diagnostic] = field(default_factory=list)
    errors:   list[Diagnostic] = field(default_factory=list)
    @property
    def todo_count(self) -> int: return len(self.todos)
```
- 序列化：`to_dict/to_json`（`types.py:100-118`）、`to_text`（`120-144`）、`report_blocks`（`163-191`，级别 `info/error/warning/todo/normal`）。
- 分类标签：`types.py:9-21`（`command/control_flow/…/variables` + "其他"）。

**关键属性**：`Diagnostic` **不携带输出行号、输出列、也不携带源文件片段本身**（`original` 只是被替换的那条命令，不含上下文）。`line` 是**源**行号。

### 1.3 TODO 呈现形态（生成脚本内）

实测/代码确认，生成脚本里的"TODO 相关文本"至少有 **6 种形态**：

| 形态 | 例（实测） | 是否行首 | 有 `report.todos` 条目？ |
|---|---|---|---|
| M1 标准整行 | `# TODO: 手动检查: wmic os get caption` | 是 | 有（`_todo`）；`_error` 形态相同但在 `errors` |
| M2 管道整行 | `# TODO: 复杂管道需手动重写` + 若干 `#` 建议行 | 是 | 有（但注释文本**不含 original**） |
| M3 行尾追加 | `if [[ false ]]; then  # TODO: 手动检查 $LASTEXITCODE 条件` | 否（行内） | 有 |
| M4 行内嵌入 | `[ 0 -eq 1 ]; then` 前的 `# TODO: 手动检查条件: <expr>` | 否（行内） | 有 |
| M5 文件头声明 | `# 带有 # TODO 标记的行无法自动转换，请人工检查` | 是 | **无**（纯说明，含 `# TODO` 子串） |
| M6 整体降级头 | `# TODO: 生成脚本未通过 bash -n 语法检查，已降级为注释` | 是 | **无**（属 `errors`，`line=0`） |

> 注意 M5 含子串 `# TODO`，任何"grep TODO 计数"都会被它污染（实测见 §1.4）。
> GUI 现有 TODO 强调正则 `_TODO_RE = r"^#\s*TODO.*$"`（`highlighter.py:107`，逐行匹配）→ **M3/M4 行内 TODO 在 GUI 里当前不会被高亮**。

### 1.4 逐条发送的前提：能否唯一定位每条 TODO？（**实证**）

**结论：不满足唯一定位。** 以下为只读探针实测（`PYTHONPATH=python`，未落盘）：

```
== ps_many: todos=3 errors=0 markers(含M5)=3
   TODO diag line=1 cat='errorlevel' orig='if ($LASTEXITCODE -ne 0) { Write-Host "x" }'
   TODO diag line=3 cat='objects'    orig='[System.IO.File]::ReadAllText("a")'
   TODO diag line=3 cat='misc'       orig='[System.IO.File]::ReadAllText("a")'   ← 同一源行 2 条
   实际输出里的动作性注释只有 2 处（M3 行内 + M1 整行）；2 条诊断合并为 1 条 M1
== bat_inline_cond: todos=2 errors=0 action-markers(含M5)=1
   TODO diag line=2 cat='control_flow' orig='"a*b"=="c" echo yes'   → 输出行内 M4
   TODO diag line=3 cat='command'      orig='wmic os get caption'   → 输出里完全没有对应 TODO 注释！
== bat_pipeline_suggestion: todos=1 markers=2
   marker out-line=3 = M5 文件头（假阳性）；out-line=6 = M1 真 TODO
```

归纳出 4 类定位障碍：
1. **多诊断 → 一注释**：同一源行的伴生诊断（objects + misc）共用一条注释（`real-corpus-report.md` §3 也按"同行合并计 1"统计）。
2. **有诊断 → 无注释**：如 `bat_inline_cond` 的 `wmic`（该命令被当作上一行 `if` 的体消费/替换，`batch.py` 侧无独立注释产出）。
3. **有注释 → 无诊断**：M5 文件头；M6 降级头（且 `errors` 条目 `line=0`）。
4. **注释位置不统一**：M3/M4 在行内；M2 是无 original 的多行块。

同时，**输出文本在写出前会被拼接/缩进/函数体归集**（`_c`、`_active_bucket`、`_compose`、函数体缓冲），因此"发射时刻的输出下标"与"最终输出行号"也不直接相等——即使想在转换器里记录下标，也要处理这一层偏移。

### 1.5 定位能力评估与候选方案（先对比，后推荐）

以"一个可替换单元 = 生成脚本中一处动作性 TODO 标记"为口径（**不是** `report.todos` 条目）：

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **A. 输出后扫描 + 对齐** | 转换完成后扫描 `text` 的 M1/M2/M3/M4，按形态切出"承载行/块"；再用 (源行号, original) 与 `report.todos` 做**尽力对齐**，取不到元数据也能工作（M1 自带 original） | 改动最小、可纯函数化、无侵入转换器；对 M1/M3 足够可靠 | M2 无语义 original；"多诊断→一注释"无法反推是哪种档；行内标记的替换跨度需规则定义 |
| **B. 发射期锚点** | 转换器在 `_todo/_error/_pipeline_todo` 处登记"该注释落在哪一段产出"，`_compose` 时换算成最终行号，挂到 `Diagnostic`/新结构 | 唯一、精确；一劳永逸 | 需改转换器内部（输出下标随缩进/函数体缓冲漂移）；改动面与回归风险高于 A |
| **C. 注释里嵌唯一 id**（如 `# TODO[id=7]: …`） | 让标记自描述 | 定位最省事 | **与 `batch.py:634` 的既有约定直接冲突**（注释约定须保持、便于用户 grep），且改动用户可见产物 |

**推荐 A 作为 6b 的落地方案，并把 B 记为"若 A 出现真实歧义时的加固路径"；C 明确不采纳。**
理由：A 不触碰转换器核心（符合"只读诊断先行 / 最小改动"），且实测里占主体的 M1/M3 自带可对齐的 `original`；M2 与"有诊断无注释"两类本就不适合逐条 API 修复，直接标为"不可自动修复"更诚实。
针对 A 的替换跨度，建议明确规则：
- M1：替换**整行**；
- M3/M4：替换**整条输出行**（行内含其它语义时给出"整行重写"预警）；
- M2：替换**整块**（标记行及其紧随的 `#` 建议行）；
- M5/M6：不进入工作列表（M6 直接判定"整份降级，拒绝修复"）。

---

## 2. 配置系统设计建议

### 2.1 现状（**项目已有配置系统**，只是不含 API 配置）

| 文件 | 位置 | 格式 | 内容 | 读取方 | 写入方 | 写入原子性 |
|---|---|---|---|---|---|---|
| `settings.json` | `~/.config/bat2sh/` | JSON | `ConvertSettings`（输出/风格/主题/最后目录/运行超时） | **仅 GUI**（`app.py:83`） | GUI（`main_window.py:953/968/1028`） | ❌ 直接 `write_text`（`settings.py:100-103`） |
| `presets.json` | 同上 | JSON | 命名预设 | GUI（`dialogs.py:171`） | GUI（`settings.py:166-174`） | ✅ `.tmp` + `replace` |
| `recent.json` | 同上 | JSON | 最近文件 | GUI（`main_window.py:147`） | GUI（`recent.py:58-64`） | ✅ `.tmp` + `replace` |

关键事实：
- 路径解析统一为 `XDG_CONFIG_HOME or ~/.config`（`settings.py:78-80`、`recent.py:13-15`）。
- **CLI 完全不读配置文件**：`settings_from_args`（`cli.py:144-159`）只用 argparse 结果构造 `ConvertSettings`；`load_settings` 的调用点**只有** `gui/app.py:83`（grep 证据）。
- 容错解析有现成范式：`preset_from_dict`（`settings.py:116-140`，类型不符回退默认、不抛异常）、`parse_presets_json`（`settings.py:143-155`）。
- **数值字段先例（P0 b4ebfcd）**：`ConvertSettings.run_timeout` 已走通全链路——字段默认值 + `normalized()` 夹取（1–3600s）+ `preset_from_dict` 数值类型容错 + `SettingsDialog` `QSpinBox`（1–3600 秒）+ 持久化往返测试。API 配置若并入 `settings.json`，改造面与此同形；本文推荐独立 `api.json`（§2.2）的判断不变。
- **核心引擎只依赖标准库**（`README.md:5`、`python/bat2sh/__init__.py:3`）→ 新增运行时依赖需强理由。

### 2.2 配置文件：格式与位置（方案对比）

决策 3 只规定"优先级 CLI > env > 文件；GUI = 配置文件可视化编辑"，**未规定格式**。任务提示给出"TOML"是可评估项。

| 方案 | 载体 | 优点 | 缺点 |
|---|---|---|---|
| **A. 扩展现有 `settings.json`** | 同文件加 `api` 子对象 | 单文件；GUI 已在写它；直接满足"GUI 可视化同一文件" | 密钥混进 GUI **频繁整体重写**的文件（切主题/关窗都会重写，`main_window.py:968/1028`）；`ConvertSettings` 是扁平 dataclass + `asdict`，加嵌套需额外结构；`load_settings` 会过滤未知键（`settings.py:89-90`），改造面不小；`save_settings` **非原子** |
| **B. 新增 `~/.config/bat2sh/api.json`（JSON）** | 同目录、新文件 | 与既有 3 份 JSON 惯例一致；XDG 路径逻辑现成；可复用 `.tmp+replace` 原子写（`recent.py:62-64`）；密钥与 GUI settings 生命周期分离；CLI 可独立读取 | 多一个文件 |
| **C. 新增 `~/.config/bat2sh/config.toml`（TOML，任务提示）** | 同目录、新文件 | 支持注释、手工编辑友好 | **写库成本**：`tomllib` 只读（3.12+ 仅解析），写需 `tomli-w`（**新依赖，违反"核心仅标准库"**）或手写序列化（转义易错）；与既有 3 份 JSON 不一致 |
| D. 全量迁移到 TOML | 替换 3 份 | 格式统一、可注释 | 迁移 + 兼容成本，超出阶段 6 范围；破坏既有用户配置 |

**推荐 B**：`~/.config/bat2sh/api.json`，JSON，原子写。
理由排序：① 零新依赖（守住核心 stdlib-only）；② 与 `presets.json`/`recent.json` 的"容错解析 + 原子写"范式一致，可直接照抄；③ 把密钥与"切主题就重写"的 settings 解耦，降低误写/混入备份的风险。
**偏离说明**：这与任务提示里的"TOML"不一致——属**方案偏离**（因依赖与惯例成本），**不违反** 9 条既定决策。若人坚持 TOML，代价是引入 `tomli-w`（或自写 writer）并接受风格不统一，需显式批准。

### 2.3 加载 / 合并 / 校验 / 优先级落地

建议新增 `python/bat2sh/core/api/config.py`（core，stdlib-only）：

```python
@dataclass
class ApiConfig:
    provider: str = "openai"       # 预留多 provider；当前仅 openai 兼容
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"     # 占位，需人确认默认值策略（见 §9-Q3）
    api_key: str = ""              # 通常留空，走 env
    timeout: float = 30.0
    max_retries: int = 1
    context_lines: int = 3         # 发送边界（§4.1）
```

- **加载**：`load_api_config(path=None) -> ApiConfig`，容错解析（坏 JSON → 默认值），照 `preset_from_dict` 的类型回退范式。
- **合并（优先级 CLI > env > file）**：
  ```python
  def resolve_api_config(cli: dict, env: Mapping, file: ApiConfig) -> ApiConfig
  ```
  逐字段：CLI 显式给出 → 用 CLI；否则 env（如 `BAT2SH_API_BASE`/`BAT2SH_API_MODEL`/`BAT2SH_API_PROVIDER`/`BAT2SH_API_KEY`/`BAT2SH_API_TIMEOUT`）→ 否则 file → 否则默认。
  只有"非 None 的显式项"参与覆盖（argparse 的默认值要设成 `None` 才能区分"未给"）。
- **校验**：`ApiConfig.normalized()` 照 `ConvertSettings.normalized()`（`settings.py:52-75`）：非法 provider 回退、`timeout<=0` 回退、`base_url` 去尾斜杠、`context_lines` 夹在 `[0, 10]`。
- **生效时机（最小侵入）**：**仅当** `--fix-todos` 或 API 相关 flag/env 出现时才 `resolve_api_config`；不改变现有 CLI 行为（现有 CLI 不读配置这一点保持不变）。

### 2.4 GUI 写回同一文件

- `SettingsDialog`（`dialogs.py:39-226`）已是 `QFormLayout` 组织，可**新增一组"API 修复"区块**（provider 下拉 / base_url / model / timeout / context_lines / api_key 掩码输入），`result_settings` 之外新增 `result_api_config()`；`MainWindow.open_settings`（`main_window.py:948-959`）在 accept 后既 `save_settings` 又 `save_api_config`。
- 或新增独立 `ApiSettingsDialog`，从工具栏/设置里进入。二选一，**推荐并入现有设置对话框**（少一处入口、决策 3 的"同一文件可视化"最直接）。
- 写回用 `save_api_config`（`.tmp+replace` 原子写）；若含明文 key，落盘后 `os.chmod(path, 0o600)`（§4.3）。

---

## 3. Provider 抽象

### 3.1 薄接口签名建议（对齐决策 1/2）

```python
# python/bat2sh/core/api/provider.py（stdlib-only）
from typing import Protocol

class Provider(Protocol):
    def complete(self, prompt: str, *, timeout: float) -> str:
        """把 prompt 发给模型，返回纯文本回复。失败抛 ProviderError（分类见 3.2）。"""
```

- 抽象"薄"到只有 `complete`；**prompt 构造、回复清洗、diff/写回都不在 provider 内**（拆到 `fixer.py` 的纯函数，便于测试与复用 CLI/GUI）。
- 选择器：`create_provider(config: ApiConfig) -> Provider`，内部 `if config.provider == "openai": return OpenAICompatibleProvider(config)`。

### 3.2 OpenAI 兼容实现要点

- **endpoint 可配置**：请求 `POST {base_url}/chat/completions`，body
  `{"model":…, "messages":[{"role":"user","content":prompt}], "temperature":0, "stream":false}`。
  同一实现即可覆盖 OpenAI / Ollama(`/v1`) / vLLM / LM Studio（它们的 OpenAI 兼容层都接受该形状）。
- **API key 来源**：由 §2.3 的 `resolve_api_config` 决定。**本地端点常无 key** → 允许 `api_key==""`，此时不发送 `Authorization` 头（而非发空 Bearer）。
- **超时**：用 `urllib.request.urlopen(req, timeout=config.timeout)`；`timeout` 覆盖连接+读取。
- **重试**：仅对**幂等安全**的失败重试（网络错误 / 429 / 5xx），最多 `max_retries`，退避 `1s, 2s…`；**不重试** 4xx（除 429）。
- **错误分类**（自定义异常，供 CLI/GUI 分档展示与降级）：
  | 异常 | 触发 | 处置 |
  |---|---|---|
  | `ProviderAuthError` | 401/403 | 提示检查 key；终止本项，不重试 |
  | `ProviderRateLimitError` | 429 | 退避重试；用尽则降级 |
  | `ProviderServerError` | 5xx | 退避重试；用尽则降级 |
  | `ProviderTimeoutError` | socket 超时 | 可重试一次 |
  | `ProviderNetworkError` | DNS/连接失败 | 可重试；用尽则降级 |
  | `ProviderProtocolError` | 响应非 JSON / 缺 `choices[0].message.content` | 不重试，降级 |
- **响应解析**：取 `choices[0].message.content`（OpenAI 兼容）；空内容 → `ProviderProtocolError`。
- **依赖**：仅 `urllib.request/urllib.error/json/socket` —— 守住 stdlib-only（**不引入 `requests`/`httpx`/`openai`**）。

### 3.3 其他 provider 的扩展点（不实现）

- 注册表 `PROVIDERS: dict[str, Callable[[ApiConfig], Provider]]`，`create_provider` 查表；新增 provider 只加一个函数 + 一个键。
- 若将来某 provider 的"薄 `complete`"不够（如需 system prompt、多轮、流式），扩展方式是在 `ApiConfig` 加字段、在**该 provider 内部**实现，不改变 `Provider` 协议对外形状（遵循决策 2）。
- 说明：决策 2 的 `complete(prompt)->str` **不支持流式**；长回复期间 CLI 只能"等待"，GUI 需靠线程 + 进度提示（§5.2）。

### 3.4 与决策 9（API 只服务 C 档）的现实落差

`Diagnostic.category` 是 `command/control_flow/objects/…` 的**转换机制分类**，**不是** A/B/C/D 置信档。真语料报告（`real-corpus-report.md` §3.1）里的 C 档（329 例，集中于"自定义日志函数调用 ~255 / Where-Object ~63 / 导出管道 ~10"）是**人工诊断**得出的，代码里**没有可在运行时判档的组件**。
→ 阶段 6 无法自动"只对 C 档发送"。可选做法（需拍板，§9-Q2）：
  (a) 不判档，**由用户逐条选择**要发送的 TODO（最保守，契合决策 8）；
  (b) 用 `category` 做一个**粗略白名单**（如 `objects` 多为 D、`command/control_flow/pipeline` 混合），仅作默认建议，仍由用户改；
  (c) 后续（v1.5+）再引人/机判档。
**推荐 (a)**：与"手动逐条确认"的整体设计最一致，也避免把"档位判断"这种不可靠的推断引入产品。

---

## 4. 安全与隐私设计

### 4.1 逐条发送的边界（越少越隐私，太少修不准）

| 候选 | 发送内容 | 隐私 | 修复质量 | 备注 |
|---|---|---|---|---|
| T1 | 仅 TODO 原文（`original`/标记文本） | 最高 | 低 | 控制流/管道类缺上下文会给出错误重写 |
| T2 | T1 + hint/category | 高 | 中 | hint 里有"为何 TODO"的线索 |
| T3 | T2 + 源文件 **±N 行**上下文 | 中 | 高 | C 档"函数调用族"需要看到函数定义/调用点（`real-corpus-report.md` §4） |
| T4 | T2 + 目标 bash 相邻行 | 中 | 高 | 让模型知道落入的 bash 结构（`if/then`、缩进） |
| T5 | 整个源文件 | 最低 | 最高 | 与"越少越隐私"相悖；且大文件浪费 token |

**推荐 T3+T4 的并集，默认 N=3（可配 `context_lines`，上限 10）**：即发送
`TODO 原文 + message/category/hint + 源文件前后 3 行 + 该 TODO 所在生成行及相邻 2 行（bash）`，
并**在每次提示里原样展示将发送的全部内容**（使同意是"知情同意"）。
不得发送整文件；不得发送与本次 TODO 无关的其它 TODO 文本（避免连带泄露）。

### 4.2 "每次提示"的具体交互（对齐决策 8，不记忆已同意）

- **确认方式**：复用 CLI 现有 `_confirm`（`cli.py:286-293`：写 stderr + 读 stdin，仅 `y/yes` 视为同意，**默认 N**）。
- **措辞建议**（CLI，中文，风格对齐现有 `将执行以上脚本，继续？[y/N]`）：
  ```
  bat2sh: 即将把以下内容发送到外部服务：<base_url>
  ── 将发送的内容（原文，可复核）────────────────
  <payload 原样>
  ────────────────────────────────────────────
  bat2sh: 内容将离开本机，可能被服务提供方记录。发送本条？[y/N]
  ```
- **GUI**：复用 `RunConfirmDialog`（`dialogs.py:317-345`，标题/头部/正文/确认按钮均已参数化）展示同一 payload，按钮 `发送` / `跳过`。
- **不可绕过性**：`--yes`（`cli.py:127-130`，本用于跳过 `--run` 的**执行**确认）**不得**顺带跳过隐私提示——否则与决策 8 冲突。非交互（无 TTY）时，建议**直接拒绝并要求 TTY**（照 `_run_flow` 的非交互拒绝范式 `cli.py:364-369`）。此项存在设计权衡，列入 §9-Q1。

### 4.3 API key 存储（方案对比）

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| 环境变量 `BAT2SH_API_KEY` | 不落盘、进程级隔离 | 需用户自行注入；`environ` 可能被子进程继承 | **推荐（主）** |
| `api.json` 明文 + `0600` | 开箱即用、GUI 可编辑 | 明文落盘 | **推荐（次）**，落盘后 chmod 0600 |
| 系统 keyring（Secret Service） | 加密 | 新依赖（`keyring`），违反 stdlib-only；headless/CI 不可用 | 阶段 6 不采纳，记为扩展点 |
| `--api-key` 命令行 | 临时可用 | 进 shell history / `ps` 可见 | 可提供但对齐提示"不推荐" |
**默认策略**：优先 env；未设则读 `api.json` 的 `api_key`（文件 chmod 0600，GUI 输入框用密码掩码）；两者皆无而端点又需鉴权 → `ProviderAuthError` 并提示如何配置。

### 4.4 错误信息防泄露 key

要求：
- 任何日志/异常/报告**不得包含** `Authorization` 头或 `api_key` 值；统一经 `_redact(text)` 处理后再输出（把 key 替换为 `***`）。
- 绝不把 key 拼进 URL（query 参数）——URL 可能被异常回显。
- **GUI 诊断已重定向到日志（P0 237ffde）**：`install_gui_logging`（`gui/app.py:27`）把 GUI 的 stdout/stderr 落到 `~/.local/state/bat2sh/gui.log`——因此 `_redact` 必须覆盖**所有**出口：日志、异常、报告、GUI 面板与 `RunConfirmDialog` 展示；"key 不进 gui.log" 与 "key 不进终端" 同等为硬约束。
- 测试断言：构造一次失败请求，断言 `key` 不出现在 stderr/异常串里；GUI 模式另断言不出现在 `gui.log`（隔离 `XDG_STATE_HOME` 后读取）。

### 4.5 用户拒绝提示后的行为

- 决策 6：**绝不静默丢弃**；决策 8：每次询问。
- 建议语义：
  - `n`（拒绝本条）→ **跳过本条**，保留原 TODO 原样，继续下一条；
  - `q`（退出）→ 结束本次 `--fix-todos`，**不写盘**，打印"已修复 X / 跳过 Y / 失败 Z"；
  - API 失败（§3.2 各类）→ 保留原 TODO + **打印警告**，继续下一条（隔离失败，不中断整批）。
  两种"继续/退出"都让用户可控，且都不产生"悄悄丢 TODO"。

---

## 5. CLI 与 GUI 交互流

### 5.1 CLI `--fix-todos`（方案对比 → 推荐）

| 方案 | 交互 | 优点 | 缺点 |
|---|---|---|---|
| **O1 逐条闭环** | 每条：构造→发送前提示→请求→diff→y/N→应用 | 与决策 5/7/8 完全一致；失败隔离好 | N 次 API 调用 + N 次确认，用户耐心消耗 |
| O2 批量请求→统一确认 | 先全部请求，再一次看总 diff | 确认次数少 | 仍要 N 次发送提示（决策 8）；失败后定位到条难；一次看大 diff 易误批 |
| O3 逐条请求→统一写入 | 每条看 diff，最后一次性确认写盘 | 折中 | 与决策 7"确认后写入"仍有偏差（确认与写入分离） |

**推荐 O1，且"写盘一次、在最后"**：逐条完成 `请求 + diff + 明确同意`，把已接受的替换**在内存里累积**，循环结束后**一次性写盘**（复用 `write_output` 的备份/权限逻辑 `engine.py:68-97`）。这样既满足"逐条确认"，又避免中途写盘产生半成品。

**流程（文字流程图）**：
```
bat2sh --fix-todos deploy.bat [-o deploy.sh] [--api-base ...] [--api-model ...]
  │
  ├─(1) 照常转换 → text, report                        [engine.convert_text]
  ├─(2) 若 report.errors 含 category=="syntax"（整体降级）→ 拒绝："已整体降级，无 TODO 可修复"，退出
  ├─(3) 扫描 text 的动作性 TODO 标记（M1/M2/M3/M4；排除 M5/M6）→ 列表 todos[1..N]
  │        无 → "未发现可修复 TODO"，退出 0
  ├─(4) for i in 1..N:
  │       a. 组装 payload = 原文 + hint/category + 源±context_lines + 目标 bash 相邻行   (§4.1)
  │       b. 隐私提示：展示 base_url + payload 原样 → [y/N/q]                        (§4.2)
  │            N → 跳过本条（保留原 TODO，计入 skipped），continue
  │            q → 跳出循环，进入 (5)（不写盘）
  │       c. provider.complete(prompt, timeout)                                        (§3)
  │            失败 → 保留原 TODO + 警告，计入 failed，continue（决策 6）
  │       d. 生成候选脚本：按形态替换 M1整行 / M3,M4整行 / M2整块                        (§1.5)
  │       e. 对候选整脚本跑 bash -n（复用 syntax.bash_syntax_error）→ 失败则视为"不可用建议"，
  │            保留原 TODO + 警告，continue（**硬门槛**，见 §10-R1）
  │       f. 展示 unified diff（复用 cli._emit_diff）→ [y/N] → 接受则更新内存脚本
  ├─(5) 若接受数>0 且非 q 中断 → write_output（备份/覆盖权限沿用现有设置）              [engine.write_output]
  └─(6) 汇总：修复 F / 跳过 S / 失败 E / 剩余 TODO R；含失败或剩余时退出码非 0（见下）
```
- **退出码（建议，待拍板 §9-Q4）**：`0` 全部处理（可含"无可修复"）；`1` 非交互拒绝/用户 q 取消；`2` 转换或写盘错误；`3` 仍有未修复 TODO（对齐现有 `--fail-on-todo=3`，`cli.py:119/419-420`）；`6`（新）API/配置错误（如无 key、端点不可达）。**不新增与现有码冲突的语义**。
- `--fix-todos` **隐含"先转换"**；与 `--run` 建议互斥（修复后由用户自行决定是否运行），与 `--print` 也可互斥或明确"仅打印修复后脚本"。

### 5.2 GUI 交互（对齐决策 4/7）

- **入口**：新增工具栏动作 `API 修复 TODO`（在 `_build_actions`/`_build_toolbar`，`main_window.py:196-290` 加一项），仅当 `current.report` 存在动作性 TODO 时启用（可复用/扩展 `needs_todo_confirmation`，`main_window.py:95-96`）。
- **交互**：点击 → 打开新 `TodoFixDialog`（参照 `RunConfirmDialog`/`ReportDialog` 写法）：
  列表展示待修复 TODO → 逐条"发送前隐私确认"（同 §4.2 的 payload 展示）→ 显示 diff（复用 `build_diff_html`/`DiffDialog`，`dialogs.py:229-276`）→ `应用本条/跳过` → 全部结束后把结果**写回 `output_editor`**（编辑器本就可编辑，`main_window.py:417`），**由用户再按现有"保存"落盘**（`save_current`，`main_window.py:612-629`）——完美贴合决策 7"不自动改写"。
- **线程**：现有 `convert_current`（`main_window.py:592-610`）是**同步**的；`batch_convert`（`main_window.py:635-690`）用 `QApplication.processEvents()` 硬顶。API 调用是**秒级**，**不能**沿用它。需用 `QThread`/`QObject` worker + 信号回主线程（项目已有 `QProcess+QTimer` 异步范式可参考，`main_window.py:733-863`），并显示进度（`self.progress`，`main_window.py:424-430`）。
- **设置页**：见 §2.4（并入 `SettingsDialog`）。

### 5.3 取消 / 中断语义

- **CLI Ctrl+C**：默认**不写盘**（丢弃本次会话的未落盘修改），打印已修复/跳过计数；原因：避免"半新增/半修复"的中间态文件，符合保守纪律。若人希望"已接受的也要落盘"，需显式提供选项（列 §9-Q5）。
- **GUI 关闭对话框**：取消本次修复，不改 `output_editor`；已应用的条目若已改编辑器，用户可用"保存/不保存"自行决定。
- **GUI 关闭窗口先例（P0 b4ebfcd）**：主窗口现有 `closeEvent`（`main_window.py:1009-1029`）在"脚本运行中"时弹询问（默认"否"），确认后终止进程组再退出。API 修复流程若以 `QThread` worker 运行，应复用同一语义：**API 请求进行中关闭窗口必须询问并取消请求**（默认不退出），不得静默丢弃在途请求或触发写盘——与本节的"取消 = 不写盘"一致。

---

## 6. 测试策略（无网络 + mock）

### 6.1 Provider 的可测性（推荐"可注入 transport"）

```python
class OpenAICompatibleProvider:
    def __init__(self, config: ApiConfig, transport: Transport = urllib_transport): ...
    def complete(self, prompt: str, *, timeout: float) -> str: ...
```
- 生产用 `urllib_transport`；测试传 `FakeTransport`（返回预置 JSON / 抛预置异常）。
- 好处：**不 monkeypatch 全局**、不碰 socket、可精确构造 401/429/5xx/超时/坏 JSON 各分支。
- 备选：`monkeypatch.setattr(urllib.request, "urlopen", fake)`（也可行，但全局性弱于注入）。

### 6.2 纯函数与既有测试范式复用

- **prompt 构造 / 回复清洗 / 标记扫描 / 片段替换**：全部做成 `core/api/fixer.py` 的纯函数，直接单测（参照 `test_gui_pure.py` 对 `build_diff_html` 的纯函数测法）。
- **隐私提示 / 拒绝流 / 非交互拒绝**：复用 `test_cli_run.py:27-40` 的 `_FakeTtyStdin`/`_NonTtyStdin` 注入 `sys.stdin`，`capfd` 断言 stderr 文案与退出码（现有 `test_cli_run.py` 即此范式）。
- **配置优先级**：`monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))`（`test_recent.py:75`、`test_presets.py:70` 范式）+ 直接调 `resolve_api_config(cli, env, file)` 断言三档覆盖；坏 JSON / 未知键 / 类型不符 → 回退（照 `test_presets.py` 的容错用例）。
- **降级路径**：fake transport 抛 `ProviderAuthError/TimeoutError/ProviderServerError` → 断言原 TODO 保留、打印警告、退出码符合预期（决策 6）。
- **diff/写回**：对替换后的脚本断言 `bash -n` 通过（复用 `conftest.bash_check`，`conftest.py:54-70`）。
- **GUI 逻辑**：把"列表→payload→替换"下沉到纯函数，widget 测试只在离屏 `QApplication`（`QT_QPA_PLATFORM=offscreen`，`test_gui_run.py:13`）下验证接线，尽量薄。

### 6.3 CI 不进真实 API（方案对比）

| 方案 | 做法 | 评价 |
|---|---|---|
| **G1 本地 conftest socket 守卫** | autouse fixture：`monkeypatch.setattr(socket, "socket", _boom)`，任何真实连接即失败 | **推荐**：零依赖、强制"测试不联网"、失败信息明确 |
| G2 `pytest-socket` 插件 | `--disable-socket` | 新测试依赖；功能更全但非必须 |
| G3 仅靠"注入 fake"约定 | 不设守卫 | 依赖自觉，可能漏网 |
**推荐 G1**，并注意：`pytest -q` 是现有 CI 命令（`.github/workflows/test.yml`），新增测试不得引入网络/交互；CI 三版本 3.12/3.13/3.14 全绿是硬门槛（`docs/testing-strategy.md:40-41`）。

---

## 7. 实现工作量估算（CLI / GUI 分开）

> 单位：**理想人日**（不含联调与真实 API 手动验收）。区间为粗估，认识不确定性大，供排序用。

| 模块 | 内容 | 估算 |
|---|---|---|
| 基础（共享，不进 CLI/GUI 归口） | `core/api/config.py`（加载/合并/校验/原子写/0600） | 1.0–1.5 |
| 基础 | `core/api/provider.py`（Protocol + OpenAI 兼容 + 错误分类 + 重试） | 1.5–2.0 |
| 基础 | `core/api/fixer.py`（prompt 构造、标记扫描 M1–M4、片段替换、`bash -n` 校验） | 1.5–2.5 |
| 基础 | 测试脚手架（FakeTransport、socket 守卫、fixtures） | 0.5–1.0 |
| **CLI 6b** | argparse 扩展 + `--fix-todos` 编排 + 提示流 + diff + 写盘 + 退出码 | 1.5–2.5 |
| CLI 6b | CLI 测试（提示/拒绝/降级/优先级/中断） | 1.0–1.5 |
| **GUI 6c** | 工具栏动作 + `TodoFixDialog`（列表/隐私确认/diff/应用） | 2.0–3.0 |
| GUI 6c | QThread worker + 进度/取消接线 | 1.0–1.5 |
| GUI 6c | 设置页增补（API 区块 + 掩码输入 + 写回） | 0.5–1.0 |
| GUI 6c | GUI 测试（offsscreen + 纯函数层） | 1.0–1.5 |
| **合计** | | **约 12–19 人日** |

风险加成：`fixer.py` 的标记定位（§1.5）若在真实语料上暴露歧义，可能额外 2–4 人日（或需转 §1.5 方案 B）。

---

## 8. 建议的实现阶段划分（6b / 6c 内部拆分）

**6b（CLI 主线，先打通"引擎侧"）**
1. 6b-1 配置层：`core/api/config.py` + 优先级解析 + 原子写 + 测试。
2. 6b-2 Provider 层：`core/api/provider.py` + 错误分类/重试 + FakeTransport 测试。
3. 6b-3 Fixer 层（**关键**）：标记扫描与定位（§1.5 方案 A）→ prompt → 替换 → `bash -n`；纯函数 + 单测（含 §1.3 六形态与 §1.4 四类障碍的回归）。
4. 6b-4 CLI 编排：`--fix-todos` + 隐私提示 + diff + 写盘 + 退出码 + 既有测试范式复用。
5. 6b-5 CLI 联调与真实语料手动验收（只读跑通、不 commit 产物）。

**6c（GUI，复用 6b 的 core）**
1. 6c-1 设置页 API 区块 + 写回（复用 `save_api_config`）。
2. 6c-2 `TodoFixDialog`（纯函数层先用 §6.2 测通）。
3. 6c-3 QThread worker + 进度/取消 + 工具栏动作启用逻辑。
4. 6c-4 GUI 测试与视觉 QA。

依赖：6c 全部依赖 6b 的 `config/provider/fixer`。建议 **6b 完成并过审后再开 6c**（避免接口返工）。

---

## 9. 未决问题清单（需人拍板）

- **Q1（交互 × 决策 8）**：`--fix-todos` 在**非交互/CI/`--yes`** 下如何自处？选项：(a) 一律要求 TTY、否则拒绝（最贴合决策 8）；(b) 提供独立显式开关（如 `--i-know-this-sends-data`）单次放行但**不记忆**；(c) `--yes` 兼作放行（**与决策 8 冲突，不推荐**）。
- **Q2（决策 9 落地）**：没有运行时 A/B/C/D 分档器。是否接受"不判档、纯人工逐条选"（§3.4 推荐 a）？还是用 `category` 做粗略默认勾选（b）？
- **Q3（默认值）**：默认 `base_url`/`model`/`timeout` 的取值策略（是否内置任何具体服务商默认？还是强制用户显式配置、缺失即报错）？涉及"是否把某商业服务商设为默认"的产品姿态。
- **Q4（退出码）**：新增 `6 = API/配置错误` 是否可接受？"仍有未修复 TODO"复用 `3` 是否合适？
- **Q5（中断写盘）**：CLI Ctrl+C 时"已接受但未落盘"的修改——丢弃（本文推荐）还是落盘？GUI 同理。
- **Q6（配置格式）**：接受 §2.2 的 **JSON（偏离任务提示的 TOML）**，还是坚持 TOML（需批准引入 `tomli-w` 或自写 writer）？
- **Q7（发送边界默认）**：`context_lines` 默认 3 是否合适？是否允许用户调到"整文件"（本文建议硬上限 10 行、禁止整文件）？
- **Q8（修复范围）**：M2（管道通用标记）与"有诊断无注释"两类，是否确认为"不参与 API 修复、仅人工"（本文建议是）？
- **Q9（GUI 入口位置）**：并入现有 `SettingsDialog` vs 独立对话框？（本文倾向并入。）
- **Q10（`--run` 联动）**：修复后是否允许 `--fix-todos --run` 串联？本文建议**先互斥**，保持小步。

### 9.1 决策记录（自动拍板）

> 拍板时间：2026-09-15（cold-start 自动 session，经用户授权全自动执行）。
> 拍板原则：文档有"推荐/倾向"→ 取推荐；无推荐 → 取最保守（保护用户 / 最少外流 / 最少自动化）；两难 → 取可逆。

| # | 决策 | 理由 |
|---|---|---|
| Q1 | 采纳 (a)：`--fix-todos` **一律要求 TTY**，非交互直接拒绝（退出码 1）；`--yes`/`--force` 均**不豁免**隐私提示（不提供任何放行开关） | 文档明确"(a) 最贴合决策 8"；(b)/(c) 给"无提示发送数据"留口子，与决策 8 冲突且不可逆（数据已外流） |
| Q2 | 采纳 (a)：**不判档，纯人工逐条选择**（无默认勾选、无 category 白名单） | 文档推荐；`category` 是转换机制分类而非 A/B/C/D 置信档，用它判档会引入不可靠推断（R3） |
| Q3 | **不内置任何具体服务商默认**：`base_url`/`model` 默认空串，`--fix-todos` 时缺失即报错（错误消息含配置指引）；`timeout=30.0`、`max_retries=1`、`context_lines=3` 保留数值默认 | 文档未给推荐（"需人确认"），取最保守：把商业服务商设为默认等于"未显式同意即外流"；数值默认不影响外流方向 |
| Q4 | 采纳并精确化：`0`=可修复项全部处理完毕（含"无可修复项"）；`1`=非交互拒绝或用户 `q` 取消（均不写盘）；`2`=转换/读取/写盘错误；`3`=结束时仍有未修复项（跳过 + 失败）；`6`（新）=API/配置错误（启动前配置缺失/非法）。不复用 `4`/`5`（`--run` 专属） | 文档推荐；`6` 为新码不覆盖任何现有语义（现有码 0/1/2/3/4/5） |
| Q5 | 采纳：Ctrl+C / 用户 `q` → **丢弃未落盘修改**（打印已接受/跳过/失败计数）；GUI 关闭对话框同理不改编辑器 | 文档推荐；避免半成品脚本落盘；可逆（用户可重跑） |
| Q6 | 采纳 B：`~/.config/bat2sh/api.json`（JSON，原子写 + `0600`），**偏离任务提示的 TOML**（按 §11 披露） | 文档推荐：零新依赖、与既有 3 份 JSON 惯例一致、密钥与 GUI 频繁重写的 settings 分离；TOML 写库需新依赖，违反 stdlib-only |
| Q7 | 采纳：`context_lines` 默认 3、硬上限 10、禁止整文件；不发送本次 TODO 之外的其它 TODO 文本 | 文档推荐；最少外流 |
| Q8 | 采纳：**M2（管道整块）与"有诊断无注释"不进入工作列表**，在扫描/汇总中标注"需人工"；工作列表 = M1/M3/M4（M5/M6 直接排除，M6 出现即拒绝整份修复） | 文档 §1.5 推荐 + §3.4(a)；M2 无 original 无法定位，修复即"修错行"风险（R2） |
| Q9 | 采纳：**并入现有 `SettingsDialog`**（新增"API 修复"区块），写回同一 `api.json` | 文档倾向；少一处入口；决策 3"GUI = 同一文件可视化编辑"最直接 |
| Q10 | 采纳：`--fix-todos` 与 `--run` **互斥**（同时给出即报错退出 1）；`--fix-todos` 允许 `--print`（仅打印修复后脚本） | 文档建议"先互斥，保持小步"；修复后是否运行由用户另行决定 |

**留案（不改变本次范围）**：

- R8 的改名（`--suggest-todos`）、"默认关闭"建议**未采纳为行为变更**——9 条既定决策与任务提示均以 `--fix-todos` 命名且要求 CLI + GUI 入口；但**采纳其文案要求**：CLI 汇总/GUI 面板必须声明"API 建议仍需人工复核，不保证语义正确"。
- R4（隐私疲劳）：不为省事提供"全部同意"；保持每次提示，`q` 提前退出即为缓解。
- R2 定位歧义：对齐按 (original, 唯一匹配源行) 尽力进行；歧义不影响安全（diff + 逐条确认仍在），仅降低上下文质量，不自动定位落点。

---

## 10. 风险与反对意见（含对本设计的直言）

- **R1（最高）"看起来对、实际错"——与项目第一纪律正面冲突。**
  LLM 修复 bash 的典型失败模式正是"语法合法、语义错误"。**缓解**：强制对候选脚本跑 `bash -n`（§5.1 step e，失败即弃用建议）；**绝不自动写盘**；逐条 diff + 人确认；失败保留原 TODO。即便如此，"语法通过但语义错"仍无法被 `bash -n` 拦住——这是本功能的**固有残余风险**，产品文案必须写明"API 建议仍需人工复核"，不能宣称"自动修复正确"。
- **R2（高）定位歧义**（§1.4/§1.5）。若真实语料上 M1/M3 的对齐出现多义（同一 original 多次出现、同源行多诊断），会出现"修错行"。**缓解**：优先按 (源行号, original) 对齐；歧义时**不自动定位**，改为把候选片段与 diff 一并展示、由用户确认落点，或退回方案 B。
- **R3 决策 9 的空转**：无分档器时，"只服务 C 档"无法在产品层面保证；若用户把 D 档（对象模型/.NET）也丢给 API，模型极可能编造。**缓解**：§3.4 的默认不判档 + 文案免责 + 用户在 diff 阶段的判断。
- **R4 隐私疲劳**：`--fix-todos` 在一条脚本上可能触发几十次提示（真语料 PS 中位 TODO=89，`real-corpus-report.md` §5.2）→ 用户会无脑按 y，"每次提示"形同虚设。**缓解**：payload 展示要短而清晰、默认 N；同时**不**为省事提供"全部同意"（那会直接违背决策 8）。这是"安全 × 可用性"的真实张力，需人确认取舍。
- **R5 成本/规模**：C 档"函数调用族"约 255 例（`real-corpus-report.md` §4-3），逐条调用 + 逐条确认在真实脚本上可能非常慢/贵。**缓解**：允许 `q` 提前退出、按需挑选（Q2 的选条 UI 有价值）。
- **R6 配置与密钥**：即便推荐 env 优先，若用户把明文 key 写进 `api.json`，仍存在落盘风险；`save_settings` 现为**非原子**（`settings.py:100-103`），新配置务必用原子写 + 0600（§2.4）。
- **R7 抽象薄度的代价**：决策 2 的 `complete(prompt)->str` 无法表达 system/多轮/流式；对"给模型系统指令以稳定输出代码"这类常见需求不友好，可能需要在 prompt 里自行背负全部约束。这是**决策既定**的取舍，记录在案；若实践发现必须加 system 角色，需回头修订决策 2（应显式提"修订"而非偷偷扩展）。
- **R8 与 PS 侧现实的关系**：真语料里 PS 12 文件当前**全部整体降级**（`real-corpus-report.md` §2.1），意味着 `--fix-todos` 在 PS 上多数情况**连可修复的 TODO 列表都拿不到**（§5.1 step 2 直接拒绝）。因此阶段 6 的现实收益主要在 **bat 侧 + 已通过 `bash -n` 的 PS 文件**；不要预期它"救活"PS 转换。PS 语法缺陷属另一条线（工程修复），**本设计不触碰**。
- **反对意见（坦率）**：如果目标是"提高真实可用率"，把同样的工程量投到"PS 系统性语法缺陷修复 + bat 遗留收敛（X5/X7/X8/X9）"的确定性收益，可能高于一个**无法保证正确性**的 LLM 修复功能。建议把阶段 6 定位为**实验性、默认关闭、以"建议"而非"修复"命名**（如 `--suggest-todos` / 按钮"API 建议"），并保留在 v1.4 中可能降级为 preview 的空间（对齐 `docs/testing-strategy.md` 的"降级为 preview 版本"处置）。

---

## 11. 对 9 条既定决策的符合性核对

| # | 决策 | 本设计是否遵守 | 说明 |
|---|---|---|---|
| 1 | 多 provider 抽象，先 OpenAI 兼容 | ✅ | `Provider` 协议 + `PROVIDERS` 注册表（§3.3） |
| 2 | 抽象要薄：仅 `complete(prompt)->str` | ✅ | §3.1；代价记 R7 |
| 3 | 优先级 CLI > env > 文件；GUI = 文件可视化编辑 | ✅ | `resolve_api_config`（§2.3）+ 设置页（§2.4） |
| 4 | 触发：CLI `--fix-todos` + GUI 按钮 | ✅ | §5.1 / §5.2 |
| 5 | 粒度：逐条 TODO 发送 | ✅ | 方案 O1（§5.1）；但"逐条定位"需 §1.5 方案 A |
| 6 | 失败降级：保留原 TODO + 警告，绝不静默丢弃 | ✅ | §4.5 / §5.1 step c |
| 7 | diff 展示，用户确认后写入，不自动改写 | ✅ | §5.1 step f / §5.2（GUI 仅改编辑器，保存另行） |
| 8 | 隐私提示每次（不记忆） | ⚠️ | §4.2 遵守，但非交互场景需 Q1 拍板（潜在冲突） |
| 9 | API 只服务 C 层，不求完美转换 | ⚠️ | 无运行时 C 档判据（§3.4）；需要 Q2 拍板落地方式 |

**结论：9 条之间无相互冲突。** 上表 ⚠️ 两处是"决策 vs 代码现实"的落差，已明确标记并列为未决问题，**未擅自调和**。

**与任务提示的偏离（非决策）**：任务提示的"配置用 TOML"被本文改为推荐"JSON"（§2.2），理由为不引入依赖、与既有 3 份 JSON 一致；如需坚持 TOML，请按 Q6 显式批准。

---

## 12. 只读声明

- 本诊断**未修改任何代码**、**未新增/删除任何测试**、**未 commit / 未建 PR / 未提 issue**。
- 唯一产物是本文件 `docs/api-fix-design.md`（未 commit，等待审阅）。
- 探针脚本经 `PYTHONPATH=python` 运行，仅向 stdout 打印，**未写任何文件**（除本设计稿）。
- 未触碰 `PKGBUILD` / `.SRCINFO` / 版本号 / `src/` 快照 / 其他 v1.4 线路（语料库收编、bat 遗留收敛）。
- `pytest --collect-only` 仅收集、未改动 pytest 缓存（`pyproject.toml` 已设 `-p no:cacheprovider`）。

（设计稿完）

---

## 附录 A：二次核验记录（cold-start 复核 session 追加，2026-09-15）

> **背景披露**：本设计稿主文档由**前一 session** 于同日 00:31 落盘（未 commit）。本次 cold-start
> session **未重写正文**，而是对全文做了独立源码核对与探针复现。复核过程只读仓库（探针经
> `PYTHONPATH=python` 仅向 stdout 打印），未修改任何代码、未 commit。

### A.1 行号与声明核对（逐一命中，零事实错误）

- `types.py`：`Diagnostic` 50-62、`ConvertReport` 65-89、`to_dict/to_json` 100-118、`to_text`
  120-144、`report_blocks` 163-191、分类标签 9-21 —— 与 §1.2 一致。
- `batch.py`：`_todo` 619-627、`_error` 629-641（634 约定在位）、`_todo_block_line`/`_error_block_line`
  651-655、`_pipeline_todo` 657-664、内联条件 1554-1560 / 1573-1574 —— 与 §1.1 一致；调用点清单
  （§1.1 标注"节选"）抽查 1480、2145、2151、2283、2769 均为真实 TODO 发射位置。
- `powershell.py`：`_todo` 140-147、`_emit_last_exit_code_warn` 519-544（行内 533）、降级触发
  118-122、M5 头 228 —— 一致。
- `syntax.py`：`record_syntax_error` 58-60（line=0）、`degraded_script` 63-76（71 降级头）—— 一致。
- 配置/GUI/CLI（§2.1/§4.2/§5.1/§5.2）：`settings.py` 66-68 / 77-78 / 88-91 / 147-155、
  `recent.py` 13-15 / 58-64、`load_settings` 仅 `app.py:47`、`_confirm` 283-290、非交互拒绝
  361-366、退出码 3（416-417）、`engine.write_output` 68-97、`build_diff_html` 220、
  `SettingsDialog` 38-217、`RunConfirmDialog` 308-336、`_TODO_RE` 107、GUI 保存点 856/871/916
  —— 全部命中。
- 基线与环境：`pytest --collect-only` = **689 tests collected**（复核重跑确认）；Python 3.14.7
  （`tomllib` 可用）；CI 三版本 3.12/3.13/3.14 + `pytest -q`；`-p no:cacheprovider`
  （`pyproject.toml:34`）—— 属实。
- 语料数字（`real-corpus-report.md`）：C 档 329、日志函数 ~255、Where-Object ~63、导出管道 ~10、
  PS TODO 中位 89、12 个 ps1 全部降级 —— 属实。
- "代码里没有 A/B/C/D 运行时判档器"（§3.4）：全仓 grep `confidence`/`置信`/`档位` 零命中 —— 属实。

### A.2 探针复现（全部复现 §1.4 结论）

| 探针输入 | 复核结果 |
|---|---|
| ps1：`$LASTEXITCODE` 条件 + `.NET` 读取 | todos=3（同一源行 objects+misc 2 条）；动作性注释仅 2 处（M3 行内 + M1）；含 `TODO` 行（计入 M5）=3 —— 复现"多诊断→一注释" |
| bat：`if /i "a*b"=="c"` + `wmic` | todos=2；行首 `^#\s*TODO` 匹配仅 M5 一处；M4 条件注释带缩进不被命中；wmic 在输出中无任何对应注释 —— 复现"有诊断→无注释""注释非行首" |
| bat：三级管道 | todos=1；含 `TODO` 行=2（out-line 3=M5 假阳性、out-line 6=M1 真 TODO）—— 复现 M5 污染 grep 计数 |
| bat：双段失败管道 | 同一源行 command+pipeline 2 条诊断、输出仅 1 条 M1 —— 复现同行合并 |

补充发现（不改变结论，供 6b 参考）：除 `_todo()`/`_error()` 外，`batch.py:1480`、`2283` 存在
**硬编码** `# TODO` 注释发射点（绕过 `_todo()`，无 `report.todos` 条目、仅 warnings 层有记录）——
属 §1.4"有注释→无诊断"类的更多实例；§1.5 方案 A 的输出扫描天然覆盖它们，但报告层无法提供元数据。

### A.3 复核结论

- **未发现事实错误**。唯一修改：文件头"工作区干净"精确化为"除本设计稿外无工作区改动"（因本稿
  自身即为工作区中唯一未跟踪文件）。
- 主文档十项交付格式齐全；§9 未决问题（Q1–Q10）与 §11 决策符合性核对（2 处 ⚠️ 决策-现实落差）
  经复核成立；未擅自调和。
- 本附录不改变正文任何设计建议。文档仍**未 commit**、未建 PR，等待人工审阅。

（附录 A 完）

---

## 附录 B：P0 后行号刷新与复核（HEAD = 8529755，2026-09-15）

> **背景**：本设计稿原始诊断与附录 A 的核验基线为 `386ccb3`。其后 main 分支落了 4 个 P0 commit
> （`f47ef7c` / `237ffde` / `b4ebfcd` / `8529755`，均已 push）。本次把**正文全部行号引用**刷新到
> `8529755`，并补入 3 处 P0 增量（§2.1 / §4.4 / §5.3）；设计结论未变（见 B.3）。
> 附录 A 保留为 386ccb3 基线的历史快照，其内联行号未随本轮改写（新旧对照见 B.1）。

### B.1 行号漂移表（386ccb3 → 8529755）

| 引用目标 | 386ccb3（原稿 / 附录 A） | 8529755（本稿） | 漂移 |
|---|---|---|---|
| `cli.py` `--fail-on-todo` | 116 | 119 | +3 |
| `cli.py` `--yes` | 124-127 | 127-130 | +3 |
| `cli.py` `settings_from_args` | 141-156 | 144-159 | +3 |
| `cli.py` `_confirm` | 283-290 | 286-293 | +3 |
| `cli.py` 非交互拒绝 | 361-366 | 364-369 | +3 |
| `cli.py` 退出码 3 | 416-417 | 419-420 | +3 |
| `gui/app.py` `load_settings` 唯一调用点 | 47 | 83 | +36 |
| `main_window.py` `needs_todo_confirmation` | 90-91 | 95-96 | +5 |
| `main_window.py` recent 加载 | 142 | 147 | +5 |
| `main_window.py` actions/toolbar | 188-282 | 196-290 | +8 |
| `main_window.py` `output_editor` | 389 | 417 | +28 |
| `main_window.py` progress | 396-402 | 424-430 | +28 |
| `main_window.py` `convert_current` | 564-582 | 592-610 | +28 |
| `main_window.py` `save_current` | 584-601 | 612-629 | +28 |
| `main_window.py` `batch_convert` | 607-660 | 635-690 | +28 |
| `main_window.py` 运行异步范式（QProcess+QTimer） | 705-733 | 733-863 | +28 |
| `main_window.py` `open_settings` | 851-862 | 948-959 | +97 |
| `main_window.py` `save_settings` 调用点 | 856/871/916 | 953/968/1028 | +97 |
| `main_window.py` `closeEvent` | （原稿未引用） | 1009-1029 | B 新增引用 |
| `dialogs.py` `SettingsDialog` | 38-217 | 39-226 | 首 +1 / 尾 +9 |
| `dialogs.py` `load_presets` 调用 | 163 | 171 | +8 |
| `dialogs.py` `build_diff_html` / `DiffDialog` | 220-267 | 229-276 | +9 |
| `dialogs.py` `RunConfirmDialog` | 308-336 | 317-345 | +9 |
| `settings.py` `normalized` | 49-63 | 52-75 | 首 +3 / 尾 +12 |
| `settings.py` `config_path` | 66-68 | 78-80 | +12 |
| `settings.py` 过滤未知键 | 77-78 | 89-90 | +12 |
| `settings.py` `save_settings` 写入 | 88-91 | 100-103 | +12 |
| `settings.py` `preset_from_dict` | 104-121 | 116-140 | 首 +12 / 尾 +19 |
| `settings.py` `parse_presets_json` | 124-136 | 143-155 | +19 |
| `settings.py` `_write_presets` | 147-155 | 166-174 | +19 |
| `batch.py` 调用点尾部 | 2769-2775 / 2868 / 2917-2996 | 2770-2776 / 2869 / 2918-2997 | +1 |
| `test_presets.py` setenv 范式 | 60 | 70 | +10 |
| `test_gui_run.py` offscreen 平台 | 11 | 13 | +2 |
| `test_recent.py` setenv 范式 | 74 | 75 | 0（原值指向相邻 def 行，本稿取精确 setenv 行） |

**未变（0 漂移）**：`batch.py` ≤2372 的全部引用（619-664 / 1554-1574 / 6 / 634）、`types.py`、`syntax.py`、
`powershell.py`、`recent.py`、`engine.py:68-97`、`highlighter.py:107`、`test_cli_run.py:27-40`、
`conftest.py:54-70`、`README.md:5`、`__init__.py:3`。

### B.2 探针重跑（@8529755，与 @386ccb3 逐项一致）

| 探针输入 | @386ccb3（附录 A.2 记录） | @8529755（本次重跑） | 差异 |
|---|---|---|---|
| ps1：`$LASTEXITCODE` 条件 + `.NET` 读取 | todos=3（同行 objects+misc）；动作性注释 2 处；含 M5 行=3 | 同左（out-line 3=M5、5=M3、9=M1） | 无 |
| bat：`if /i "a*b"=="c"` + `wmic` | todos=2；行首 `^#\s*TODO` 仅 M5；M4 缩进不命中；wmic 无注释 | 同左（out-line 3=M5、7=M4 缩进） | 无 |
| bat：三级管道 | todos=1；含 `TODO` 行=2（3=M5 假阳性、6=M1 真 TODO） | 同左 | 无 |
| bat：双段失败管道 | 同一源行 2 条诊断（command+pipeline）、输出仅 1 条 M1 | 同左 | 无 |

### B.3 P0 增量与"结论不变"声明

- `f47ef7c`（CLI 颜色 TERM 容错）与 `8529755`（cls→clear TERM 容错）：不触及 6a 的 TODO 机制 / 配置 /
  Provider 设计，无交叉。
- `237ffde`（GUI 诊断重定向到 `gui.log`）→ 已补入 **§4.4**："密钥不得入 gui.log" 为硬约束。
- `b4ebfcd`（GUI 运行停止/输入/超时 + 关闭窗口询问）→ 已补入 **§2.1**（`run_timeout` 数值字段先例）
  与 **§5.3**（`closeEvent` 询问先例）。
- **§0 五条结论、§9 Q1–Q10、§11 符合性表均未变**；两处 ⚠️（决策 8 非交互、决策 9 无分档器）仍在，
  仍待人拍板。

### B.4 刷新方式与只读声明

- 刷新范围仅本文件 `docs/api-fix-design.md`；行号经逐目核对，并以刷新前备份做了全文 diff 审计。
- 未改任何代码、未新增/删除测试、未 commit / 未 push（`origin/main` 保持 `8529755`）。

（附录 B 完，全文完）
