#!/usr/bin/env bash
# 由 bat2sh 自动转换生成，源文件: stress_test.bat
# 带有 # TODO 标记的行无法自动转换，请人工检查
set -euo pipefail
# 检测到通配符匹配：已启用 nullglob，无匹配时循环体不执行
shopt -s nullglob
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

label_SKIP() {
    echo "跳过了。"

    # 使用 goto :eof 在子程序中
    label_RETURN_EOF
    echo "从 :eof 返回"

    # 使用 exit /b
    label_EXIT_B
    # TODO: 手动检查: echo 从 exit /b 返回，ERRORLEVEL=%ERRORLEVEL%

    # 使用 shift
    label_SHIFT_TEST a b c d
    echo "shift 测试完成"

    # 使用 %* 和 %~dp0
    label_SHOW_ARGS one two three

    # 使用 for 遍历参数
    echo "遍历参数:"
    for a in "$@"; do
        echo "参数: ${a}"
    done

    # 使用 if 各种形式
    if [ -n "${MY_VAR:-}" ]; then
        echo "MY_VAR 已定义"
    fi
    if [ -z "${NOT_DEFINED:-}" ]; then
        echo "NOT_DEFINED 未定义"
    fi
    if [ -e "test1.txt" ]; then
        echo "test1.txt 存在"
    fi
    if [ ! -e "nonexistent.txt" ]; then
        echo "nonexistent.txt 不存在"
    fi
    if [ "${MY_VAR}" = "Hello World" ]; then
        echo "字符串相等"
    fi
    if [[ "hello" == "hello" ]]; then
        echo "忽略大小写相等"
    fi
    if [ "${NUM1}" -gt "${NUM2}" ]; then
        echo "NUM1 大于 NUM2"
    fi
    if [ "${NUM1}" -lt "${NUM2}" ]; then
        echo "NUM1 小于 NUM2"
    else
        echo "NUM1 不小于 NUM2"
    fi
    if [ $? -ge 0 ]; then
        echo "ERRORLEVEL  0" >=
    fi
    # TODO: 手动检查: if %ERRORLEVEL% equ 0 echo ERRORLEVEL 等于 0
    if [ 0 -eq 1 ]; then
        echo "命令扩展版本  2" >=
    fi

    # 使用 assoc 和 ftype
    echo "文件关联:"
    xdg-mime query default text/plain 2>/dev/null
    xdg-mime query default text/plain 2>/dev/null

    # 使用 vol
    echo "卷信息:"

    # 使用 systeminfo
    echo "系统信息摘要:"
    # TODO: 复杂管道需手动重写
    #  原命令: systeminfo | findstr /i "OS 名称 OS Name 版本 Version 系统类型 System Type" 2>nul
    #  参考(中): uname -a | grep -i "OS 名称 OS Name 版本 Version 系统类型 System Type" 2>/dev/null
    #  差异: 信息量与结构差异大；系统版本请另加 cat /etc/os-release；findstr 与 grep 的正则语法存在差异（/r 在 grep 中为默认行为）

    # 使用 driverquery
    echo "驱动查询:"
    # TODO: 复杂管道需手动重写
    #  原命令: driverquery | findstr /i "Running" | findstr /i "True" 2>nul | findstr /n "^" | findstr "^[1-5]:"
    #  参考(中): lsmod | grep -i "Running" | grep -i "True" 2>/dev/null | grep -n "^" | grep "^[1-5]:"
    #  差异: 驱动服务与内核模块语义不同；findstr 与 grep 的正则语法存在差异（/r 在 grep 中为默认行为）

    # 使用 tasklist 更多
    echo "任务列表:"
    # TODO: 复杂管道需手动重写
    #  原命令: tasklist /svc | findstr /i "svchost" | findstr /n "^" | findstr "^[1-5]:"
    #  参考(中): ps aux /svc | grep -i "svchost" | grep -n "^" | grep "^[1-5]:"
    #  差异: 列格式完全不同；/fi 等过滤条件需改写为 grep/ps 选项；findstr 与 grep 的正则语法存在差异（/r 在 grep 中为默认行为）

    # 使用 net user 和 net start
    echo "本地用户:"
    # TODO: 复杂管道需手动重写
    #  原命令: net user 2>nul | findstr /v "命令成功完成" | findstr /n "^" | findstr "^[1-5]:"
    #  参考(中): getent passwd 2>/dev/null | grep -v "命令成功完成" | grep -n "^" | grep "^[1-5]:"
    #  差异: 输出无表头，字段与格式完全不同；findstr 与 grep 的正则语法存在差异（/r 在 grep 中为默认行为）
    echo "已启动服务:"
    # TODO: 复杂管道需手动重写
    #  原命令: net start 2>nul | findstr /n "^" | findstr "^[1-5]:"
    #  参考(中): systemctl list-units --type=service --state=running | grep -n "^" | grep "^[1-5]:"
    #  差异: 输出格式不同（无 Windows 的清单标题与列）；findstr 与 grep 的正则语法存在差异（/r 在 grep 中为默认行为）

    # 使用 whoami
    echo "当前用户:"
    # TODO: 手动检查: whoami /all 2>nul | findstr /i "用户名 User Name 组 Group" | findstr /n "^" | findstr "^[1-5]:"

    # 使用 query user
    echo "登录用户:"
    query user 2>/dev/null

    # 使用 icacls
    echo "文件权限:"

    # 使用 %~dp0 和 %~nx0
    echo "脚本完整路径: $(readlink -f "$0")"
    echo "脚本驱动器: ${SCRIPT_DIR}/"
    echo "脚本路径: ${SCRIPT_DIR}/"
    echo "脚本名称: \"$0\""
    echo "脚本扩展名: \"$0\""
    echo "脚本短名: %s0"
    echo "脚本属性: %a0"
    echo "脚本时间: %t0"
    echo "脚本大小: %z0"

    # 使用 %~$PATH:1 搜索路径
    echo "PATH 中查找 notepad: %~\$PATH:notepad"

    # 使用 %CD% 和 %=C:%
    echo "当前目录: $(pwd)"
    echo "当前目录扩展: %=C:%"

    # 使用 %RANDOM% 和 %ERRORLEVEL%
    echo "随机数: $RANDOM"
    # TODO: 手动检查: echo 错误级别: %ERRORLEVEL%

    # 使用 %DATE% 和 %TIME% 解析
    # TODO: 手动检查: for /f "tokens=1-3 delims=/- " %%a in ("%DATE%") do (
        # set "YEAR=%%c"
        # set "MONTH=%%a"
        # set "DAY=%%b"
    echo "解析日期: 年=${YEAR} 月=${MONTH} 日=${DAY}"
    # TODO: 手动检查: for /f "tokens=1-3 delims=:." %%a in ("%TIME%") do (
        # set "HOUR=%%a"
        # set "MIN=%%b"
        # set "SEC=%%c"
    echo "解析时间: 时=${HOUR} 分=${MIN} 秒=${SEC}"

    # 使用 if 嵌套
    if [ -e "test1.txt" ]; then
        if [ -e "test2.txt" ]; then
            echo "两个文件都存在"
        else
            echo "test1 存在但 test2 不存在"
        fi
    else
        echo "test1 不存在"
    fi

    # 使用括号块和延迟扩展
    COUNTER="0"
    for i in $(seq 1 1 3); do
        COUNTER=$(( COUNTER + (1) ))
        if [ "${COUNTER}" -eq 2 ]; then
            echo "计数器为 2"
        else
            echo "计数器为 ${COUNTER}"
        fi
    done

    # 使用 & 和 && 和 ||
    echo "命令分隔: echo A"
    echo "B"
    echo "条件执行: (echo C) && (echo D)"
    echo "条件执行: (exit /b 1) || (echo E)"

    # 使用 | 管道和 > 重定向组合
    echo "管道重定向:"
    # TODO: 手动检查: echo hello | findstr "hello" > pipe.txt
    cat pipe.txt

    # 使用 2>&1 合并错误
    # TODO: 手动检查: echo 错误合并: dir nonexistent 2>&1 | findstr /i "找不到"

    # 使用 >nul 2>&1 抑制输出
    echo "抑制输出: dir" >/dev/null 2>&1

    # 使用 < 输入重定向
    echo "输入重定向: findstr \"第一行\"" <test1.txt

    # 使用 for /f 解析带引号的字符串
    # TODO: 手动检查: for /f "tokens=1-3 delims=," %%a in ("one,two,three") do echo %%a %%b %%c

    # 使用 for /f 解析命令输出并跳过行
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [ -z "$a" ] && continue
        echo "文件: ${a}"
    done < <(ls -1 | tail -n +2)

    # 使用 for /f 解析带 eol 的
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [[ -z "$a" || "$a" == \;* ]] && continue
        echo "行: ${a}"
    done < "test1.txt"

    # 使用 for /f 解析多行命令输出
    # TODO: 手动检查: for /f "tokens=*" %%a in ('echo line1^& echo line2^& echo line3') do echo 输出: %%a

    # 使用 for /f 解析 powershell 输出
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [ -z "$a" ] && continue
        echo "PS输出: ${a}"
    done < <(pwsh -NoProfile -Command "Write-Output 'PS line'")

    # 使用 for /f 解析 wmic 输出
    # TODO: 手动检查: for /f "tokens=2 delims==" %%a in ('wmic os get Caption /value 2^>nul ^| findstr "Caption"') do echo OS: %%a

    # 使用 for /f 解析注册表输出
    # TODO: 手动检查: for /f "tokens=3" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v ProductName 2^>nul ^| findstr "ProductName"') do echo 产品名称: %%a

    # 使用 for /f 解析 netstat
    # TODO: 手动检查: for /f "tokens=2" %%a in ('netstat -an ^| findstr "LISTENING" ^| findstr ":135"') do echo 端口135: %%a

    # 使用 for /f 解析 tasklist
    # TODO: 手动检查: for /f "tokens=1,2" %%a in ('tasklist /fi "imagename eq explorer.exe" ^| findstr /i "explorer"') do echo 进程: %%a PID: %%b

    # 使用 for /f 解析 sc query
    # TODO: 手动检查: for /f "tokens=1,2" %%a in ('sc query wuauserv ^| findstr "STATE"') do echo 服务状态: %%a %%b

    # 使用 for /f 解析 whoami
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [ -z "$a" ] && continue
        echo "当前用户: ${a}"
    done < <(whoami)

    # 使用 for /f 解析 ipconfig
    # TODO: 手动检查: for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do echo IP: %%a

    # 使用 for /f 解析 systeminfo
    # TODO: 手动检查: for /f "tokens=2 delims=:" %%a in ('systeminfo ^| findstr /i "OS Name"') do echo OS: %%a

    # 使用 for /f 解析 driverquery
    # TODO: 手动检查: for /f "tokens=1" %%a in ('driverquery ^| findstr /i "Running"') do echo 驱动: %%a

    # 使用 for /f 解析 net user
    # TODO: 手动检查: for /f "tokens=*" %%a in ('net user ^| findstr /v "命令成功完成"') do echo 用户: %%a

    # 使用 for /f 解析 net start
    # TODO: 手动检查: for /f "tokens=*" %%a in ('net start ^| findstr /v "命令成功完成"') do echo 服务: %%a

    # 使用 for /f 解析 query user
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [ -z "$a" ] && continue
        echo "登录: ${a}"
    done < <(query user)

    # 使用 for /f 解析 icacls
    # TODO: 手动检查: for /f "tokens=*" %%a in ('icacls test1.txt') do echo 权限: %%a

    # 使用 for /f 解析 certutil
    # TODO: 手动检查: for /f "tokens=*" %%a in ('certutil -hashfile test1.txt MD5 ^| findstr /v "hash CertUtil"') do echo 哈希: %%a

    # 使用 for /f 解析 robocopy
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [ -z "$a" ] && continue
        echo "robocopy: ${a}"
    done < <(rsync -a . . test1.txt /NJH /NJS /NDL /NC /NS)

    # 使用 for /f 解析 xcopy
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [ -z "$a" ] && continue
        echo "xcopy: ${a}"
    done < <(cp -r "test1.txt" "test4.txt")

    # 使用 for /f 解析 assoc
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [ -z "$a" ] && continue
        echo "关联: ${a}"
    done < <(xdg-mime query default text/plain)

    # 使用 for /f 解析 ftype
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [ -z "$a" ] && continue
        echo "类型: ${a}"
    done < <(xdg-mime query default text/plain)

    # 使用 for /f 解析 vol
    # TODO: 手动检查: for /f "tokens=*" %%a in ('vol C:') do echo 卷: %%a

    # 使用 for /f 解析 chcp
    # TODO: 手动检查: for /f "tokens=*" %%a in ('chcp') do echo 代码页: %%a

    # 使用 for /f 解析 set
    while IFS='=' read -r a b; do
        b="${b%$'\r'}"
        [ -z "$a" ] && continue
        if [ "${a}" = "PATH" ]; then
            echo "PATH=${b}"
        fi
        if [ "${a}" = "TEMP" ]; then
            echo "TEMP=${b}"
        fi
        if [ "${a}" = "USERNAME" ]; then
            echo "USERNAME=${b}"
        fi
    done < <(env)

    # 使用 for /f 解析 cd
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [ -z "$a" ] && continue
        echo "当前目录: ${a}"
    done < <(pwd)

    # 使用 for /f 解析 date
    # TODO: 手动检查: for /f "tokens=*" %%a in ('date /t') do echo 日期: %%a

    # 使用 for /f 解析 time
    # TODO: 手动检查: for /f "tokens=*" %%a in ('time /t') do echo 时间: %%a

    # 使用 for /f 解析 title
    # TODO: 手动检查: for /f "tokens=*" %%a in ('title') do echo 标题: %%a

    # 使用 for /f 解析 color
    # TODO: 手动检查: for /f "tokens=*" %%a in ('color') do echo 颜色: %%a

    # 使用 for /f 解析 mode
    # TODO: 手动检查: for /f "tokens=*" %%a in ('mode con') do echo 模式: %%a

    # 使用 for /f 解析 ver
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [ -z "$a" ] && continue
        echo "版本: ${a}"
    done < <(uname -a)

    # 使用 for /f 解析 echo
    while IFS= read -r a; do
        a="${a%$'\r'}"
        [ -z "$a" ] && continue
        echo "回显: ${a}"
    done < <(echo "hello")

    # 使用 for /f 解析 rem
    # TODO: 手动检查: for /f "tokens=*" %%a in ('rem comment') do echo 注释: %%a

    # 结束部分
    echo
    echo "============================================================"
    echo "测试完成。"
    echo "日志文件: ${LOG_FILE}"
    echo "工作目录: ${WORK_DIR}"
    echo "============================================================"

    # 清理临时文件
    popd
    rm -rf "${WORK_DIR}" 2>/dev/null
    rm -f "${LOG_FILE}" 2>/dev/null

    return 0

    # ============================================================
    # 子程序定义
    # ============================================================
}

