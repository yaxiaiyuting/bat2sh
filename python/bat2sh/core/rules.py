"""转换规则表 —— 所有可扩展的映射和数据都集中在这里。

扩展方式：
* 简单命令（参数直接透传）：往 ``BATCH_SIMPLE_MAP`` / ``PS_SIMPLE_CMDLETS`` 加一行。
* 需要特判参数的命令：在 ``BATCH_HANDLER_MAP`` / ``PS_HANDLER_MAP`` 中把命令
  映射到转换器上的 ``cmd_*`` 方法，然后在对应转换器里实现该方法。
* Windows 专有命令：加入 ``BATCH_TODO_COMMANDS`` / ``PS_TODO_CMDLETS``，
  转换时会生成 ``# TODO: 手动检查: ...`` 注释。
"""

from __future__ import annotations

# =========================================================================
# 批处理 (.bat / .cmd)
# =========================================================================

#: 简单命令映射：命令名(小写) -> bash 命令前缀，参数原样透传（会做变量/路径转换）
BATCH_SIMPLE_MAP: dict[str, str] = {
    "type": "cat",
    "copy": "cp",
    "xcopy": "cp -r",
    "robocopy": "rsync -a",
    "move": "mv",
    "ren": "mv",
    "rename": "mv",
    "md": "mkdir -p",
    "mkdir": "mkdir -p",
    "pushd": "pushd",
    "popd": "popd",
    "fc": "diff",
    "comp": "cmp",
    "where": "command -v",
    "whoami": "whoami",
    "hostname": "hostname",
    "nslookup": "nslookup",
    "tree": "tree",
    "mklink": "ln -s",
    "shift": "shift",
    "break": "break",
    "goto": "",  # 由转换器特判
    "call": "",  # 由转换器特判
}

#: 需要特判参数的命令：命令名(小写) -> BatchConverter 方法名
BATCH_HANDLER_MAP: dict[str, str] = {
    "echo": "cmd_echo",
    "pause": "cmd_pause",
    "cls": "cmd_cls",
    "cd": "cmd_cd",
    "chdir": "cmd_cd",
    "copy": "cmd_copy",
    "move": "cmd_move",
    "xcopy": "cmd_xcopy",
    "robocopy": "cmd_robocopy",
    "dir": "cmd_dir",
    "del": "cmd_del",
    "erase": "cmd_del",
    "rd": "cmd_rmdir",
    "rmdir": "cmd_rmdir",
    "start": "cmd_start",
    "timeout": "cmd_timeout",
    "ping": "cmd_ping",
    "ipconfig": "cmd_ipconfig",
    "netstat": "cmd_netstat",
    "tasklist": "cmd_tasklist",
    "taskkill": "cmd_taskkill",
    "find": "cmd_find",
    "findstr": "cmd_findstr",
    "set": "cmd_set",
    "setx": "cmd_setx",
    "if": "cmd_if_unsupported",  # 不应到达（dispatcher 已处理）
    "exit": "cmd_exit",
    "shutdown": "cmd_shutdown",
    "attrib": "cmd_todo_hint",
    "icacls": "cmd_todo_hint",
    "cacls": "cmd_todo_hint",
    "net": "cmd_todo_hint",
    "sc": "cmd_todo_hint",
    "schtasks": "cmd_todo_hint",
    "reg": "cmd_todo_hint",
    "wmic": "cmd_todo_hint",
    "powershell": "cmd_powershell",
    "pwsh": "cmd_powershell",
    "cmd": "cmd_cmd",
    "runas": "cmd_runas",
    "setlocal": "cmd_noop",
    "endlocal": "cmd_noop",
    "title": "cmd_noop",
    "color": "cmd_noop",
    "chcp": "cmd_noop",
    "mode": "cmd_noop",
    "prompt": "cmd_noop",
    "verify": "cmd_noop",
    "doskey": "cmd_noop",
    "vol": "cmd_noop",
    "label": "cmd_noop",
    "ctty": "cmd_noop",
    "graphics": "cmd_noop",
    "loadhigh": "cmd_noop",
    "lh": "cmd_noop",
    "path": "cmd_todo_hint",
    "date": "cmd_todo_hint",
    "time": "cmd_todo_hint",
    "subst": "cmd_todo_hint",
    "diskpart": "cmd_todo_hint",
    "format": "cmd_todo_hint",
    "chkdsk": "cmd_todo_hint",
    "bcdedit": "cmd_todo_hint",
    "compact": "cmd_todo_hint",
    "cipher": "cmd_todo_hint",
    "fsutil": "cmd_todo_hint",
    "takeown": "cmd_todo_hint",
    "assoc": "cmd_assoc",
    "ftype": "cmd_ftype",
    "bcdboot": "cmd_todo_hint",
    "choice": "cmd_choice",
    "ver": "cmd_ver",
    "systeminfo": "cmd_systeminfo",
    "certutil": "cmd_certutil",
    "driverquery": "cmd_driverquery",
}

