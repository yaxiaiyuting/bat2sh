# bat2sh — Windows 脚本转 Bash 转换器

将 Windows 批处理（`.bat`/`.cmd`）与 PowerShell（`.ps1`）脚本转换为 Linux Bash 脚本的
桌面工具 + 命令行工具。界面使用 **Python 3 + PySide6（Qt6）**，贴合 KDE Breeze 风格，
在 Wayland（KWin）下原生运行；核心转换引擎只依赖 Python 标准库。

> 转换是"尽力而为"的静态翻译：能自动转换的语句会直接翻译，无法等价转换的语句会
> 插入 `# TODO: 手动检查: <原命令>` 注释并在预览中红色高亮。**生成脚本务必人工复核。**

---

## 1. 功能特性

- 三栏主界面：文件列表（支持拖拽）｜源文件预览（语法高亮、只读）｜转换结果（语法高亮、可编辑）
- 自动识别 `.bat`/`.cmd`（批处理）与 `.ps1`（PowerShell）
- 顶部工具栏：打开文件、打开文件夹、转换、保存、批量转换、预览差异、转换报告、主题、设置、关于
- 底部状态栏：转换进度、警告数、错误数、已转换行数
- 深色/浅色主题切换，默认跟随系统（KDE 下可用系统配色）
- 编码自动检测：UTF-8 BOM → UTF-8 → GBK → GB18030 → Latin-1，可手动覆盖
- 输出统一 UTF-8（无 BOM）、LF 行尾，可自动 `chmod +x`
- 转换报告：已转换行数、保持不变行数、警告、无法自动转换（TODO）清单
- 差异预览：`difflib` 生成源文件与转换结果的对照表
- 命令行模式：`bat2sh --cli input.bat -o output.sh`，适合脚本/CI 调用
- 规则集中定义在 `core/rules.py`，扩展翻译规则只需改表或加 `cmd_*` 方法

## 2. 项目结构