label_SUBROUTINE() {
    echo "子程序: 参数1=$1, 参数2=$2"
    LOCAL_VAR="子程序局部变量"
    echo "子程序局部变量: ${LOCAL_VAR}"
    return 0
}

label_TEST_ERROR() {
    echo "测试错误处理..."
    return 1
}

label_RETURN_EOF() {
    echo "这是 :RETURN_EOF 子程序"
    return
}

label_EXIT_B() {
    echo "这是 :EXIT_B 子程序"
    return 5
}

label_SHIFT_TEST() {
    echo "shift 测试开始，参数: \"$@\""
    shift
    echo "移动后参数: \"$@\""
    shift
    echo "再次移动后参数: \"$@\""
    return 0
}

label_SHOW_ARGS() {
    echo "子程序参数: \"$@\""
    echo "第一个参数: $1"
    echo "所有参数: \"$@\""
    return 0
}
# ============================================================
# 复杂批处理测试脚本 - 用于测试 bat2sh 转换器
# ============================================================

SCRIPT_NAME="$(basename \"$0\")"
SCRIPT_DIR="${SCRIPT_DIR}/"
LOG_FILE="${TMPDIR:-/tmp}/complex_bat_test_$RANDOM.log"
WORK_DIR="${TMPDIR:-/tmp}/complex_bat_test_$RANDOM"

