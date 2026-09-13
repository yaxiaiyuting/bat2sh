@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Complex BAT Test Script
color 0A

REM ============================================================
REM 复杂批处理测试脚本 - 用于测试 bat2sh 转换器
REM ============================================================

set "SCRIPT_NAME=%~nx0"
set "SCRIPT_DIR=%~dp0"
set "LOG_FILE=%TEMP%\complex_bat_test_%RANDOM%.log"
set "WORK_DIR=%TEMP%\complex_bat_test_%RANDOM%"

echo [%DATE% %TIME%] 开始执行 %SCRIPT_NAME% > "%LOG_FILE%"
echo 脚本目录: %SCRIPT_DIR% >> "%LOG_FILE%"

REM 参数处理
set "ARG1=%~1"
set "ARG2=%~2"
set "ALL_ARGS=%*"
if "%~1"=="" (
    echo 未提供参数，使用默认值。
    set "ARG1=default1"
    set "ARG2=default2"
) else (
    echo 参数1: %ARG1%
    echo 参数2: %ARG2%
)
echo 所有参数: %ALL_ARGS%

REM 字符串操作
set "STR=Hello, World! This is a complex BAT script."
echo 原始字符串: %STR%
echo 子字符串(0,5): %STR:~0,5%
echo 子字符串(7): %STR:~7%
echo 替换 World 为 BAT: %STR:World=BAT%
echo 删除逗号前内容: %STR:*:=%
set "STR2=abcdef"
echo 从右取3个: %STR2:~-3%
echo 取第2到第4: %STR2:~1,3%

REM 算术运算
set /a NUM1=10
set /a NUM2=3
set /a SUM=%NUM1% + %NUM2%
set /a MOD=%NUM1% %% %NUM2%
echo 算术: %NUM1% + %NUM2% = %SUM%, %NUM1% %% %NUM2% = %MOD%
set /a RAND_NUM=%RANDOM% %% 100
echo 随机数: %RAND_NUM%
set /a "COMPLEX=(10+20)*3/2-5"
echo 复杂算术: %COMPLEX%
set /a "BITWISE=5 & 3"
echo 位运算: %BITWISE%
set /a "SHIFT=1 << 3"
echo 左移: %SHIFT%

REM 延迟扩展与变量嵌套
set "VAR_NAME=DYNAMIC"
set "DYNAMIC=这是动态变量"
echo 延迟扩展: !%VAR_NAME%!
call set "INDIRECT=%%%VAR_NAME%%%"
echo 间接引用: %INDIRECT%

set "A=B"
set "B=Value"
call set "RESULT=%%%A%%%"
echo 嵌套变量: %RESULT%
set "RESULT2=!%A%!"
echo 延迟嵌套: %RESULT2%

REM 创建临时工作目录
if not exist "%WORK_DIR%" mkdir "%WORK_DIR%"
pushd "%WORK_DIR%"
echo 当前工作目录: %CD%

REM 文件操作
echo 这是第一行 > test1.txt
echo 这是第二行 >> test1.txt
echo 第三行包含数字 12345 >> test1.txt
type test1.txt
copy test1.txt test2.txt >nul
findstr /r "[0-9][0-9]*" test1.txt > numbers.txt
sort /r test1.txt > sorted.txt
fc test1.txt test2.txt >nul && echo 文件相同 || echo 文件不同
attrib test1.txt
dir /b

REM for 循环
echo 普通 for:
for %%i in (apple banana cherry) do echo 水果: %%i

echo for /l:
for /l %%i in (1,1,5) do (
    set /a SQUARE=%%i * %%i
    echo %%i 的平方是 !SQUARE!
)

echo for /f 解析命令输出:
for /f "tokens=1,2 delims=," %%a in ('echo 1,2,3,4') do (
    echo 第一列: %%a, 第二列: %%b
)

echo for /f 读取文件:
for /f "usebackq tokens=*" %%l in ("test1.txt") do (
    echo 行: %%l
)

echo for /r 遍历:
for /r . %%f in (*.txt) do echo 文件: %%f

echo for /d 遍历目录:
for /d %%d in (*) do echo 目录: %%d