#: 完全忽略的批处理命令：命令名 -> 生成的注释（None 表示不生成任何输出）
BATCH_NOOP_MAP: dict[str, str | None] = {
    "setlocal": None,
    "endlocal": None,
    "title": None,
    "color": None,
    "chcp": None,
    "mode": None,
    "prompt": None,
    "verify": None,
    "doskey": None,
    "vol": None,
    "label": None,
    "ctty": None,
    "graphics": None,
    "loadhigh": None,
    "lh": None,
    "echo": None,
}

#: Windows 专有命令 -> 转换建议（生成 TODO）
BATCH_TODO_COMMANDS: dict[str, str] = {
    "attrib": "请改用 chmod 调整文件属性",
    "icacls": "请改用 chmod/chown 设置权限",
    "cacls": "请改用 chmod/chown 设置权限",
    "net": "请改用 systemctl/ss 等 Linux 命令",
    "sc": "服务管理请改用 systemctl",
    "schtasks": "计划任务请改用 cron 或 systemd timer",
    "reg": "注册表在 Linux 无对应物",
    "regedit": "注册表在 Linux 无对应物",
    "wmic": "WMI 在 Linux 无对应物，请改用 /proc、lsblk、lscpu 等",
    "path": "PATH 语法不同，请手动设置",
    "date": "修改系统日期请用 timedatectl（此处多为查询，请手动处理）",
    "time": "修改系统时间请用 timedatectl（此处多为查询，请手动处理）",
    "subst": "虚拟盘符在 Linux 无对应物",
    "diskpart": "磁盘分区请改用 parted/fdisk",
    "format": "格式化请改用 mkfs",
    "chkdsk": "磁盘检查请改用 fsck",
    "bcdedit": "引导配置请改用 grub/systemd-boot",
    "compact": "NTFS 压缩无对应物",
    "cipher": "EFS 加密无对应物",
    "fsutil": "文件系统工具无对应物",
    "takeown": "所有权请改用 chown",
    "bcdboot": "引导配置请改用 grub/systemd-boot",
}

#: assoc 查询的扩展名 -> MIME 类型（仅覆盖常见类型，其余保持 TODO）
BATCH_EXT_MIME: dict[str, str] = {
    ".txt": "text/plain",
    ".log": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "application/xml",
    ".json": "application/json",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".zip": "application/zip",
    ".gz": "application/gzip",
    ".tar": "application/x-tar",
    ".sh": "application/x-shellscript",
    ".py": "text/x-python",
}

#: ftype 查询的文件类型名 -> MIME 类型（仅覆盖常见类型，其余保持 TODO）
BATCH_FTYPE_MIME: dict[str, str] = {
    "txtfile": "text/plain",
    "logfile": "text/plain",
    "markdownfile": "text/markdown",
    "htmlfile": "text/html",
    "xmlfile": "application/xml",
    "jsonfile": "application/json",
    "pdffile": "application/pdf",
    "pngfile": "image/png",
    "jpegfile": "image/jpeg",
    "giffile": "image/gif",
    "svgfile": "image/svg+xml",
    "mp3file": "audio/mpeg",
    "mp4file": "video/mp4",
    "zipfile": "application/zip",
    "gzipfile": "application/gzip",
    "pythonfile": "text/x-python",
    "shfile": "application/x-shellscript",
}

#: %VAR% 特殊变量映射（大写键）
BATCH_ENV_MAP: dict[str, str] = {
    "CD": "$(pwd)",
    "USERNAME": "${USER}",
    "USERPROFILE": "${HOME}",
    "HOMEPATH": "${HOME}",
    "HOMEDRIVE": "",
    "TEMP": "${TMPDIR:-/tmp}",
    "TMP": "${TMPDIR:-/tmp}",
    "PATH": "${PATH}",
    "RANDOM": "$RANDOM",
    "ERRORLEVEL": "$?",
    "OS": "Linux",
    "COMSPEC": "/bin/bash",
    "PROCESSOR_ARCHITECTURE": "$(uname -m)",
    "PROCESSOR_IDENTIFIER": "$(uname -p)",
    "NUMBER_OF_PROCESSORS": "$(nproc)",
    "COMPUTERNAME": "$(hostname)",
    "DATE": "$(date +%F)",
    "TIME": "$(date +%T)",
    "SYSTEMDRIVE": "/",
    "SYSTEMROOT": "${SystemRoot:-/}",
    "WINDIR": "/",
    "PROGRAMDATA": "/usr/share",
    "LOCALAPPDATA": "${XDG_DATA_HOME:-$HOME/.local/share}",
    "APPDATA": "${XDG_CONFIG_HOME:-$HOME/.config}",
}

