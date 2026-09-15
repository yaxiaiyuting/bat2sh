# bat2sh — Windows 脚本转 Bash 转换器

将 Windows 批处理（`.bat`/`.cmd`）与 PowerShell（`.ps1`）脚本转换为 Linux Bash 脚本的
桌面工具 + 命令行工具。界面使用 **Python 3 + PySide6（Qt6）**，贴合 KDE Breeze 风格，
在 Wayland（KWin）下原生运行；核心转换引擎只依赖 Python 标准库。

> 转换是"尽力而为"的静态翻译：能自动转换的语句会直接翻译，无法等价转换的语句会
> 插入 `# TODO: 手动检查: <原命令>` 注释并在预览中红色高亮。报告分
> **错误（红）/ 警告（黄）/ 无法自动转换（TODO，灰）** 三层；错误表示生成脚本可能
> 无法正确执行，务必优先处理。**生成脚本务必人工复核。**

---

## 1. 功能特性

- 三栏主界面：文件列表（支持拖拽）｜源文件预览（语法高亮、只读）｜转换结果（语法高亮、可编辑）
- 自动识别 `.bat`/`.cmd`（批处理）与 `.ps1`（PowerShell）
- 顶部工具栏：打开文件、打开文件夹、转换、保存、批量转换、预览差异、转换报告、主题、设置、关于
- 底部状态栏：转换进度、错误数、警告数、TODO 数、已转换行数
- 深色/浅色主题切换，默认跟随系统（KDE 下可用系统配色）
- 编码自动检测：UTF-8 BOM → UTF-8 → GBK → GB18030 → Latin-1，可手动覆盖
- 输出统一 UTF-8（无 BOM）、LF 行尾，可自动 `chmod +x`
- 转换报告：已转换行数、保持不变行数、错误、警告、无法自动转换（TODO）清单（错误红/警告黄高亮）
- 差异预览：`difflib` 生成源文件与转换结果的对照表
- 命令行模式：`bat2sh --cli input.bat -o output.sh`，适合脚本/CI 调用
- API 修复 TODO（实验性）：CLI `--fix-todos` / GUI 工具栏，为无法自动转换的语句获取修复建议（逐条确认、diff 后应用，绝不自动写盘）
- 规则集中定义在 `core/rules.py`，扩展翻译规则只需改表或加 `cmd_*` 方法

## 2. 项目结构

```text
bat2sh/
├── PKGBUILD                     # Arch/CachyOS 打包脚本 (makepkg -si)
├── install.sh                   # 免打包安装脚本（默认 ~/.local）
├── bat2sh.desktop               # 桌面项
├── pyproject.toml               # pip/setuptools 打包配置
├── LICENSE
├── README.md
├── .github/
│   └── workflows/test.yml       # CI：多版本 Python 运行 pytest
├── scripts/
│   ├── bat2sh-launcher          # 安装版启动器（供 PKGBUILD 使用）
│   └── bat2sh-dev               # 源码目录直接运行
├── examples/
│   ├── hello.bat  / hello.sh
│   ├── deploy.bat / deploy.sh
│   ├── backup.ps1 / backup.sh
│   └── cleanup.ps1/ cleanup.sh
├── tests/                       # pytest 回归测试
│   ├── conftest.py
│   ├── test_batch.py
│   ├── test_powershell.py
│   ├── test_encoding.py
│   ├── test_cli.py
│   └── test_examples.py
└── python/bat2sh/
    ├── __init__.py              # 版本与应用元信息
    ├── __main__.py              # 统一入口：GUI / --cli
    ├── cli.py                   # 命令行模式
    ├── data/bat2sh.svg          # 应用图标
    ├── core/                    # 转换引擎（不依赖 PySide6）
    │   ├── types.py             # SourceKind / ConvertReport / Diagnostic
    │   ├── encoding.py          # 编码检测与读写
    │   ├── settings.py          # 转换设置 + JSON 持久化
    │   ├── utils.py             # 引号/重定向切分/路径转换等工具
    │   ├── rules.py             # ★ 全部转换规则表（字典，便于扩展）
    │   ├── batch.py             # 批处理转换器
    │   ├── powershell.py        # PowerShell 转换器
    │   └── engine.py            # 文件识别、写出、备份、chmod
    └── gui/                     # 图形界面（PySide6）
        ├── app.py               # QApplication 入口
        ├── main_window.py       # 主窗口与业务编排
        ├── editor.py            # 带行号的代码编辑器
        ├── highlighter.py       # bat/ps1/bash 语法高亮 + TODO 高亮
        ├── dialogs.py           # 设置/差异/报告/关于对话框
        └── theme.py             # 深色/浅色/跟随系统
```

## 3. 安装

### 3.1 Arch / CachyOS：PKGBUILD

```bash
# 在项目根目录
makepkg -si
```

依赖解析：`python`、`python-pyside6`（AUR 之外的官方仓库均有）。
PKGBUILD 使用 GitHub Release 的 tag tarball 作为 `source`，并固定 `sha256sums`；
发布新版本时需要同步更新 `pkgver` 与校验和（`updpkgsums`）。

### 3.2 免打包安装（推荐个人使用）

```bash
./install.sh                # 安装到 ~/.local
sudo PREFIX=/usr/local ./install.sh   # 系统级安装
```

### 3.3 pip / 源码运行

```bash
pip install .               # 通过 pyproject.toml 安装（含 PySide6 依赖）
# 或直接源码运行（无需安装）：
./scripts/bat2sh-dev                # GUI
./scripts/bat2sh-dev --cli a.bat    # CLI
```

### 3.4 KDE/Wayland 说明

- 应用设置 `desktopFileName`，Wayland 下窗口图标/任务栏分组正常。
- 使用原生 `QFileDialog`（xdg-desktop-portal），不做任何 X11 特有调用。
- 若未自动套用 Breeze 风格，请安装 `breeze` 并确保
  `QT_QPA_PLATFORMTHEME=kde`（多数 CachyOS/KDE 默认已是）。
- 生成的脚本 shebang 固定为 `#!/usr/bin/env bash`，与用户默认的 fish 无关。

### 3.5 文件关联（双击 .bat/.cmd/.ps1 打开 bat2sh）

PKGBUILD/AUR 安装时会注册 bat2sh 专用 MIME 类型并刷新数据库。
`bat2sh.desktop` 同时声明可打开系统的 `application/x-bat` 与
`application/x-powershell`，因此双击 / "打开方式" 中都能选择 bat2sh：

- `application/x-bat2sh-batch` → `*.bat`、`*.cmd`（继承 `application/x-bat`）
- `application/x-bat2sh-powershell` → `*.ps1`（继承 `application/x-powershell`）