REM 嵌套循环与延迟扩展
echo 嵌套循环:
for /l %%i in (1,1,3) do (
    for /l %%j in (1,1,3) do (
        set /a PRODUCT=%%i * %%j
        echo !PRODUCT! 
    )
)

REM 子程序调用
call :SUBROUTINE "参数A" "参数B"
echo 子程序返回后 ERRORLEVEL=%ERRORLEVEL%

call :TEST_ERROR
if errorlevel 1 (
    echo 错误处理: 捕获到错误
) else (
    echo 错误处理: 无错误
)

REM 系统信息查询
echo 系统信息:
ver
echo 计算机名: %COMPUTERNAME%
echo 用户名: %USERNAME%
echo 域: %USERDOMAIN%
echo 处理器架构: %PROCESSOR_ARCHITECTURE%
echo 处理器数量: %NUMBER_OF_PROCESSORS%
echo 系统目录: %SystemRoot%
echo 临时目录: %TEMP%

REM 注册表读取
echo 注册表读取:
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v ProductName 2>nul
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer" /v ShellState 2>nul

REM PowerShell 调用
echo PowerShell 调用:
powershell -NoProfile -Command "Write-Output 'Hello from PowerShell'; Get-Date -Format 'yyyy-MM-dd HH:mm:ss'; Get-Process | Select-Object -First 3 Name, Id" 2>nul
if errorlevel 1 echo PowerShell 调用失败或未安装。

REM WMIC 查询
echo WMIC 查询:
wmic os get Caption,Version /value 2>nul
wmic cpu get Name /value 2>nul
wmic logicaldisk get DeviceID,Size,FreeSpace /value 2>nul

REM 网络查询
echo 网络查询:
ipconfig | findstr /i "IPv4 地址 IPv4 Address"
ping -n 1 127.0.0.1 >nul && echo 本地回环可达
netstat -an | findstr "LISTENING" | findstr ":135" >nul && echo 端口135正在监听 || echo 端口135未监听

REM 服务与任务查询
echo 服务查询:
sc query wuauserv 2>nul | findstr "STATE"
echo 任务查询:
tasklist /fi "imagename eq explorer.exe" 2>nul | findstr /i "explorer.exe"

REM 管道与重定向
echo 管道测试:
echo line1 & echo line2 & echo line3 | findstr "line2"
echo 重定向测试:
(echo 输出到文件) > redirect.txt
type redirect.txt
echo 错误重定向:
dir nonexistent_file 2>&1 | findstr /i "找不到"

REM 特殊字符转义
echo 特殊字符: ^& ^| ^< ^> ^^ %% 
echo 百分号: %%PATH%%
echo 感叹号: ^!

REM 环境变量操作
set "MY_VAR=Hello"
set "MY_VAR=%MY_VAR% World"
echo MY_VAR=%MY_VAR%
set MY_VAR
set PATH

REM 使用 set /p 从文件读取
echo 从文件读取:
set /p FIRST_LINE=<test1.txt
echo 第一行: %FIRST_LINE%

REM 使用 choice 和 timeout
echo 等待 1 秒...
timeout /t 1 /nobreak >nul
choice /c YN /t 1 /d Y >nul
echo 选择完成，ERRORLEVEL=%ERRORLEVEL%

REM 使用 pushd/popd
pushd "%SystemRoot%"
echo 进入系统目录: %CD%
popd
echo 返回: %CD%

REM 使用 certutil 计算哈希
echo 文件哈希:
certutil -hashfile test1.txt MD5 2>nul | findstr /v "hash CertUtil"

REM 使用 findstr 正则
echo 正则查找:
findstr /r /c:"^[0-9][0-9]*$" numbers.txt

REM 使用 sort 和 more
echo 排序并显示:
sort test1.txt | more +1

REM 使用 fc 和 comp
echo 文件比较:
fc test1.txt test2.txt >nul && echo 相同 || echo 不同
comp test1.txt test2.txt >nul && echo 相同 || echo 不同

REM 使用 xcopy 和 robocopy
echo xcopy 测试:
xcopy test1.txt test3.txt /Y >nul
if exist test3.txt echo xcopy 成功
echo robocopy 测试:
robocopy . . test1.txt /NJH /NJS /NDL /NC /NS >nul 2>&1
if errorlevel 1 (echo robocopy 返回非零) else (echo robocopy 成功)