```text
bat2sh/
├── PKGBUILD                     # Arch/CachyOS 打包脚本 (makepkg -si)
├── bat2sh.install               # PKGBUILD 安装钩子
├── install.sh                   # 免打包安装脚本（默认 ~/.local）
├── bat2sh.desktop               # 桌面项
├── pyproject.toml               # pip/setuptools 打包配置
├── LICENSE
├── README.md
├── scripts/
│   ├── bat2sh-launcher          # 安装版启动器（供 PKGBUILD 使用）
│   └── bat2sh-dev               # 源码目录直接运行
├── examples/
│   ├── hello.bat  / hello.sh
│   ├── deploy.bat / deploy.sh
│   ├── backup.ps1 / backup.sh
│   └── cleanup.ps1/ cleanup.sh
└── src/bat2sh/
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
PKGBUILD 使用本地 tarball 模式（`sha256sums=('SKIP')`），发布到 AUR 时请替换为正式
source 与校验和。

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

## 4. 使用

### 4.1 图形界面

```bash
bat2sh            # 启动 GUI
bat2sh a.bat b.ps1  # 启动并载入文件
```

工作流：打开/拖入文件 → 自动转换并在右侧预览 → 按需编辑 → 保存（自动 `chmod +x`）。
"批量转换"会按设置逐个转换、写出，并弹出汇总报告。

快捷键：

| 快捷键 | 功能 |
| --- | --- |
| `Ctrl+O` | 打开文件 |
| `Ctrl+Shift+O` | 打开文件夹 |
| `Ctrl+Enter` | 转换当前文件 |
| `Ctrl+S` | 保存当前结果 |
| `Ctrl+Shift+R` | 批量转换 |
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
bat2sh --cli a.bat --report --fail-on-todo # CI: 有 TODO 时退出码 3
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
| `--encoding` | 强制输入编码（默认自动检测） |
| `--no-overwrite` | 输出已存在时拒绝覆盖 |
| `--print` | 输出到 stdout |
| `--report` | 打印转换报告 |
| `--fail-on-todo` | 存在 TODO 时返回 3 |
| `-q, --quiet` | 静默 |

退出码：`0` 成功；`2` 读取/写入/转换错误；`3` 使用 `--fail-on-todo` 且存在 TODO。

### 4.3 设置项

输出目录、输出后缀、自动 `chmod +x`、覆盖前备份、转换前备份源文件、允许覆盖、
缩进风格（2/4 空格、Tab）、变量加双引号、严格模式（`set -euo pipefail`）、主题。
设置保存在 `${XDG_CONFIG_HOME:-~/.config}/bat2sh/settings.json`。

## 5. 编码处理

- 检测顺序：UTF-8 BOM → UTF-16/32 BOM → UTF-8 → GBK → GB18030 → Latin-1 兜底。
- 纯标准库实现，不依赖 chardet；无法解码的字节以替换字符处理并在报告中警告。
- 界面上显示检测结果（"自动检测（gbk）"），可在下拉框中手动覆盖后重新转换。
- 输出固定为 UTF-8 无 BOM、LF 行尾。

## 6. 支持的转换规则

### 6.1 批处理（.bat/.cmd）

| 源语法 | 转换结果 |
| --- | --- |
| `rem x` / `:: x` | `# x` |
| `%VAR%`、`%1`、`%*`、`%~dp0`、`%~nx0`、`%~f1` | `${VAR}`、`$1`、`"$@"`、`${SCRIPT_DIR}/`、`$(basename "$0")`、`$(readlink -f "$1")` |
| `set VAR=value` | `VAR="value"`（去除尾随空格，自动加引号可配置） |
| `set /p VAR=提示` | `read -rp "提示" VAR` |
| `set /a x=1+2`、`set /a x+=1` | `x=$(( 1+2 ))`、`x=$(( x + (1) ))`，按位取反 `!`→`~` |
| `echo text` / `echo.` | `echo "text"` / `echo` |
| `pause` / `pause >nul` | `read -rp "Press Enter to continue..."` |
| `cls` | `clear` |
| `cd /d path` / `cd` | `cd "path"` / `pwd` |
| `dir [/b] [/s] [path]` | `ls -la` / `ls -1` / `ls -laR` |
| `copy` / `move` / `xcopy` / `robocopy` | `cp` / `mv` / `cp -r` / `rsync -a`（开关尽力映射，未知开关告警） |
| `del` / `erase` / `rmdir /s` / `md` | `rm -f`（`/s`→`rm -rf`）/ `rm -rf` / `mkdir -p` |
| `type file` | `cat file` |
| `find "s" f` / `findstr /i "s" f` | `grep -F` / `grep`（/i、/v、/n、/c 等已映射） |
| `start "" "file"` | `xdg-open "file" &`；可执行目标 → `nohup ... &` |
| `if exist X (...) else (...)` | `if [ -e "X" ]; then ... else ... fi` |
| `if "%A%"=="B" (...)`（equ/neq/lss/gtr…） | `if [ "$A" = "B" ]; then ...; fi` |
| `if errorlevel N` / `if not errorlevel N` | `if [ $? -ge N ]` / `[ $? -lt N ]`（含 `$?` 时机警告） |
| `if defined VAR` | `[ -n "${VAR:-}" ]` |
| `for %%i in (*.txt) do ...`（含嵌套、多行块） | `for i in *.txt; do ...; done` |
| `for /l %%i in (1,1,10) do ...` | `for i in $(seq 1 1 10); do ...; done` |
| `for /d %%d in (dir\*) do ...` | `for d in dir/*/; do ...; done` |
| `call :label args` / `:label` | `label_<name> args` / `label_<name>() { ... }`（子程序重构为函数并前置定义） |
| `call other.bat args` | `bash "other.sh" args`（提示确认已转换） |
| `goto :eof` | 函数内 `return 0`；顶层 `exit 0` |
| `exit /b N` / `exit N` | 函数内 `return N`；顶层 `exit N` |
| `%~dp0` 路径分隔符 `\` | `/`（含 `"dir\"` 尾反斜杠、驱动器前缀告警） |
| `>nul` / `2>&1` / `> file` | `>/dev/null` / 原样 / `>file`（顺序保持） |
| `ping -n/-w/-l/-t` | `ping -c/-W/-s`（毫秒→秒），`-t` 忽略并告警 |
| `tasklist` / `taskkill /im x /pid N` | `ps aux` / `pkill -f x`、`kill N` |
| `ipconfig` / `netstat` | `ip addr` / `ss -tuln`（输出格式不同，告警） |
| `timeout /t N` | `sleep N` |
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

> 下列内容会生成警告或 `# TODO`。请在保存前逐条核对转换报告。

### 8.1 批处理

1. **`goto`/标签控制流**：仅 `call :label` 子程序会被重构为函数。普通 `goto` 跳转、
   循环式 goto、跨标签 fall-through 无法等价转换 → `# TODO`。
2. **`for /f`、`for /r`**：命令输出解析、token/delims 选项、递归遍历 → 整块注释为 TODO
   （提示改用 `while read` / `find`）。