双击行为：打开 GUI 并载入文件、自动转换到预览态，**不会自动保存或执行**。

安装 bat2sh **不会**抢占系统默认程序：`.bat/.cmd` 若已关联 Wine，双击仍由
Wine 打开。要让双击默认用 bat2sh，手动将其设为默认（任选其一）：

```bash
# 命令行（用户级）：
xdg-mime default bat2sh.desktop application/x-bat
xdg-mime default bat2sh.desktop application/x-powershell
xdg-mime default bat2sh.desktop application/x-bat2sh-batch
xdg-mime default bat2sh.desktop application/x-bat2sh-powershell

# 如需恢复 Wine 处理 .bat/.cmd：
xdg-mime default wine.desktop application/x-bat
```

KDE Plasma：系统设置 → 应用程序 → 文件关联，搜索 `bat` / `ps1`，将 bat2sh
移到首位；或在 Dolphin 中右键文件 → 打开方式 → 其他应用，选择 bat2sh 并
勾选"记住此应用"。

不使用 PKGBUILD 时（如 `install.sh` 用户级安装），可手动注册：

```bash
install -Dm644 data/mime/bat2sh.xml ~/.local/share/mime/packages/bat2sh.xml
update-mime-database ~/.local/share/mime
install -Dm644 bat2sh.desktop ~/.local/share/applications/bat2sh.desktop
update-desktop-database ~/.local/share/applications
```

## 4. 使用

### 4.1 图形界面

```bash
bat2sh            # 启动 GUI
bat2sh a.bat b.ps1  # 启动并载入文件
```

工作流：打开/拖入文件 → 自动转换并在右侧预览 → 按需编辑 → 保存（自动 `chmod +x`）。
"批量转换"会按设置逐个转换、写出，并弹出汇总报告。
"转换并运行"会在窗口底部内嵌面板中执行脚本、实时显示输出（30 秒超时，可折叠）。
双击打开与默认程序设置见 3.5 节"文件关联"。

快捷键：

| 快捷键 | 功能 |
| --- | --- |
| `Ctrl+O` | 打开文件 |
| `Ctrl+Shift+O` | 打开文件夹 |
| `Ctrl+Enter` | 转换当前文件 |
| `Ctrl+S` | 保存当前结果 |
| `Ctrl+Shift+R` | 批量转换 |
| `Ctrl+Shift+Enter` | 转换并运行（内嵌输出） |
| `Ctrl+D` | 预览差异 |
| `Ctrl+R` | 转换报告 |
| `Ctrl+T` | 切换主题（跟随系统/浅色/深色） |
| `Ctrl+,` | 设置 |
| `Ctrl+Q` | 退出 |

### 4.2 命令行

```bash
bat2sh --cli input.bat -o output.sh        # 单文件
bat2sh --cli a.bat b.ps1 --outdir build/   # 多文件到指定目录
bat2sh --cli a.bat --print                 # 只打印到 stdout，不写文件
bat2sh --cli a.bat --diff                  # 打印源文件与结果的 unified diff
bat2sh --cli a.bat --dry-run               # 只显示将写出的文件，不落盘
bat2sh --cli a.bat --report --fail-on-todo # CI: 有错误/TODO 时退出码 3
bat2sh --cli a.bat --report-json           # 转换报告以 JSON 输出到 stdout（--print 时走 stderr）
bat2sh --cli a.bat --run --yes             # 转换后执行（含错误/TODO 时拒绝，退出码 4）
bat2sh --cli a.bat --run --force           # 强制执行（跳过 TODO 防护与确认）
bat2sh --cli a.bat --fix-todos             # 交互式：调用 API 为 TODO 获取修复建议（见 4.5）
```

| 参数 | 说明 |
| --- | --- |
| `-o, --output` | 输出文件（仅单文件） |
| `--outdir` | 输出目录（默认与源文件同目录） |
| `--suffix` | 输出后缀（默认 `.sh`） |
| `--indent {2,4,tab}` | 缩进风格（默认 4 空格） |
| `--no-exec` | 不添加可执行权限 |
| `--backup` / `--backup-source` | 覆盖输出前备份 / 转换前备份源文件 |
| `--no-quote-vars` | 变量不强制加双引号 |
| `--no-strict` | 不添加 `set -euo pipefail` |
| `--last-exit-code {warn,map}` | PowerShell `$LASTEXITCODE` 策略（默认 `warn`；`map` 近似映射为 `$?`） |
| `--encoding` | 强制输入编码（默认自动检测） |
| `--no-overwrite` | 输出已存在时拒绝覆盖 |
| `--print` | 输出到 stdout |
| `--diff` | 打印源文件与转换结果的 unified diff（`--print` 时走 stderr） |
| `--dry-run` | 只显示将写出的文件，不实际写盘、不改权限 |
| `--report` | 打印转换报告（纯文本，stderr） |
| `--report-json` | 以 JSON 格式打印转换报告（普通模式 stdout，`--print` 时 stderr；与 `--report` 互斥） |
| `--fail-on-todo` | 存在 TODO 或错误时返回 3 |
| `--run` | 转换后立即执行（不写文件；含错误/TODO 时拒绝，退出码 4；仅单文件） |
| `--force` | 跳过 TODO 防护与执行确认（谨慎使用） |
| `--yes` | 跳过执行确认（非交互环境必需；仍受 TODO 防护） |
| `--run-timeout N` | 执行超时秒数（默认 30；超时退出码 5） |
| `--run-cwd DIR` | 执行工作目录（默认脚本所在目录） |
| `--fix-todos` | 调用 API 为 TODO 生成修复建议（需交互终端；与 `--run` 互斥；见 4.5） |
| `--api-base` / `--api-model` | API 地址 / 模型（覆盖配置文件；通常配合 `--fix-todos`） |
| `--api-provider` | API 类型（当前仅 `openai` 兼容） |
| `--api-key` | API key（不推荐：会进入 shell 历史；建议用 `BAT2SH_API_KEY`） |
| `--api-timeout N` | API 空闲超时秒数（默认 30；流式响应中两次数据到达的最大间隔） |
| `--api-context-lines N` | 发送的源文件上下文行数（默认 3，上限 10） |
| `-q, --quiet` | 静默 |