#: 转换时需要提醒语义差异的变量
BATCH_ENV_WARN: set[str] = {"ERRORLEVEL", "DATE", "TIME", "SYSTEMROOT", "WINDIR", "PROGRAMDATA", "APPDATA", "LOCALAPPDATA"}

#: .exe / .cmd 可执行文件名 -> Linux 命令
BATCH_EXE_MAP: dict[str, str] = {
    "python.exe": "python3",
    "python3.exe": "python3",
    "pip.exe": "pip3",
    "java.exe": "java",
    "javac.exe": "javac",
    "node.exe": "node",
    "npm.cmd": "npm",
    "npx.cmd": "npx",
    "git.exe": "git",
    "curl.exe": "curl",
    "wget.exe": "wget",
    "tar.exe": "tar",
    "ssh.exe": "ssh",
    "scp.exe": "scp",
    "sqlite3.exe": "sqlite3",
    "ffmpeg.exe": "ffmpeg",
    "7z.exe": "7z",
    "code.cmd": "code",
}

#: 在 Linux 上通常可直接使用的命令（保留时不再警告）
BATCH_POSIX_KEEP: set[str] = {
    "python", "python3", "pip", "pip3", "git", "curl", "wget", "tar", "unzip", "zip",
    "gzip", "gunzip", "bzip2", "xz", "sed", "awk", "grep", "egrep", "fgrep", "find",
    "xargs", "sort", "uniq", "head", "tail", "wc", "cat", "ls", "cp", "mv", "rm",
    "mkdir", "rmdir", "touch", "chmod", "chown", "ln", "readlink", "realpath",
    "echo", "printf", "sleep", "kill", "pkill", "ps", "top", "ssh", "scp", "sftp",
    "rsync", "make", "cmake", "gcc", "g++", "clang", "java", "javac", "jar", "node",
    "npm", "npx", "yarn", "pnpm", "pipx", "docker", "podman", "podman-compose",
    "systemctl", "journalctl", "systemd-run", "timedatectl", "localectl", "loginctl",
    "ss", "ip", "ping", "traceroute", "dig", "host", "nc", "nmap", "openssl",
    "ffmpeg", "convert", "magick", "vim", "nano", "xdg-open", "notify-send",
    "bash", "sh", "source", "env", "export", "read", "test", "seq", "basename",
    "dirname", "date", "hostname", "whoami", "id", "groups", "uname", "nproc",
    "mount", "umount", "df", "du", "free", "lsblk", "lscpu", "lsusb", "lspci",
    "sqlite3", "mysql", "psql", "redis-cli", "jq", "yq", "tree", "file", "stat",
    "md5sum", "sha256sum", "base64", "diff", "patch", "tee", "tr", "cut", "paste",
    "sleep", "wait", "true", "false", "yes", "which", "type", "command", "alias",
    "dotnet", "go", "cargo", "rustc", "uv", "uvx", "code", "flatpak", "pacman",
    "apt", "dnf", "yay", "paru", "brave", "firefox", "chromium", "vlc", "mpv",
}

#: 批处理比较运算符 -> bash test 运算符
BATCH_TEST_OPERATORS: dict[str, str] = {
    "==": "=",
    "===": "=",
    "equ": "-eq",
    "neq": "-ne",
    "lss": "-lt",
    "leq": "-le",
    "gtr": "-gt",
    "geq": "-ge",
}


# =========================================================================
# PowerShell (.ps1)
# =========================================================================

#: 简单 cmdlet 映射：cmdlet(小写) -> bash 命令（参数原样透传）
PS_SIMPLE_CMDLETS: dict[str, str] = {
    "write-output": "echo",
    "clear-host": "clear",
    "set-location": "cd",
    "chdir": "cd",
    "get-location": "pwd",
    "push-location": "pushd",
    "pop-location": "popd",
    "select-string": "grep",
    "sort-object": "sort",
    "out-null": "true",
    "get-process": "ps aux",
    "get-date": "date",
    "get-command": "command -v",
    "set-strictmode": ":",
    "set-executionpolicy": ":",
    "update-formatdata": ":",
    "start-transcript": ":",
    "stop-transcript": ":",
    "set-variable": "export",
    "new-variable": "export",
    "remove-variable": "unset",
    "get-variable": "env",
    "test-connection": "ping",
}