3. **延迟展开 `!var!`**：尽力转 `${var}`，但循环内赋值语义不同，需复核。
4. **`set /a`**：多表达式（逗号）、复杂位运算仅部分支持；`!`→`~` 为近似。
5. **`%DATE%`/`%TIME%`**：格式与 Windows 区域设置不同；`%ERRORLEVEL%`→`$?` 只反映
   紧邻上一条命令的退出码，插入其他命令后语义会变。
6. **`%VAR%` 的单词切分**、`^` 转义、空变量与引号嵌套：与 cmd 解析器存在细节差异。
7. **Windows 驱动器路径**：`C:\dir` 会变成 `C:/dir`（并非有效的 Linux 路径），
   需要手工改成挂载点；驱动器前缀会产生告警。
8. **Windows 专有命令**：`reg`、`sc`、`schtasks`、`wmic`、`attrib`、`icacls`、
   `takeown`、`diskpart`、`bcdedit`、`choice` 等 → TODO，并在报告中给出替代建议。
9. **近似命令**：`taskkill`→`pkill`、`ipconfig`→`ip addr`、`netstat`→`ss`、
   `shutdown`→`systemctl`、`robocopy`→`rsync -a`、`start`→`xdg-open`，
   行为/参数/输出并不完全一致；`start` 的窗口标题、`/wait`、`/b` 等语义有限。
10. **`cmd /c`、`runas`、`powershell -Command`**：引号嵌套复杂时需人工整理。
11. **`&` 分隔的多命令与管道混合**、`>file` 位置在命令之前等非常规写法：可能改变
    重定向顺序。
12. **`if errorlevel N`**：上一条是简单命令时，N=1 生成 `if ! cmd` / `if cmd`；
    N≥2 生成 `__bat2sh_status=0; cmd || __bat2sh_status=$?; if [ "$__bat2sh_status" -ge N ]`
    以保留精确退出码。上一条不是简单命令（前面是 `fi`/`done`/块语句）、`if /i`、
    `else if errorlevel` 等情况仍回退 `[ $? ... ]` 并告警；strict 模式下该回退通常是
    死代码（前一条命令失败时 `set -e` 已退出）。
13. **`goto :eof` 生成裸 `return`**（函数内）而非 `return 0`：批处理的 `goto :eof`
    不修改 errorlevel，裸 `return` 保留最后一条命令的退出码，调用方的
    `if errorlevel` 改写出的 `if ! func` 才能真正捕获失败；写成 `return 0` 会让
    函数永远报告成功。
14. **旧版 bash（<4.4）与 `set -u`**：`shopt -s nullglob` 让空 glob 产生空数组后，
    `"${arr[@]}"` 在 bash 4.4 以前会报 `unbound variable`。转换器面向 bash 5.x；
    如需兼容 RHEL7/macOS 自带旧 bash，请手工改为 `${arr[@]+"${arr[@]}"}`。

### 8.2 PowerShell

1. **对象管道**：`Where-Object`、`ForEach-Object`、`Select-Object`（除 `-First/-Last`）、
   `Group-Object`、`Get-Member`、`Format-Table/List`、`ConvertTo/From-Json` 等
   依赖对象模型 → TODO（建议改用 `grep/awk/jq`）。
2. **`try/catch/finally`**：仅保留控制结构（`if true; then ... else ... fi` + 注释），
   无真正的异常语义；建议配合脚本头 `set -e` 并手工整理错误处理。
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
7. **字符串/布尔差异**：PowerShell 插值、`-f` 格式运算符、here-string、反引号转义、
   空字符串与 0 的真值判断与 bash 不同；here-string 与 `-f` 会标 TODO。
8. **数组与哈希表**：`@{...}`、`.Keys/.Values`、对象数组属性访问无法等价；普通数组
   会转成 bash 数组（`"${arr[@]}"`）。
9. **`Read-Host -AsSecureString`**：转为 `read -s`，但返回的是纯文本而非安全字符串。
10. **`$?`/`$LASTEXITCODE`**：在 bash 中 `$?` 语义更窄，多条命令后需重新获取。
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
- `# TODO` 行与菜单"转换报告"是人工复核清单；`--fail-on-todo` 可用于 CI 卡点。
- 复杂脚本建议先分段转换、逐段验证，再合并。

## 9. 扩展转换规则

所有规则集中在 `src/bat2sh/core/rules.py`：

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
CI 由 GitHub Actions 在 Python 3.11 / 3.12 / 3.13 / 3.14 上运行 `pytest`，
配置见 `.github/workflows/test.yml`。

## 11. 许可

GNU Affero General Public License v3.0，见 `LICENSE`。