退出码：`0` 成功；`2` 读取/写入/转换错误；`3` 使用 `--fail-on-todo` 且存在错误或 TODO；
`4` 使用 `--run` 且存在错误或 TODO（未加 `--force`）；`5` 执行超时或无法启动 bash；
`6` 使用 `--fix-todos` 但 API 配置缺失/非法。
`--diff` 与 `--report-json` 在普通文件模式下输出到 stdout（便于管道解析）、`--print` 模式下走 stderr；`--report` 纯文本报告与状态行（`[已写出]`/`[dry-run]`）始终走 stderr。
支持颜色的终端下，状态行与 `--report` 按 错误红 / 警告黄 / 成功绿 着色（TODO 灰）；
`NO_COLOR=1` 关闭着色，`FORCE_COLOR=1` 可在管道中强制开启。
`--print` 与 `--dry-run` 同时给出时，`--print` 优先，`--dry-run` 被忽略。

### 4.3 设置项

输出目录、输出后缀、自动 `chmod +x`、覆盖前备份、转换前备份源文件、允许覆盖、
缩进风格（2/4 空格、Tab）、变量加双引号、严格模式（`set -euo pipefail`）、
`$LASTEXITCODE` 策略（warn/map）、主题。
设置保存在 `${XDG_CONFIG_HOME:-~/.config}/bat2sh/settings.json`。

### 4.4 自动执行（--run / "转换并运行"）与安全说明

CLI 使用 `--run` 在转换后立即执行脚本（不写出 `.sh` 文件；仅支持单个输入文件）：

```bash
bat2sh --cli deploy.bat --run                   # TTY 下提示确认后执行
bat2sh --cli deploy.bat --run --yes             # 非交互执行（仍拒绝 TODO）
bat2sh --cli deploy.bat --run --yes --run-timeout 120   # 放宽超时（默认 30 秒）
bat2sh --cli deploy.bat --run --yes --run-cwd /srv      # 指定工作目录（默认脚本目录）
```

执行机制与安全边界：

- 脚本写入临时文件后以 `bash <临时文件>` 执行，stdout/stderr 透传，执行后立即清理。
- **TODO 防护**：转换结果含 `# TODO`（无法自动转换的语句）时默认拒绝执行，
  退出码 `4`，并在 stderr 列出具体位置；只有 `--force` 能跳过。
- **确认机制**：交互终端提示 `将执行以上脚本，继续？[y/N]`，回答非 y 退出码 `1`；
  非交互环境（管道、CI）必须显式加 `--yes`（或 `--force`），否则拒绝执行。
- **退出码**：脚本自身退出码原样透传（脚本 `exit 7` → CLI 返回 `7`）；
  超时（默认 30 秒）或无法启动 bash → `5`；被信号终止 → `5`。

GUI 中"转换并运行"（`Ctrl+Shift+Enter`）流程相同：结果框有未保存修改时先按源文件
重新转换（未保存的修改不参与执行）→ 含 TODO 时弹窗列出并可取消 → 展示脚本全文
确认 → 在底部"运行输出"面板流式显示 stdout/stderr，30 秒超时自动终止，
状态栏显示退出码，面板可折叠。

安全提示：

- 转换是**近似**翻译，复杂脚本请先人工核对；首次建议用 `--print` 或 `--dry-run`
  检查输出，再考虑 `--run`。
- 不要对来源不可信的 `.bat/.cmd/.ps1` 使用 `--force`：TODO 防护是最后一道闸门，
  跳过它意味着未转换的语句将以近似或缺失的形式执行。
- 执行权限与当前用户相同，工作目录默认是脚本所在目录。

### 4.5 API 修复 TODO（`--fix-todos` / GUI"API 修复 TODO"）

为生成脚本中的 `# TODO`（无法自动转换的语句）调用 OpenAI 兼容 API 获取修复建议。
**实验性功能，默认不触发；建议仍需人工复核，不保证语义正确。**

```bash
export BAT2SH_API_KEY=...                  # 推荐：key 走环境变量（不落盘）
bat2sh --cli deploy.bat --fix-todos        # 在交互终端逐条确认
```

模型输出实时流式显示在 stderr（仅正文；思维链只以"思维链 N 段"状态行提示，不显示内容），
stdout 始终保留给脚本本身（`--print`）。

配置（优先级 **CLI > 环境变量 > 文件**）：

- 文件：`${XDG_CONFIG_HOME:-~/.config}/bat2sh/api.json`（原子写 + `0600`；GUI 设置页可视化编辑同一文件）
- 环境变量：`BAT2SH_API_BASE`、`BAT2SH_API_MODEL`、`BAT2SH_API_KEY`、`BAT2SH_API_PROVIDER`、`BAT2SH_API_TIMEOUT`
- 不内置任何服务商默认：`base_url`/`model` 缺失即报错（退出码 `6`），并给出配置指引
- 兼容 OpenAI / Ollama(`/v1`) / vLLM / LM Studio 等 OpenAI 兼容端点；仅标准库实现
- GUI 设置页提供"测试连接"按钮：用当前填写的地址/模型/key 发送一次最小请求（固定 10 秒超时，
  不发送文件内容），成功显示延迟毫秒，失败显示分类（超时/认证/网络/格式/…）

隐私与安全边界：

- **每次发送前**在终端原样展示将离开本机的完整内容并逐条确认（默认 N）；不提供"全部同意"，
  `--yes`/`--force` **不可**绕过；需要交互终端，非 TTY 直接拒绝
- 发送边界：TODO 原文 + 报告元数据 + 源文件 ±3 行（可调，上限 10）+ 目标 bash 相邻 2 行；
  不发送整文件，上下文中的其它 TODO 文本会被省略
- 建议必须通过整脚本 `bash -n` 校验；展示 unified diff 确认后才应用；失败保留原 TODO 并警告
- 全部结束后**一次性写盘**（`--print` 时只输出）；`q`/Ctrl+C 中断则丢弃本次修改，不写盘
- 退出码：`3` 仍有未修复项（跳过 + 失败）；`6` 配置错误
- 仅覆盖整行注释（M1）与行内 TODO（M3/M4）；管道整块标记（M2）与整体降级不参与，需人工处理
- API key 不会出现在日志/异常/报告中；PowerShell 侧整体降级（`bash -n` 失败）的文件直接拒绝修复

## 5. 编码处理

- 检测顺序：UTF-8 BOM → UTF-16/32 BOM → UTF-8 → GBK → GB18030 → Latin-1 兜底。
- 纯标准库实现，不依赖 chardet；无法解码的字节以替换字符处理并在报告中警告。
- 界面上显示检测结果（"自动检测（gbk）"），可在下拉框中手动覆盖后重新转换。
- 输出固定为 UTF-8 无 BOM、LF 行尾。

## 6. 支持的转换规则

### 6.1 批处理（.bat/.cmd）