echo "[$(date +%Y-%m-%d) $(date +%H:%M:%S)] 开始执行 ${SCRIPT_NAME}" >"${LOG_FILE}"
echo "脚本目录: ${SCRIPT_DIR}" >>"${LOG_FILE}"

# 参数处理
ARG1="$1"
ARG2="$2"
ALL_ARGS="\"$@\""
if [ "$1" = "" ]; then
    echo "未提供参数，使用默认值。"
    ARG1="default1"
    ARG2="default2"
else
    echo "参数1: ${ARG1}"
    echo "参数2: ${ARG2}"
fi
echo "所有参数: ${ALL_ARGS}"

# 字符串操作
STR="Hello, World! This is a complex BAT script."
echo "原始字符串: ${STR}"
echo "子字符串(0,5): %STR:~0,5%"
echo "子字符串(7): %STR:~7%"
echo "替换 World 为 BAT: %STR:World=BAT%"
echo "删除逗号前内容: %STR:*:=%"
STR2="abcdef"
echo "从右取3个: %STR2:~-3%"
echo "取第2到第4: %STR2:~1,3%"

# 算术运算
NUM1=$(( 10 ))
NUM2=$(( 3 ))
SUM=$(( ${NUM1} + ${NUM2} ))
MOD=$(( ${NUM1} % ${NUM2} ))
echo "算术: ${NUM1} + ${NUM2} = ${SUM}, ${NUM1} % ${NUM2} = ${MOD}"
RAND_NUM=$(( $RANDOM % 100 ))
echo "随机数: ${RAND_NUM}"
COMPLEX=$(( (10+20)*3/2-5 ))
echo "复杂算术: ${COMPLEX}"
BITWISE=$(( 5 & 3 ))
echo "位运算: ${BITWISE}"
SHIFT=$(( 1 << 3 ))
echo "左移: ${SHIFT}"