REM 使用 wmic 进程查询
echo 进程查询:
wmic process where "name='explorer.exe'" get ProcessId,CommandLine /value 2>nul

REM 使用 PowerShell 复杂管道
echo PowerShell 复杂管道:
powershell -NoProfile -Command "Get-ChildItem -Path . -Filter *.txt | Where-Object { $_.Length -gt 0 } | Select-Object Name, Length | ConvertTo-Json" 2>nul

REM 使用 .NET 调用
echo .NET 调用:
powershell -NoProfile -Command "[System.Environment]::OSVersion.VersionString" 2>nul
powershell -NoProfile -Command "[System.DateTime]::Now.ToString('yyyy-MM-dd')" 2>nul

REM 注册表更多
echo 注册表更多:
reg query "HKLM\HARDWARE\DESCRIPTION\System\BIOS" /v SystemManufacturer 2>nul
reg query "HKCU\Control Panel\Desktop" /v Wallpaper 2>nul

REM 使用 goto 和标签
echo 跳转测试:
goto :SKIP
echo 这行不会执行
:SKIP
echo 跳过了。

REM 使用 goto :eof 在子程序中
call :RETURN_EOF
echo 从 :eof 返回

REM 使用 exit /b
call :EXIT_B
echo 从 exit /b 返回，ERRORLEVEL=%ERRORLEVEL%

REM 使用 shift
call :SHIFT_TEST a b c d
echo shift 测试完成

REM 使用 %* 和 %~dp0
call :SHOW_ARGS one two three

REM 使用 for 遍历参数
echo 遍历参数:
for %%a in (%*) do echo 参数: %%a

REM 使用 if 各种形式
if defined MY_VAR echo MY_VAR 已定义
if not defined NOT_DEFINED echo NOT_DEFINED 未定义
if exist test1.txt echo test1.txt 存在
if not exist nonexistent.txt echo nonexistent.txt 不存在
if "%MY_VAR%"=="Hello World" echo 字符串相等
if /i "HELLO"=="hello" echo 忽略大小写相等
if %NUM1% gtr %NUM2% echo NUM1 大于 NUM2
if %NUM1% lss %NUM2% (echo NUM1 小于 NUM2) else (echo NUM1 不小于 NUM2)
if errorlevel 0 echo ERRORLEVEL >= 0
if %ERRORLEVEL% equ 0 echo ERRORLEVEL 等于 0
if cmdextversion 2 echo 命令扩展版本 >= 2

REM 使用 assoc 和 ftype
echo 文件关联:
assoc .txt 2>nul
ftype txtfile 2>nul

REM 使用 vol
echo 卷信息:
vol C: 2>nul

REM 使用 systeminfo
echo 系统信息摘要:
systeminfo | findstr /i "OS 名称 OS Name 版本 Version 系统类型 System Type" 2>nul

REM 使用 driverquery
echo 驱动查询:
driverquery | findstr /i "Running" | findstr /i "True" 2>nul | findstr /n "^" | findstr "^[1-5]:"

REM 使用 tasklist 更多
echo 任务列表:
tasklist /svc | findstr /i "svchost" | findstr /n "^" | findstr "^[1-5]:"

REM 使用 net user 和 net start
echo 本地用户:
net user 2>nul | findstr /v "命令成功完成" | findstr /n "^" | findstr "^[1-5]:"
echo 已启动服务:
net start 2>nul | findstr /n "^" | findstr "^[1-5]:"

REM 使用 whoami
echo 当前用户:
whoami /all 2>nul | findstr /i "用户名 User Name 组 Group" | findstr /n "^" | findstr "^[1-5]:"

REM 使用 query user
echo 登录用户:
query user 2>nul

REM 使用 icacls
echo 文件权限:
icacls test1.txt 2>nul

REM 使用 %~dp0 和 %~nx0
echo 脚本完整路径: %~f0
echo 脚本驱动器: %~d0
echo 脚本路径: %~p0
echo 脚本名称: %~n0
echo 脚本扩展名: %~x0
echo 脚本短名: %~s0
echo 脚本属性: %~a0
echo 脚本时间: %~t0
echo 脚本大小: %~z0

REM 使用 %~$PATH:1 搜索路径
echo PATH 中查找 notepad: %~$PATH:notepad