| 源语法 | 转换结果 |
| --- | --- |
| `rem x` / `:: x` / `REM.-- x` | `# x`（`rem` 后跟标点也算注释；`remfoo` 不算） |
| `%VAR%`、`%1`、`%*`、`%~dp0`、`%~nx0`、`%~f1` | `${VAR}`、`$1`、`"$@"`、`${SCRIPT_DIR}/`、`$(basename "$0")`、`$(readlink -f "$1")` |
| `set VAR=value` | `VAR="value"`（去除尾随空格，自动加引号可配置） |
| `set /p VAR=提示` | `read -rp "提示" VAR` |
| `<nul set /p=文本`（无变量名） | `printf '%s' "文本"`（无换行打印惯用法）；非 nul 形式 → TODO |
| `set /a x=1+2`、`set /a x+=1` | `x=$(( 1+2 ))`、`x=$(( x + (1) ))`，按位取反 `!`→`~` |
| `echo text` / `echo.` | `echo "text"` / `echo` |
| `pause` / `pause >nul` | `read -rp "Press Enter to continue..."` |
| `cls` | `clear` |
| `cd /d path` / `cd.` / `cd..` / `cd` | `cd "path"` / `cd "."` / `cd ".."` / `pwd` |
| `dir [/b] [/s] [path]` | `ls -la` / `ls -1`（`/s` 时 `ls -1R`）/ `ls -laR`（`/a`、`/a-d` 等属性开关忽略并告警） |
| `copy` / `move` / `xcopy` / `robocopy` | `cp` / `mv` / `cp -r` / `rsync -a`（`/MIR`→`--delete`；源/目标补尾斜杠以匹配“复制目录内容”语义；未知开关→TODO） |
| `del` / `erase` / `rmdir /s` / `md` | `rm -f`（`/s`→`rm -rf`）/ `rm -rf` / `mkdir -p` |
| `type file` | `cat file` |
| `find "s" f` / `findstr /i "s" f` | `grep -F` / `grep`（/i、/v、/n、/c 等已映射） |
| `findstr /i "IPv4 地址" f`（中文模式） | 已知中文模式整段映射（如 `"IPv4 地址"`→`"inet "`、`"物理地址"`→`"ether "`），**带差异说明告警**；未收录中文仅告警（英文输出中可能永不匹配） |
| `findstr /i "a b c" f`（引号内多词） | `grep -i -e "a" -e "b" -e "c"`（findstr 以空格分隔多个搜索串，OR 语义；逐词做中文映射） |
| `findstr /c:"p1" /c:"p2" f`（多 `/c:`） | `grep -F -e "p1" -e "p2"`（全部保留）；`/r` 时为 `grep -E -e …`；`/c:` 与裸词混合按文档语义共存（字面项转义） |
| `start "" "file"` | `xdg-open "file" &`；可执行目标 → `nohup ... &` |
| `if exist X (...) else (...)` | `if [ -e "X" ]; then ... else ... fi` |
| `if "%A%"=="B" (...)`（equ/neq/lss/gtr…） | `if [ "$A" = "B" ]; then ...; fi` |
| `if errorlevel N` / `if not errorlevel N` | `if [ $? -ge N ]` / `[ $? -lt N ]`（含 `$?` 时机警告） |
| `if defined VAR` | `[ -n "${VAR:-}" ]` |
| `for %%i in (*.txt) do ...`（含嵌套、多行块） | `for i in *.txt; do ...; done` |
| `for /f "tokens=*" %%i in ('cmd') do ...`（或无选项） | `while IFS= read -r i; do ...; done < <(cmd)`（选项已支持；`'CMD ^| FILTER'` 两段内管道直译；三段以上/含重定向仍 TODO） |
| `for /l %%i in (1,1,10) do ...` | `for i in $(seq 1 1 10); do ...; done` |
| `for /d %%d in (dir\*) do ...` | `for d in dir/*/; do ...; done` |
| `call :label args` / `call:label args` / `:label` | `label_<name> args` / `label_<name>() { ... }`（子程序重构为函数并前置定义） |
| `call other.bat args` | `bash "other.sh" args`（提示确认已转换） |
| `goto :eof` / `goto:eof` | 函数内 `return`；顶层 `exit 0`（`&` 串联中的 goto 同样处理） |
| `exit /b N` / `exit N` | 函数内 `return N`；顶层 `exit N` |
| `%~dp0` 路径分隔符 `\` | `/`（含 `"dir\"` 尾反斜杠、驱动器前缀告警） |
| `>nul` / `2>&1` / `> file` | `>/dev/null` / 原样 / `>file`（顺序保持） |
| `ping -n/-w/-l/-t` | `ping -c/-W/-s`（毫秒→秒），`-t` 忽略并告警 |
| `tasklist` / `taskkill /im x /pid N` | `ps aux` / `pkill -f x`、`kill N` |
| `ipconfig` / `netstat` | `ip addr` / `ss -tuln`（输出格式不同，告警） |
| `timeout /t N` | `sleep N` |
| `choice /c ... [/t N] [/m "提示"]` | `read -r -n 1 [-t N] [-p "提示"]`（后续依赖 `%ERRORLEVEL%` 时整行 TODO） |
| `certutil -hashfile f MD5\|SHA256` | `md5sum f` / `sha256sum f`（其他算法 TODO；输出格式不同，告警） |
| `driverquery` | `lsmod`（仅内核模块，语义不同，告警；有意不做 `lspci` 映射） |
| `assoc .ext` / `ftype name` | `xdg-mime query default <MIME>`（常见扩展名/类型名映射；未知 → TODO） |
| `dir x \| findstr y`（两段、无重定向/`&`） | `ls x \| grep y`（多级管道、含重定向/`&` 连接 → 整行 TODO） |
| `%SystemRoot%` | `${SystemRoot:-/}`（保留变量名，可用环境变量覆盖） |
| `call set "R=%%%A%%%"` | `R="${!A}"`（整个值为单个间接引用；复杂形式 → TODO） |
| `if /i "%A%"=="%B%"` | `[[ ${A,,} == ${B,,} ]]`（变量）；字面量转换时小写；通配符/复杂表达式 → TODO；不使用 `shopt` |
| `%ERRORLEVEL%` | warn（默认）：TODO；`--last-exit-code map`：`${__bat2sh_rc}`（首次引用处捕获 `$?`） |
| `%DATE%` / `%TIME%` | `$(date +%Y-%m-%d)` / `$(date +%H:%M:%S)`（ISO 近似并告警；`for /f` 内 → TODO） |
| `ver` / `systeminfo` | `uname -a` |
| `where x` / `mklink` / `fc` / `comp` | `command -v x` / `ln -s` / `diff` / `cmp` |
| `shift`、`pushd`、`popd`、`&` 顺序执行、`&&`、`\|\|`、管道 | 原样或等价形式 |
| `setlocal enabledelayedexpansion`、`!var!` | 忽略/尽力转换为 `${var}`（告警） |
| `title/color/chcp/mode/prompt/verify/...` | 忽略（无对应行为） |
| `python.exe` 等常见 `.exe` | 映射为 `python3` 等（表见 `rules.BATCH_EXE_MAP`） |