# 延迟扩展与变量嵌套
VAR_NAME="DYNAMIC"
DYNAMIC="这是动态变量"
echo "延迟扩展: !${VAR_NAME}!"
INDIRECT="${!VAR_NAME}"
echo "间接引用: ${INDIRECT}"

A="B"
B="Value"
RESULT="${!A}"
echo "嵌套变量: ${RESULT}"
RESULT2="!${A}!"
echo "延迟嵌套: ${RESULT2}"

# 创建临时工作目录
if [ ! -e "${WORK_DIR}" ]; then
    mkdir -p "${WORK_DIR}"
fi
pushd "${WORK_DIR}"
echo "当前工作目录: $(pwd)"

# 文件操作
echo "这是第一行" >test1.txt
echo "这是第二行" >>test1.txt
echo "第三行包含数字 12345" >>test1.txt
cat test1.txt
cp "test1.txt" "test2.txt" >/dev/null
grep "[0-9][0-9]*" "test1.txt" >numbers.txt
sort /r test1.txt >sorted.txt
diff test1.txt test2.txt  && echo 文件相同 || echo 文件不同 >/dev/null
ls -1

# for 循环
echo "普通 for:"
for i in apple banana cherry; do
    echo "水果: ${i}"
done

echo "for /l:"
for i in $(seq 1 1 5); do
    SQUARE=$(( ${i} * ${i} ))
    echo "${i} 的平方是 ${SQUARE}"