REM 使用 %CD% 和 %=C:%
echo 当前目录: %CD%
echo 当前目录扩展: %=C:%

REM 使用 %RANDOM% 和 %ERRORLEVEL%
echo 随机数: %RANDOM%
echo 错误级别: %ERRORLEVEL%

REM 使用 %DATE% 和 %TIME% 解析
for /f "tokens=1-3 delims=/- " %%a in ("%DATE%") do (
    set "YEAR=%%c"
    set "MONTH=%%a"
    set "DAY=%%b"
)
echo 解析日期: 年=%YEAR% 月=%MONTH% 日=%DAY%
for /f "tokens=1-3 delims=:." %%a in ("%TIME%") do (
    set "HOUR=%%a"
    set "MIN=%%b"
    set "SEC=%%c"
)
echo 解析时间: 时=%HOUR% 分=%MIN% 秒=%SEC%

REM 使用 if 嵌套
if exist test1.txt (
    if exist test2.txt (
        echo 两个文件都存在
    ) else (
        echo test1 存在但 test2 不存在
    )
) else (
    echo test1 不存在
)

REM 使用括号块和延迟扩展
set "COUNTER=0"
for /l %%i in (1,1,3) do (
    set /a COUNTER+=1
    if !COUNTER! equ 2 (
        echo 计数器为 2
    ) else (
        echo 计数器为 !COUNTER!
    )
)

REM 使用 & 和 && 和 ||
echo 命令分隔: echo A & echo B
echo 条件执行: (echo C) && (echo D)
echo 条件执行: (exit /b 1) || (echo E)

REM 使用 | 管道和 > 重定向组合
echo 管道重定向:
echo hello | findstr "hello" > pipe.txt
type pipe.txt

REM 使用 2>&1 合并错误
echo 错误合并: dir nonexistent 2>&1 | findstr /i "找不到"

REM 使用 >nul 2>&1 抑制输出
echo 抑制输出: dir >nul 2>&1

REM 使用 < 输入重定向
echo 输入重定向: findstr "第一行" < test1.txt

REM 使用 for /f 解析带引号的字符串
for /f "tokens=1-3 delims=," %%a in ("one,two,three") do echo %%a %%b %%c

REM 使用 for /f 解析命令输出并跳过行
for /f "skip=1 tokens=*" %%a in ('dir /b') do echo 文件: %%a

REM 使用 for /f 解析带 eol 的
for /f "eol=; tokens=*" %%a in (test1.txt) do echo 行: %%a

REM 使用 for /f 解析多行命令输出
for /f "tokens=*" %%a in ('echo line1^& echo line2^& echo line3') do echo 输出: %%a

REM 使用 for /f 解析 powershell 输出
for /f "tokens=*" %%a in ('powershell -NoProfile -Command "Write-Output 'PS line'"') do echo PS输出: %%a

REM 使用 for /f 解析 wmic 输出
for /f "tokens=2 delims==" %%a in ('wmic os get Caption /value 2^>nul ^| findstr "Caption"') do echo OS: %%a

REM 使用 for /f 解析注册表输出
for /f "tokens=3" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v ProductName 2^>nul ^| findstr "ProductName"') do echo 产品名称: %%a

REM 使用 for /f 解析 netstat
for /f "tokens=2" %%a in ('netstat -an ^| findstr "LISTENING" ^| findstr ":135"') do echo 端口135: %%a

REM 使用 for /f 解析 tasklist
for /f "tokens=1,2" %%a in ('tasklist /fi "imagename eq explorer.exe" ^| findstr /i "explorer"') do echo 进程: %%a PID: %%b

REM 使用 for /f 解析 sc query
for /f "tokens=1,2" %%a in ('sc query wuauserv ^| findstr "STATE"') do echo 服务状态: %%a %%b

REM 使用 for /f 解析 whoami
for /f "tokens=*" %%a in ('whoami') do echo 当前用户: %%a

REM 使用 for /f 解析 ipconfig
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do echo IP: %%a

REM 使用 for /f 解析 systeminfo
for /f "tokens=2 delims=:" %%a in ('systeminfo ^| findstr /i "OS Name"') do echo OS: %%a

REM 使用 for /f 解析 driverquery
for /f "tokens=1" %%a in ('driverquery ^| findstr /i "Running"') do echo 驱动: %%a