### 6.2 PowerShell（.ps1）

| 源语法 | 转换结果 |
| --- | --- |
| `# 注释`、`<#...#>` | `# 注释`（块注释转行注释并告警） |
| `$var`（大小写不敏感） | `${var}`，统一为首次出现的拼写 |
| `$env:VAR`、`$PSScriptRoot`、`$args`、`$null/$true/$false` | `${VAR}`、`${SCRIPT_DIR}`（自动声明）、`"$@"`、`""`/`true`/`false` |
| `Write-Host/Write-Output`（含 `-NoNewline`、`-Separator`） | `echo` / `printf '%s'`（颜色参数忽略并告警） |
| `Write-Warning/Write-Error`、`Write-Verbose/Debug` | `echo ... >&2`、注释 |
| `Read-Host "p"` / `$x = Read-Host "p"` | `read -rp "p" REPLY` / `read -rp "p" x`（`-AsSecureString`→`read -s`） |
| `Clear-Host` / `Set-Location` / `Get-Location` / `Push/Pop-Location` | `clear` / `cd` / `pwd` / `pushd` / `popd` |
| `Get-ChildItem`（`-Recurse`/`-Filter`） | 数组 `( "dir"/*.txt )`，`-Recurse`→`find` |
| `Get-Content`（`-Tail`/`-TotalCount`/`-Wait`） | `cat` / `tail -n` / `head -n` / `tail -f` |
| `Set-Content/Add-Content/Out-File`（管道或 `-Value`） | `> "file"` / `>> "file"`（`-Append`） |
| `Copy-Item/Move-Item/Remove-Item/Rename-Item` | `cp [-r]` / `mv` / `rm -rf/-r/-f` / `mv` |
| `New-Item -ItemType Directory/File/SymbolicLink` | `mkdir -p` / `touch` / `ln -s` |
| `Test-Path [-PathType Leaf/Container]` | `-e` / `-f` / `-d`（条件中）；赋值时 `$([ ... ] && echo true \|\| echo false)` |
| `Join-Path` / `Split-Path -Leaf/-Parent` / `Resolve-Path` | `"a/b"` / `$(basename ..)`、`$(dirname ..)` / `$(realpath ..)` |
| `Get-Date` / `Get-Date -Format "yyyy-MM-dd"` | `date` / `date +%Y-%m-%d`（格式近似转换） |
| `Start-Sleep -Seconds/-Milliseconds` | `sleep N` |
| `Get-Process` / `Stop-Process -Name/-Id` / `Start-Process` | `ps aux` / `pkill -f`、`kill N` / `xdg-open ... &` |
| `Invoke-WebRequest -Uri U -OutFile F` | `curl -L [-o F] U` |
| `Expand-Archive` / `Compress-Archive` | `unzip` / `zip -r` |
| `Get/Start/Stop/Restart-Service` | `systemctl status/start/stop/restart` |
| `@"..."@` / `@'...'@` here-string | `cat <<EOF`（插值）/ `cat <<'EOF'`（字面量）；赋值形式 `x=$(cat <<EOF ... )`（见 §8.2） |
| `try { cmd } catch { ... }`（无类型、try 体单命令） | `if ! cmd; then ...; fi`（近似；多命令/类型 catch/finally 保留结构 + TODO） |
| `if ($x -eq "y") {...} elseif ... else ...` | `if [[ "${x:-}" = "y" ]]; then ... elif ... else ... fi` |
| `-eq/-ne/-gt/-lt/-ge/-le/-like/-match/-and/-or/-not` | `=`/`!=`/`-gt`/`-lt`/`-ge`/`-le`/`==`（glob）/`=~`/`&&`/`\|\|`/`!`（`[[ ]]` 内） |
| `foreach ($i in $list) {...}`、`1..10`、`Get-ChildItem ...` | `for i in ...; do ...; done`、`$(seq 1 10)`、数组展开 |
| `for ($i=0; $i -lt N; $i++) {...}` | `for (( i=0; i<N; i++ )); do ...; done` |
| `while ($cond) {...}` / `do {...} while ($cond)` | `while [[ ... ]]; do ...; done` / `while true; do ...; if ! [[ ... ]]; then break; fi; done` |
| `function F($a, $b) {...}` / `param(...)` | `F() { local a="$1"; local b="$2"; ... }`（默认值→`${1:-默认}`） |
| `$ErrorActionPreference = "Stop"` | `set -e`（脚本头已启用严格模式） |
| `$x = $x + 1` | `x=$(( ${x:-0} + 1 ))` |
| 数组 `@(...)` / `$x += item` | `x=( ... )` / `x+=( item )` |
| `exit/return/throw/break/continue` | `exit`/`return`/`echo ... >&2; exit 1`/`break`/`continue` |
| `Where-Object { $_.Prop -eq "v" }`（简单条件） | `grep -F 'v'`（`-like`→`grep -E` 正则、`-match`→`grep -E`；近似并加行内 `# 近似:` 注释） |
| 管道 `\|` + `Select-String`/`Sort-Object`/`Measure-Object`/`Out-File`/`Tee-Object`/`Out-Null` | `grep`/`sort`/`wc`/`> file`/`tee`/`>/dev/null` |
| `*exe`、`. ./x.ps1` 点源 | 去掉 `.exe`、`source ./x.sh`（告警） |

## 7. 示例

示例文件位于 `examples/`，以下对比均由 `bat2sh` 实际生成（可直接运行查看）。

### 7.1 `hello.bat` → `hello.sh`

```bat
@echo off
rem 简单的问候脚本
set NAME=World
set GREETING=Hello
echo %GREETING%, %NAME%!
echo 当前目录: %CD%
if exist config.ini (
    echo 找到配置文件
) else (
    echo 未找到 config.ini，使用默认配置
)
pause
exit /b 0
```

```bash
#!/usr/bin/env bash
# 由 bat2sh 自动转换生成，源文件: hello.bat
# 带有 # TODO 标记的行无法自动转换，请人工检查
set -euo pipefail

# 简单的问候脚本
NAME="World"
GREETING="Hello"
echo "${GREETING}, ${NAME}!"
echo "当前目录: $(pwd)"
if [ -e "config.ini" ]; then
    echo "找到配置文件"
else
    echo "未找到 config.ini，使用默认配置"
fi
read -rp "Press Enter to continue..."
exit 0
```