done

echo "for /f 解析命令输出:"
while IFS=, read -r a b _; do
    b="${b%$'\r'}"
    [ -z "$a" ] && continue
    echo "第一列: ${a}, 第二列: ${b}"
done < <(echo "1,2,3,4")

echo "for /f 读取文件:"
while IFS= read -r l; do
    l="${l%$'\r'}"
    [ -z "$l" ] && continue
    echo "行: ${l}"
done < "test1.txt"

echo "for /r 遍历:"
# TODO: 手动检查: for /r . %%f in (*.txt) do echo 文件: %%f

echo "for /d 遍历目录:"
for d in */; do
    echo "目录: ${d}"
done

# 嵌套循环与延迟扩展
echo "嵌套循环:"
for i in $(seq 1 1 3); do
    for j in $(seq 1 1 3); do
        PRODUCT=$(( ${i} * ${j} ))
        echo "${PRODUCT}"
    done
done

# 子程序调用
label_SUBROUTINE "参数A" "参数B"
# TODO: 手动检查: echo 子程序返回后 ERRORLEVEL=%ERRORLEVEL%

if ! label_TEST_ERROR; then
    echo "错误处理: 捕获到错误"
else
    echo "错误处理: 无错误"
fi

# 系统信息查询
echo "系统信息:"
uname -a
echo "计算机名: $(hostname)"
echo "用户名: ${USER}"
echo "域: ${USERDOMAIN}"
echo "处理器架构: $(uname -m)"
echo "处理器数量: $(nproc)"
echo "系统目录: ${SystemRoot:-/}"
echo "临时目录: ${TMPDIR:-/tmp}"