REM 使用 for /f 解析 net user
for /f "tokens=*" %%a in ('net user ^| findstr /v "命令成功完成"') do echo 用户: %%a

REM 使用 for /f 解析 net start
for /f "tokens=*" %%a in ('net start ^| findstr /v "命令成功完成"') do echo 服务: %%a

REM 使用 for /f 解析 query user
for /f "tokens=*" %%a in ('query user') do echo 登录: %%a

REM 使用 for /f 解析 icacls
for /f "tokens=*" %%a in ('icacls test1.txt') do echo 权限: %%a

REM 使用 for /f 解析 certutil
for /f "tokens=*" %%a in ('certutil -hashfile test1.txt MD5 ^| findstr /v "hash CertUtil"') do echo 哈希: %%a

REM 使用 for /f 解析 robocopy
for /f "tokens=*" %%a in ('robocopy . . test1.txt /NJH /NJS /NDL /NC /NS') do echo robocopy: %%a

REM 使用 for /f 解析 xcopy
for /f "tokens=*" %%a in ('xcopy test1.txt test4.txt /Y') do echo xcopy: %%a

REM 使用 for /f 解析 assoc
for /f "tokens=*" %%a in ('assoc .txt') do echo 关联: %%a

REM 使用 for /f 解析 ftype
for /f "tokens=*" %%a in ('ftype txtfile') do echo 类型: %%a

REM 使用 for /f 解析 vol
for /f "tokens=*" %%a in ('vol C:') do echo 卷: %%a

REM 使用 for /f 解析 chcp
for /f "tokens=*" %%a in ('chcp') do echo 代码页: %%a

REM 使用 for /f 解析 set
for /f "tokens=1* delims==" %%a in ('set') do (
    if "%%a"=="PATH" echo PATH=%%b
    if "%%a"=="TEMP" echo TEMP=%%b
    if "%%a"=="USERNAME" echo USERNAME=%%b
)

REM 使用 for /f 解析 cd
for /f "tokens=*" %%a in ('cd') do echo 当前目录: %%a

REM 使用 for /f 解析 date
for /f "tokens=*" %%a in ('date /t') do echo 日期: %%a

REM 使用 for /f 解析 time
for /f "tokens=*" %%a in ('time /t') do echo 时间: %%a

REM 使用 for /f 解析 title
for /f "tokens=*" %%a in ('title') do echo 标题: %%a

REM 使用 for /f 解析 color
for /f "tokens=*" %%a in ('color') do echo 颜色: %%a

REM 使用 for /f 解析 mode
for /f "tokens=*" %%a in ('mode con') do echo 模式: %%a

REM 使用 for /f 解析 ver
for /f "tokens=*" %%a in ('ver') do echo 版本: %%a

REM 使用 for /f 解析 echo
for /f "tokens=*" %%a in ('echo hello') do echo 回显: %%a

REM 使用 for /f 解析 rem
for /f "tokens=*" %%a in ('rem comment') do echo 注释: %%a

REM 结束部分
echo.
echo ============================================================
echo 测试完成。
echo 日志文件: %LOG_FILE%
echo 工作目录: %WORK_DIR%
echo ============================================================

REM 清理临时文件
popd
rd /s /q "%WORK_DIR%" 2>nul
del "%LOG_FILE%" 2>nul

endlocal
exit /b 0

REM ============================================================
REM 子程序定义
REM ============================================================

:SUBROUTINE
setlocal
echo 子程序: 参数1=%~1, 参数2=%~2
set "LOCAL_VAR=子程序局部变量"
echo 子程序局部变量: %LOCAL_VAR%
endlocal
exit /b 0

:TEST_ERROR
setlocal
echo 测试错误处理...
exit /b 1

:RETURN_EOF
echo 这是 :RETURN_EOF 子程序
goto :eof

:EXIT_B
echo 这是 :EXIT_B 子程序
exit /b 5

:SHIFT_TEST
echo shift 测试开始，参数: %*
shift
echo 移动后参数: %*
shift
echo 再次移动后参数: %*
exit /b 0

:SHOW_ARGS
echo 子程序参数: %*
echo 第一个参数: %~1
echo 所有参数: %*
exit /b 0