### 7.2 `deploy.bat` → `deploy.sh`（子程序 + 循环 + errorlevel）

转换要点：`call :copy_files` 子程序被重构为前置函数；`for %%F in ("%SRC%\*.exe" ...)`
展开为带引号前缀的 glob；`%~nxF` → `$(basename "${f}")`。

```bash
label_copy_files() {
    for f in "${SRC}"/*.exe "${SRC}"/*.dll; do
        echo "复制 $(basename "${f}")"
        cp -f "${f}" "${DST}/"
    done
    return 0
}
...
SRC="./build/release"
DST="./deploy"
if [ ! -e "${DST}" ]; then
    mkdir -p "${DST}"
fi
label_copy_files
if [ $? -ge 1 ]; then
    exit 1
fi
label_summary
exit 0
```

### 7.3 `backup.ps1` → `backup.sh`（param + foreach + Join-Path）

```powershell
param([string]$Source = "C:\Data", [string]$Destination = "D:\Backup")
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Destination)) {
    New-Item -ItemType Directory -Path $Destination | Out-Null
}
$files = Get-ChildItem "$Source\*.txt"
foreach ($file in $files) {
    $target = Join-Path $Destination $file
    Write-Host "备份 $file -> $target"
    Copy-Item -Path $file -Destination $target -Force
    $count = $count + 1
}
```

```bash
Source="${1:-C:/Data}"
Destination="${2:-D:/Backup}"

set -e

if [[ ! (-e "${Destination:-}") ]]; then
    mkdir -p "${Destination}" > /dev/null
fi

files=("${Source}"/*.txt)
count=0
for file in "${files[@]}"; do
    target="${Destination}/${file}"
    echo "备份 ${file} -> ${target}"
    cp -f "${file}" "${target}"
    count=$(( ${count:-0} + 1 ))
done
```

### 7.4 `cleanup.ps1` → `cleanup.sh`（函数 + 参数默认值）

```bash
Remove_OldLogs() {
    local Path="${1:-/tmp/logs}"
    local Keep="${2:-5}"
    if [[ ! (-e "${Path:-}") ]]; then
        echo "目录不存在: ${Path}" >&2
        return 0
    fi
    logs=("${Path}"/*.log)
    for log in "${logs[@]}"; do
        echo "删除 ${log}"
        rm -f "${log}"
    done
}

set -e
Remove_OldLogs -Path "${TEMP}/logs" -Keep 3   # 告警：命名参数需改为位置参数
clear
echo "清理完成"
```

## 8. 无法完美转换、需要人工干预的特性

> 下列内容会生成错误、警告或 `# TODO`。报告分三层：**错误**（生成脚本可能无法执行，
> 如 `bash -n` 语法校验失败、标签位于控制块内等危险写法）、**警告**（可能语义偏差）、
> **无法自动转换（TODO）**（需人工改写）。请在保存前逐条核对转换报告。

### 8.1 批处理

1. **`goto`/标签控制流**：仅 `call :label` 子程序会被重构为函数。普通 `goto` 跳转、
   循环式 goto、跨标签 fall-through 无法等价转换 → `# TODO`。位于控制块内的标签
   （危险写法）记为**错误**（红）：bat 允许跳入块内，bash 无法表达该结构。
2. **`for /f`、`for /r`**：**支持**并转换为 `while read`：
   - 选项：`tokens=*` / `tokens=N` / `tokens=1,2` / `tokens=1-3` / `tokens=1*`、
     `delims=X`（未指定时按空白拆词，tokens 默认 1）、`skip=N`（命令侧为
     `cmd | tail -n +N+1`）、`eol=X`（近似为跳过以 X 开头的行；**Windows 在行中间
     遇到 X 会截断，该语义无法还原，转换时会告警**）、`usebackq` 双引号文件与
     裸文件名（`done < "file"`）。
   - 结构：命令输出统一用进程替换 `done < <(cmd)`（避免 `| while` 子 shell 丢变量）；
     循环体首变量为空的行自动跳过；行尾 `\r`（CRLF）自动去除。
   - 内管道：`'CMD ^| FILTER'` 两段自动直译为 `done < <(CMD | FILTER)`；过滤无匹配时
     循环体不执行、脚本继续（进程替换不向外传播失败）。三段及以上、含重定向或 `&`
     连接的管道仍整行 TODO。
   **仍不支持**：`usebackq` 反引号命令、字符串字面量 `("文本")` → 整行 `# TODO`；
   循环体内 `goto`（整行 TODO + 告警，无法保证跳出语义）、循环体引用未声明的
   `%%x`（仅告警，不生成变量）。`for /r` 递归遍历仍 TODO（提示改用 `find`）。
3. **延迟展开 `!var!`**：尽力转 `${var}`，但循环内赋值语义不同，需复核。
4. **`set /a`**：多表达式（逗号）、复杂位运算仅部分支持；`!`→`~` 为近似。
5. **`%DATE%`/`%TIME%`**：映射为 ISO 格式（`$(date +%Y-%m-%d)` / `$(date +%H:%M:%S)`），
   与 Windows 区域设置格式不同并告警；出现在 `for /f` 中时整行 `# TODO`。
   **`%ERRORLEVEL%`**：默认（warn）整行 `# TODO`；`--last-exit-code map` 时近似映射为
   `${__bat2sh_rc}`（首次引用处捕获 `$?`），只反映紧邻一条命令的退出码。
6. **`%VAR%` 的单词切分**、`^` 转义、空变量与引号嵌套：与 cmd 解析器存在细节差异。
   `for %%x in (%VAR%)` 这类变量集合会生成 `for x in "${VAR}"; do`：加引号可避免含空格
   路径被拆开（更安全），但变量内容本身含空白时行为与 cmd 的拆词不同；若需要 cmd 的
   拆词语义，请手工去掉引号（`--no-quote-vars` 也会关闭该行为）。
7. **Windows 驱动器路径**：`C:\dir` 会变成 `C:/dir`（并非有效的 Linux 路径），
   需要手工改成挂载点；驱动器前缀会产生告警。
8. **Windows 专有命令**：`reg`、`sc`、`schtasks`、`wmic`、`attrib`、`icacls`、
   `takeown`、`diskpart`、`bcdedit` 等 → TODO，并在报告中给出替代建议；
   有意不映射的完整清单与理由见 8.4。
9. **近似命令**：`taskkill`→`pkill`、`ipconfig`→`ip addr`、`netstat`→`ss`、
   `choice`→`read -r -n 1`、`shutdown`→`systemctl`、`robocopy`→`rsync -a`、
   `start`→`xdg-open`，行为/参数/输出并不完全一致；`start` 的窗口标题、
   `/wait`、`/b` 等语义有限。