#: 需要特判参数的 cmdlet：cmdlet(小写) -> PowerShellConverter 方法名
PS_HANDLER_MAP: dict[str, str] = {
    "write-host": "cmd_write_host",
    "write-warning": "cmd_write_warning",
    "write-error": "cmd_write_error",
    "write-verbose": "cmd_write_verbose",
    "write-debug": "cmd_write_debug",
    "get-date": "cmd_get_date",
    "read-host": "cmd_read_host",
    "get-childitem": "cmd_get_childitem",
    "get-content": "cmd_get_content",
    "set-content": "cmd_set_content",
    "add-content": "cmd_add_content",
    "out-file": "cmd_out_file",
    "copy-item": "cmd_copy_item",
    "move-item": "cmd_move_item",
    "remove-item": "cmd_remove_item",
    "rename-item": "cmd_rename_item",
    "new-item": "cmd_new_item",
    "test-path": "cmd_test_path",
    "join-path": "cmd_join_path",
    "split-path": "cmd_split_path",
    "resolve-path": "cmd_resolve_path",
    "invoke-webrequest": "cmd_invoke_webrequest",
    "invoke-restmethod": "cmd_invoke_webrequest",
    "expand-archive": "cmd_expand_archive",
    "compress-archive": "cmd_compress_archive",
    "start-sleep": "cmd_start_sleep",
    "stop-process": "cmd_stop_process",
    "start-process": "cmd_start_process",
    "tee-object": "cmd_tee_object",
    "measure-object": "cmd_measure_object",
    "select-object": "cmd_select_object",
    "where-object": "cmd_where_object",
    "foreach-object": "cmd_foreach_object",
    "convertto-json": "cmd_todo_cmdlet",
    "convertfrom-json": "cmd_todo_cmdlet",
    "get-member": "cmd_todo_cmdlet",
    "get-itemproperty": "cmd_todo_cmdlet",
    "set-itemproperty": "cmd_todo_cmdlet",
    "new-object": "cmd_todo_cmdlet",
    "add-type": "cmd_todo_cmdlet",
    "add-member": "cmd_todo_cmdlet",
    "out-string": "cmd_todo_cmdlet",
    "get-service": "cmd_service",
    "restart-service": "cmd_service",
    "stop-service": "cmd_service",
    "start-service": "cmd_service",
    "get-item": "cmd_get_item",
    "get-childitem": "cmd_get_childitem",
    "get-acl": "cmd_todo_cmdlet",
    "set-acl": "cmd_todo_cmdlet",
    "invoke-expression": "cmd_todo_cmdlet",
    "get-help": "cmd_get_help",
    "format-table": "cmd_todo_cmdlet",
    "format-list": "cmd_todo_cmdlet",
}

#: PowerShell 专有 cmdlet -> 转换建议（生成 TODO）
PS_TODO_CMDLETS: dict[str, str] = {
    "new-object": "请改用对应语言的构造方式",
    "add-type": "编译 C# 代码在 Linux 无对应物",
    "add-member": "对象成员操作无对应物",
    "convertto-json": "请改用 jq 处理 JSON",
    "convertfrom-json": "请改用 jq 处理 JSON",
    "get-member": "对象反射无对应物",
    "get-itemproperty": "请改用环境变量或配置文件",
    "set-itemproperty": "请改用环境变量或配置文件",
    "get-acl": "请改用 ls -l / getfacl",
    "set-acl": "请改用 chmod/setfacl",
    "invoke-expression": "动态执行请改用 eval（注意安全风险）",
    "format-table": "表格输出请改用 column -t",
    "format-list": "请手动格式化输出",
    "out-string": "请改用管道与文本工具",
    "register-scheduledjob": "计划任务请改用 cron/systemd timer",
    "register-scheduledtask": "计划任务请改用 cron/systemd timer",
    "start-job": "后台任务请改用 & 或 systemd-run",
    "wait-job": "后台任务请改用 wait",
    "receive-job": "后台任务请改用 wait 与输出重定向",
    "stop-job": "后台任务请改用 kill",
    "get-eventlog": "事件日志请改用 journalctl",
    "get-winevent": "事件日志请改用 journalctl",
    "write-eventlog": "事件日志请改用 logger",
    "get-counter": "性能计数请改用 /proc 或 perf",
    "measure-command": "计时请改用 time",
    "get-wmiobject": "WMI 在 Linux 无对应物",
    "get-ciminstance": "CIM/WMI 在 Linux 无对应物",
    "set-service": "请改用 systemctl",
    "get-hotfix": "补丁管理请改用包管理器",
    "get-computerinfo": "请改用 /proc 与 dmidecode",
    "restart-computer": "请改用 systemctl reboot",
    "stop-computer": "请改用 systemctl poweroff",
    "set-timezone": "请改用 timedatectl",
    "new-service": "请改用 systemd unit",
    "get-scheduledtask": "计划任务请改用 crontab -l",
    "get-psdrive": "驱动器在 Linux 无对应物",
    "new-psdrive": "驱动器在 Linux 无对应物",
    "out-gridview": "图形输出请改用 zenity/文本输出",
    "get-clipboard": "剪贴板请改用 xclip/wl-paste",
    "set-clipboard": "剪贴板请改用 xclip/wl-copy",
    "show-command": "图形化命令窗口无对应物",
    "get-credential": "凭据管理请改用 secret-tool/pass",
}