# 注册表读取
echo "注册表读取:"

# PowerShell 调用
echo "PowerShell 调用:"
if ! pwsh -NoProfile -Command "Write-Output 'Hello from PowerShell'; Get-Date -Format 'yyyy-MM-dd HH:mm:ss'; Get-Process | Select-Object -First 3 Name, Id" 2>/dev/null; then
    echo "PowerShell 调用失败或未安装。"
fi

# WMIC 查询
echo "WMIC 查询:"

# 网络查询
echo "网络查询:"
ip addr | grep -i "IPv4 地址 IPv4 Address"
ping -c 1 127.0.0.1 && echo 本地回环可达 >/dev/null
# TODO: 复杂管道需手动重写
#  原命令: netstat -an | findstr "LISTENING" | findstr ":135" >nul && echo 端口135正在监听 || echo 端口135未监听
#  参考(中): ss -an | grep "LISTENING" | grep ":135" >nul && echo 端口135正在监听 || echo 端口135未监听
#  差异: 列名与列顺序不同；findstr 与 grep 的正则语法存在差异（/r 在 grep 中为默认行为）

# 服务与任务查询
echo "服务查询:"
# TODO: 复杂管道需手动重写
#  原命令: sc query wuauserv 2>nul | findstr "STATE"
#  参考(中): systemctl is-active wuauserv 2>/dev/null | grep "STATE"
#  差异: sc 输出 STATE : 4 RUNNING 等文本，systemctl 输出 active/inactive；findstr 与 grep 的正则语法存在差异（/r 在 grep 中为默认行为）
echo "任务查询:"
# TODO: 复杂管道需手动重写
#  原命令: tasklist /fi "imagename eq explorer.exe" 2>nul | findstr /i "explorer.exe"
#  参考(中): ps aux /fi "imagename eq explorer.exe" 2>/dev/null | grep -i "explorer.exe"
#  差异: 列格式完全不同；/fi 等过滤条件需改写为 grep/ps 选项；findstr 与 grep 的正则语法存在差异（/r 在 grep 中为默认行为）