10. **`cmd /c`、`runas`、`powershell -Command`**：引号嵌套复杂时需人工整理。
11. **`&` 分隔的多命令与管道混合**、`>file` 位置在命令之前等非常规写法：可能改变
    重定向顺序。
12. **`if errorlevel N`**：上一条是简单命令时，N=1 生成 `if ! cmd` / `if cmd`；
    N≥2 生成 `__bat2sh_status=0; cmd || __bat2sh_status=$?; if [ "$__bat2sh_status" -ge N ]`
    以保留精确退出码。上一条不是简单命令（前面是 `fi`/`done`/块语句）、
    `else if errorlevel` 等情况仍回退 `[ $? ... ]` 并告警（`if /i` 的字符串比较已用
    `${a,,}` 局部转换，见 8.4）；strict 模式下该回退通常是
    死代码（前一条命令失败时 `set -e` 已退出）。
13. **`goto :eof` 生成裸 `return`**（函数内）而非 `return 0`：批处理的 `goto :eof`
    不修改 errorlevel，裸 `return` 保留最后一条命令的退出码，调用方的
    `if errorlevel` 改写出的 `if ! func` 才能真正捕获失败；写成 `return 0` 会让
    函数永远报告成功。
14. **旧版 bash（<4.4）与 `set -u`**：`shopt -s nullglob` 让空 glob 产生空数组后，
    `"${arr[@]}"` 在 bash 4.4 以前会报 `unbound variable`。转换器面向 bash 5.x；
    如需兼容 RHEL7/macOS 自带旧 bash，请手工改为 `${arr[@]+"${arr[@]}"}`。
15. **`equ`/`neq` 按操作数形式分派数值/字符串比较**：两侧都是纯数字字面量时生成
    `-eq`/`-ne`；任一侧带引号、或为裸的非数字字面量（如 `abc`）时生成字符串比较
    `=`/`!=`，避免 bash 报 `integer expression expected`。**变量引用（如 `%X%`）
    无法静态判定，按 cmd 的数值语义生成 `-eq`/`-ne`**——若运行时值非数字，bash 会
    报整数错误（与 cmd 的 `Invalid number` 行为近似）；需要字符串比较时请象 cmd 一样
    显式加引号（`if "%X%" equ "%Y%"`）。`lss`/`leq`/`gtr`/`geq` 始终为数值比较
    （cmd 语义），字符串排序请手工改写。

### 8.2 PowerShell

1. **对象管道**：`Where-Object` 仅**文件/文本类管道**（`Get-ChildItem`/`Get-Item`/
   `Get-Content` 等）的简单条件（单个属性或 `$_` 的 `-eq`/`-ne`/`-like`/`-match`）
   可近似转换为 `grep`，并在生成脚本中以 `# 近似: ...` 行内注释标明；注意它按
   **整行文本**匹配，无法还原 `$_.Prop` 属性语义。**进程/对象类管道**
   （如 `Get-Process | Where-Object { $_.CPU -gt 10 }`）、`-gt`/`-lt` 数值比较、
   多条件（`-and`/`-or`）、方法调用等复杂条件，以及 `ForEach-Object`、
   `Select-Object`（除 `-First/-Last`）、`Group-Object`、`Get-Member`、
   `Format-Table/List`、`ConvertTo/From-Json` 等仍依赖对象模型 → 整行 `# TODO`
   （建议改用 `grep/awk/jq`）。
2. **`try/catch/finally`**（部分自动转换）：try 体只有单条命令且 catch 无类型时转换为
   `if ! cmd; then ...; fi`；多命令、带类型 catch 仍为"结构保留 + TODO"。
   `finally` 生成独立的 `if true; then ... fi`，与 try/catch 块并列而非嵌套。
   已知限制：
   1. 近似语义是"命令失败才进 catch"，并非 PowerShell 的 terminating error/异常捕获；
      命令成功但报错、异常来自其他语句时行为不同（每次转换都会告警）。
   2. 带类型的 catch（`catch [Type]`）类型被解析但不做过滤，一律结构保留 + TODO，
      并单独告警"catch 类型已忽略"。
   3. `finally` 在脚本因 `set -e` 提前退出或执行 `exit` 时不会执行（bash 需 `trap`
      才能等价）。
   4. "单条命令"判定保守：try 体多出任何非空、非结构行（含注释）就退化为结构保留，
      不尝试 `if !`。
   5. 裸 `try { cmd }`（无 catch/finally）按普通语句顺序执行，不产生告警。
   6. 赋值语句（如 `$x = 1`）也会被视为单条命令，生成 `if ! x=1; then ...`——
      bash 中合法且恒成功，几乎永不进入 catch。
   7. 嵌套 try 不支持：内层 try 整块注释为 TODO，避免生成非法 bash。
   8. 空分支体（try / catch / finally / else）会自动补 `:`（bash no-op），
      保证生成脚本通过 `bash -n`。
   建议配合脚本头 `set -e` 并手工整理错误处理。
3. **`switch`**：整块注释为 TODO。
4. **.NET 与对象操作**：`[System.IO.File]::ReadAllText()`、`New-Object`、`Add-Type`、
   `Add-Member`、`$obj.Property`、`$_.X`、`Get-ItemProperty` 等 → TODO。
5. **脚本块参数与高级函数**：`[Parameter()]`、`[CmdletBinding()]`、位置/命名参数的
   完整绑定语义无法对应。`param()` 中的 attribute（Mandatory/Position/Validate*/
   Alias 等）会被剥离，参数仅按位置传递并告警，类型转换与 `[switch]` 命名调用仍需人工核对。
   用户函数的命名参数调用按本文件扫描到的参数顺序改写为位置参数（告警）；
   跨文件/模块、`Invoke-Expression`、动态 `Set-Alias` 产生的函数无法静态绑定：
   未扫描到定义时生成 `# TODO`，命名风格不符合启发式（如全小写）的自定义函数
   会被当作外部命令原样保留。
6. **模块、配置文件、执行策略、远程、作业、事件日志、注册表、WMI/CIM** → TODO。
7. **字符串/布尔差异**：`-f` 格式运算符、反引号转义、空字符串与 0 的真值判断与 bash
   不同。here-string 已转换为 heredoc：`@'...'@` 使用引号定界符，`@"..."@` 使用插值
   定界符并尽力转换变量，但反斜杠/反引号转义语义不同（告警）；赋值形式生成
   `x=$(cat <<EOF ... )`，结尾换行会被命令替换去掉（告警）。`-f` 仍标 TODO。
8. **数组与哈希表**：`@{...}`、`.Keys/.Values`、对象数组属性访问无法等价；普通数组
   会转成 bash 数组（`"${arr[@]}"`）。