#: PowerShell 自动变量 -> bash 片段
PS_AUTOMATIC_VARS: dict[str, str] = {
    "args": '"$@"',
    "input": '"$@"',
    "psscriptroot": "${SCRIPT_DIR}",
    "pscommandpath": "${BASH_SOURCE[0]}",
    "pwd": "$(pwd)",
    "home": "${HOME}",
    "true": "true",
    "false": "false",
    "null": '""',
}

#: 无法自动转换、需要 TODO 的自动变量
PS_TODO_VARS: dict[str, str] = {
    "psboundparameters": "参数绑定在 bash 无对应物",
    "myinvocation": "调用上下文无对应物",
    "error": "错误对象无对应物",
    "lastexitcode": "注意：$? 只能反映上一条命令的退出码",
    "host": "宿主对象无对应物",
    "psversiontable": "版本表无对应物",
    "profile": "配置文件概念不同",
    "matches": "正则匹配结果无对应物",
}

#: $env:NAME 环境变量映射（小写键）。Windows 与 Linux 的默认值可能不同，属近似映射。
PS_ENV_MAP: dict[str, str] = {
    "temp": "${TMPDIR:-/tmp}",
    "tmp": "${TMPDIR:-/tmp}",
    "userprofile": "${HOME}",
    "homepath": "${HOME}",
    "homedrive": "",
    "appdata": "${XDG_CONFIG_HOME:-$HOME/.config}",
    "localappdata": "${XDG_DATA_HOME:-$HOME/.local/share}",
    "programdata": "/usr/share",
    "username": "${USER}",
    "computername": "$(hostname)",
    "processor_architecture": "$(uname -m)",
    "number_of_processors": "$(nproc)",
    "systemdrive": "/",
    "systemroot": "/",
    "windir": "/",
    "path": "${PATH}",
    "os": "Linux",
}

#: 需要提醒"近似映射"的 $env: 变量
PS_ENV_WARN: set[str] = {
    "temp", "tmp", "userprofile", "homepath", "homedrive", "appdata",
    "localappdata", "programdata", "systemdrive", "systemroot", "windir",
}

#: PowerShell 日期格式 -> strftime 占位符（按顺序替换）
PS_DATE_TOKENS: tuple[tuple[str, str], ...] = (
    ("yyyy", "%Y"),
    ("yy", "%y"),
    ("MMMM", "%B"),
    ("MMM", "%b"),
    ("MM", "%m"),
    ("dddd", "%A"),
    ("ddd", "%a"),
    ("dd", "%d"),
    ("HH", "%H"),
    ("hh", "%I"),
    ("mm", "%M"),
    ("ss", "%S"),
    ("tt", "%p"),
    ("fff", "%3N"),
    ("zzz", "%:z"),
)

#: PowerShell 比较运算符（小写）-> bash [[ ]] 运算符
PS_TEST_OPERATORS: dict[str, str] = {
    "-eq": "=",
    "-ne": "!=",
    "-gt": "-gt",
    "-lt": "-lt",
    "-ge": "-ge",
    "-le": "-le",
    "-like": "==",
    "-notlike": "!=",
    "-ceq": "=",
    "-cne": "!=",
}

#: 逻辑运算符（小写）-> bash
PS_LOGIC_OPERATORS: dict[str, str] = {
    "-and": "&&",
    "-or": "||",
    "-xor": "!=",
    "-not": "!",
}

#: 在 Linux 上通常可直接使用的命令（保留时不再警告）
PS_POSIX_KEEP: set[str] = BATCH_POSIX_KEEP

#: 转换时需要提醒语义差异的 cmdlet
PS_WARN_CMDLETS: set[str] = {
    "select-string", "sort-object", "get-process", "set-location", "push-location",
}