# 管道与重定向
echo "管道测试:"
# TODO: 手动检查: echo line1 & echo line2 & echo line3 | findstr "line2"
echo "重定向测试:"
{ echo "输出到文件"; } >redirect.txt
cat redirect.txt
echo "错误重定向:"
# TODO: 复杂管道需手动重写
#  原命令: dir nonexistent_file 2>&1 | findstr /i "找不到"
#  参考(中): ls nonexistent_file 2>&1 | grep -i "找不到"
#  差异: Windows dir 列格式与 ls 不同（/b→ls -1、/s→ls -R 已近似，请核对）；findstr 与 grep 的正则语法存在差异（/r 在 grep 中为默认行为）

# 特殊字符转义
echo "特殊字符: & | < > ^ %"
echo "百分号: %PATH%"
echo "感叹号: !"

# 环境变量操作
MY_VAR="Hello"
MY_VAR="${MY_VAR} World"
echo "MY_VAR=${MY_VAR}"
env | grep -E "^MY_VAR"
env | grep -E "^PATH"

# 使用 set /p 从文件读取
echo "从文件读取:"
read -rp "" FIRST_LINE <test1.txt || true
echo "第一行: ${FIRST_LINE}"

# 使用 choice 和 timeout
echo "等待 1 秒..."
sleep 1 >/dev/null
# TODO: 手动检查: choice /c YN /t 1 /d Y >/dev/null
# TODO: 手动检查: echo 选择完成，ERRORLEVEL=%ERRORLEVEL%

# 使用 pushd/popd
pushd "${SystemRoot:-/}"
echo "进入系统目录: $(pwd)"
popd
echo "返回: $(pwd)"

# 使用 certutil 计算哈希
echo "文件哈希:"
# TODO: 复杂管道需手动重写
#  原命令: certutil -hashfile test1.txt MD5 2>nul | findstr /v "hash CertUtil"
#  参考(高): md5sum test1.txt 2>/dev/null | grep -v "hash CertUtil"
#  差异: 输出无 CertUtil 头与指纹格式；findstr 与 grep 的正则语法存在差异（/r 在 grep 中为默认行为）

# 使用 findstr 正则
echo "正则查找:"
grep -F "^[0-9][0-9]*$" "numbers.txt"

# 使用 sort 和 more
echo "排序并显示:"
sort test1.txt | more +1

# 使用 fc 和 comp
echo "文件比较:"
diff test1.txt test2.txt  && echo 相同 || echo 不同 >/dev/null
cmp test1.txt test2.txt  && echo 相同 || echo 不同 >/dev/null

# 使用 xcopy 和 robocopy
echo "xcopy 测试:"
cp -r "test1.txt" "test3.txt" >/dev/null
if [ -e "test3.txt" ]; then
    echo "xcopy 成功"
fi
echo "robocopy 测试:"
if ! rsync -a . . test1.txt /NJH /NJS /NDL /NC /NS >/dev/null 2>&1; then
    echo "robocopy 返回非零"
else
    echo "robocopy 成功"
fi

# 使用 wmic 进程查询
echo "进程查询:"

# 使用 PowerShell 复杂管道
echo "PowerShell 复杂管道:"
pwsh -NoProfile -Command "Get-ChildItem -Path . -Filter *.txt | Where-Object { $_.Length -gt 0 } | Select-Object Name, Length | ConvertTo-Json" 2>/dev/null

# 使用 .NET 调用
echo ".NET 调用:"
pwsh -NoProfile -Command "[System.Environment]::OSVersion.VersionString" 2>/dev/null
pwsh -NoProfile -Command "[System.DateTime]::Now.ToString('yyyy-MM-dd')" 2>/dev/null

# 注册表更多
echo "注册表更多:"

# 使用 goto 和标签
echo "跳转测试:"
# TODO: 手动检查: goto :SKIP
echo "这行不会执行"