9. **`Read-Host -AsSecureString`**：转为 `read -s`，但返回的是纯文本而非安全字符串。
10. **`$?`/`$LASTEXITCODE`**：bash 的 `$?` 只反映紧邻上一条命令的退出码（读一次即被
    后续命令覆盖），而 PowerShell 的 `$LASTEXITCODE` 可重复读取，直接映射存在语义
    偏差。默认策略 `warn`：含 `$LASTEXITCODE` 的语句整行替换为 `# TODO`，条件行生成
    `if [[ false ]]; then  # TODO ...` 占位，不生成可能误导的引用。可选策略 `map`
    （CLI：`--last-exit-code map`；GUI：设置 →「$LASTEXITCODE 策略」）近似映射为
    bash `$?`：首次引用处插入 `__bat2sh_rc=$?` 捕获，后续引用统一读
    `${__bat2sh_rc}`；跨函数/跨作用域时自动退回 `warn` 并告警。两种策略都建议对
    关键退出码判断手工复核。
11. **`$env:NAME`**：常见变量映射为近似值（`$env:TEMP`→`${TMPDIR:-/tmp}`、
    `$env:APPDATA`→`${XDG_CONFIG_HOME:-$HOME/.config}` 等）并告警；未收录变量原样
    保留为 `${NAME}` 并告警——strict 模式（`set -u`）下变量未设置会直接报错，
    建议在脚本里显式给默认值或改名。
12. **`Join-Path`**：生成 `__bat2sh_join_path` 辅助函数，子路径为绝对路径
    （`/...` 或 `C:/...`）时重置为子路径（对齐 .NET `Path.Combine`），否则以 `/`
    拼接。bash 没有 provider 概念：不解析 `~`/盘符/UNC，不自动创建父目录；
    子路径可能是目录（变量、含 `/`、`..`、盘符）时告警；`-Resolve`、
    `-AdditionalChildPath` 等选项不转换并告警。

### 8.3 通用

- 转换不做数据流/类型分析，**不保证行为等价**；请把生成的 `.sh` 当"高级草稿"。
- `# TODO` 行与菜单"转换报告"（错误红/警告黄/TODO 灰）是人工复核清单；
  `--fail-on-todo`（存在错误或 TODO 时退出码 3）可用于 CI 卡点。
- 复杂脚本建议先分段转换、逐段验证，再合并。

### 8.4 有意不做自动映射的命令（设计决策）

命令"有对应物"≠"可以自动映射"：输出格式或抽象层不同的映射会产生**静默错误**，
比 `# TODO` 更危险。以下命令**有意不做自动映射**，保持 TODO 或原样：

| 命令 | 不映射的原因 |
| --- | --- |
| `wmic` | 输出为对象/表格文本，常被 `for /f` 按列解析；`lsblk`/`lscpu` 等只能覆盖个别用法，无稳定等价输出 |
| `sc query` | 服务列表的**输出格式**是 `for /f` 的事实接口，`systemctl` 的格式完全不同 |
| `net user` / `net start` | 同上：账户/服务列表的列布局被脚本依赖，替换即静默错位 |
| `icacls` | Windows ACL 与 Linux UGO/ACL 是**不同抽象层**，`chmod` 无法一一对应 |
| `reg query` | Linux 无注册表；用 grep 近似配置文件无法保证键值语义 |
| `goto` 跨函数 | 需要跨标签控制流分析才能重构；转换器只做局部改写，跨函数跳转一律 TODO |
| `cmdextversion` | Linux 无对应检查：保留为恒假条件 + TODO（不能当作成功分支执行） |
| 复杂管道 | 多级（>2 段）、含重定向（如 `2>nul`、`2>&1`）或 `&` 连接的管道，逐段重写会改变执行顺序与错误传播 → 整行 TODO |
| `choice` 后接 `%ERRORLEVEL%` | `read` 无法保留"选项序号"退出码语义；检测到后续依赖即整行 TODO |
| `for /f` 中的 `%DATE%`/`%TIME%`/`%ERRORLEVEL%`/多级管道（≥3 段） | 循环按该输出解析字段，格式与捕获时机无法保证 → 整行 TODO（`'CMD ^| FILTER'` 两段已支持直译） |
| `%ERRORLEVEL%`（默认 warn 策略） | `$?` 只反映紧邻一条命令；用 `--last-exit-code map` 才会近似映射为 `__bat2sh_rc` |

对应的"干净映射"（无下游格式依赖，已自动转换）：
`certutil -hashfile`（MD5/SHA256）、`driverquery`（仅 `lsmod`）、
`assoc`/`ftype` 查询（`xdg-mime query default`）、`%SystemRoot%`（`${SystemRoot:-/}`）、
`call set` 间接引用（`R="${!A}"`）、`if /i` 字符串比较（`${a,,}`，不用 `shopt`）、
`%DATE%`/`%TIME%`（ISO 格式，`for /f` 内除外）。

## 9. 扩展转换规则

所有规则集中在 `python/bat2sh/core/rules.py`：

- 简单命令（参数透传）：往 `BATCH_SIMPLE_MAP` / `PS_SIMPLE_CMDLETS` 加一行。
- 需要特判参数：在 `BATCH_HANDLER_MAP` / `PS_HANDLER_MAP` 中把命令映射到转换器的
  `cmd_*` 方法，再在 `batch.py` / `powershell.py` 中实现该方法（返回 `str` 行或
  `None` 表示生成 TODO）。
- Windows 专有命令：加入 `BATCH_TODO_COMMANDS` / `PS_TODO_CMDLETS`，可附编译提示。
- 环境变量/自动变量映射：`BATCH_ENV_MAP`、`PS_AUTOMATIC_VARS`、`PS_TODO_VARS`。

## 10. 开发与测试

```bash
# 安装测试依赖并运行完整测试套件
pip install -e .[test]
pytest

# 冒烟测试（无 GUI）
./scripts/bat2sh-dev --cli examples/hello.bat --print
# 语法校验生成的脚本
./scripts/bat2sh-dev --cli examples/deploy.bat --print | bash -n
# GUI 无显示环境自测（需要 PySide6）
QT_QPA_PLATFORM=offscreen python -c "from bat2sh.gui.app import run_gui"
```

测试覆盖转换器回归（批处理 / PowerShell）、编码检测、CLI 退出码与 examples 冒烟。
CI 由 GitHub Actions 在 Python 3.12 / 3.13 / 3.14 上运行 `pytest`，
配置见 `.github/workflows/test.yml`。

## 11. 许可

GNU Affero General Public License v3.0，见 `LICENSE`。
