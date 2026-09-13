@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
title Extreme BAT Stress Test - v1.2.0 Killer

REM ============================================================
REM 模块 1: for /f 地狱 —— 各种选项组合、嵌套、边界
REM ============================================================

echo [模块1] for /f 地狱

REM 1.1 tokens 带星号（tokens=1,*）
for /f "tokens=1,* delims=:" %%a in ("key:value:with:colons") do (
    echo key=%%a value=%%b
)

REM 1.2 delims 包含空格和制表符
for /f "tokens=1,2 delims=	 " %%a in ("col1	col2 col3") do echo a=%%a b=%%b

REM 1.3 eol 与 delims 同时使用
for /f "eol=# delims=, tokens=1,2" %%a in ("#comment,skip" "real,data") do echo %%a=%%b

REM 1.4 skip 大数值 + tokens=*
for /f "skip=100 tokens=*" %%a in ('dir /b') do echo %%a

REM 1.5 usebackq 与单引号混用
for /f "usebackq tokens=*" %%a in (`echo backquote`) do echo %%a
for /f "usebackq tokens=*" %%a in ('single quote file.txt') do echo %%a
for /f "usebackq tokens=*" %%a in ("double quote file.txt") do echo %%a

REM 1.6 嵌套 for /f，内外都用 %%a
for /f "tokens=1" %%a in ('echo outer') do (
    for /f "tokens=1" %%a in ('echo inner') do (
        echo 冲突: %%a
    )
)

REM 1.7 for /f 解析带引号的 CSV
for /f "tokens=1-4 delims=," %%a in ("a,b,c,d") do echo %%a %%b %%c %%d

REM 1.8 for /f 解析空行
for /f "tokens=*" %%a in ('echo. & echo line2') do echo [%%a]

REM 1.9 for /f 中的管道嵌套
for /f "tokens=*" %%a in ('dir /b ^| findstr ".bat" ^| findstr /v "test"') do echo %%a

REM 1.10 for /f 解析多行命令输出
for /f "tokens=*" %%a in ('echo line1^& echo line2^& echo line3') do echo %%a

REM ============================================================
REM 模块 2: 延迟扩展与变量嵌套地狱
REM ============================================================

echo [模块2] 变量地狱

set "A=B"
set "B=C"
set "C=FinalValue"
set "D=!C!"
set "E=%%C%%"

REM 2.1 三重间接引用
call set "TRIPLE=%%%A%%%"
call call set "QUAD=%%%%%A%%%%%"

REM 2.2 延迟扩展中的变量名
set "VAR_NAME=DYNAMIC"
set "DYNAMIC=延迟值"
echo !%VAR_NAME%!
echo !%VAR_NAME%!

REM 2.3 变量名包含空格
set "MY VAR=with space"
echo %MY VAR%

REM 2.4 变量名包含特殊字符
set "VAR-NAME=dash"
set "VAR.NAME=dot"
echo %VAR-NAME% %VAR.NAME%

REM 2.5 未定义变量直接展开
echo 未定义: [%UNDEFINED_VAR%]
echo 延迟未定义: [!UNDEFINED_VAR!]

REM 2.6 空变量与空字符串
set "EMPTY="
if "%EMPTY%"=="" echo EMPTY 是空
if defined EMPTY (echo 已定义) else (echo 未定义)

REM 2.7 字符串操作极限
set "STR=abcdefghij"
echo 前3: %STR:~0,3%
echo 后3: %STR:~-3%
echo 从2到5: %STR:~2,4%
echo 替换: %STR:abc=XYZ%
echo 删除: %STR:def=%
echo 带星替换: %STR:*def=%
echo 从右替换: %STR:*c=%

REM 2.8 for 变量在循环外使用
for %%i in (a b c) do echo %%i
echo 循环外: %%i

REM ============================================================
REM 模块 3: 特殊字符与转义地狱
REM ============================================================

echo [模块3] 特殊字符地狱

REM 3.1 所有特殊字符
echo 特殊: ^& ^| ^< ^> ^^ ^( ^) ^! ^" 
echo 百分号: %% %%PATH%% %%%%
echo 感叹号: ^! ! 
echo 插入符: ^^ ^^^

REM 3.2 在括号内输出特殊字符
(
    echo 括号内: ^& ^|
    echo 括号内: ^< ^>
    echo 括号内: ^^
)

REM 3.3 变量内容包含特殊字符
set "SPECIAL=a&b|c<d>e^f"
echo %SPECIAL%
echo !SPECIAL!

REM 3.4 字符串中的引号
echo "双引号"
echo '单引号'
echo `反引号`
echo "混合'引号`测试"

REM 3.5 反斜杠与路径
echo C:\Windows\System32
echo \\server\share\file
echo C:\\double\\backslash

REM 3.6 重定向符作为字面量
echo 输出到文件 ^> test.txt
echo 从文件读取 ^< test.txt
echo 管道符 ^| 不是管道

REM ============================================================
REM 模块 4: goto 与标签地狱
REM ============================================================

echo [模块4] goto 地狱

REM 4.1 向前跳转
goto :FORWARD
echo 这行不会执行
:FORWARD
echo 向前跳转成功

REM 4.2 向后跳转（循环）
set /a COUNT=0
:LOOP_START
set /a COUNT+=1
if %COUNT% lss 3 goto :LOOP_START
echo 循环完成: %COUNT%

REM 4.3 跳入 if 块内部（危险）
if 1==1 (
    goto :INSIDE_IF
    echo 这行不会执行
    :INSIDE_IF
    echo 跳入 if 块
)

REM 4.4 跳入 for 循环内部（非常危险）
for %%i in (a b c) do (
    goto :INSIDE_FOR
    :INSIDE_FOR
    echo 跳入 for: %%i
)

REM 4.5 goto :eof 在子程序外
call :TEST_EOF
echo 从 :eof 返回

REM 4.6 goto 带标签变量
set "LABEL=DYNAMIC_LABEL"
goto :%LABEL%
echo 这行不会执行
:DYNAMIC_LABEL
echo 动态标签跳转成功

REM 4.7 goto 到不存在的标签
goto :NONEXISTENT_LABEL
echo 这行不会执行

REM ============================================================
REM 模块 5: 管道与重定向地狱
REM ============================================================

echo [模块5] 管道地狱

REM 5.1 五级管道
echo a b c d e | findstr "a" | findstr "b" | findstr "c" | findstr "d" | findstr "e"

REM 5.2 管道与重定向混合
dir 2>&1 | findstr /i "找不到" > err.txt

REM 5.3 管道到 for /f
for /f "tokens=*" %%a in ('dir /b ^| findstr ".txt"') do echo %%a

REM 5.4 命令连接符 & 和 &&
echo A & echo B & echo C
echo D && echo E || echo F
(echo G) && (echo H)

REM 5.5 命令连接符在 for 中
for %%i in (1 2 3) do echo %%i & echo 第二个

REM 5.6 重定向到 NUL
echo 丢弃 >nul
echo 丢弃 2>nul
echo 丢弃 >nul 2>&1
echo 丢弃 2>&1 >nul

REM 5.7 追加与覆盖
echo 第一次 > out.txt
echo 第二次 >> out.txt
type out.txt

REM 5.8 输入重定向
findstr "test" < out.txt
sort < out.txt

REM 5.9 管道中带变量的命令
set "CMD=dir"
%CMD% | findstr ".txt"

REM 5.10 管道到 more 和 sort
type out.txt | sort | more

REM ============================================================
REM 模块 6: if 与 errorlevel 地狱
REM ============================================================

echo [模块6] 条件判断地狱

REM 6.1 if 的所有比较运算符
set /a N1=10
set /a N2=20
if %N1% equ 10 echo equ
if %N1% neq 20 echo neq
if %N1% lss %N2% echo lss
if %N1% leq 10 echo leq
if %N2% gtr %N1% echo gtr
if %N2% geq 20 echo geq

REM 6.2 if /i 忽略大小写
if /i "HELLO"=="hello" echo 忽略大小写
if /i not "HELLO"=="world" echo 取反

REM 6.3 if exist 各种形式
if exist out.txt echo 文件存在
if not exist nonexistent.txt echo 文件不存在
if exist *.txt echo 有 txt 文件
if exist C:\Windows\System32\cmd.exe echo 系统文件存在
if exist "C:\Program Files" echo 目录存在（带空格）

REM 6.4 if defined
set "DEFINED_VAR=1"
if defined DEFINED_VAR echo 已定义
if not defined UNDEFINED_VAR echo 未定义

REM 6.5 errorlevel 三种写法
cmd /c exit 1
if errorlevel 1 echo errorlevel >= 1
if %ERRORLEVEL% equ 1 echo ERRORLEVEL == 1
if !ERRORLEVEL! neq 0 echo 延迟 errorlevel != 0

REM 6.6 errorlevel 与 && || 混用
cmd /c exit 0 && echo 成功 || echo 失败
cmd /c exit 1 && echo 成功 || echo 失败

REM 6.7 if 嵌套多层
if 1==1 (
    if 2==2 (
        if 3==3 (
            echo 三层嵌套
        )
    )
)

REM 6.8 if 与 goto 混用
if %N1% lss %N2% (
    goto :IF_GOTO
) else (
    echo 不跳转
)
:IF_GOTO
echo 从 if 跳转

REM 6.9 cmdextversion
if cmdextversion 2 echo 扩展版本 >= 2
if cmdextversion 1 echo 扩展版本 >= 1

REM 6.10 if 比较带引号与不带引号
if "abc"=="abc" echo 带引号
if abc==abc echo 不带引号（可能出错）
if "%UNDEFINED%"=="" echo 未定义变量比较

REM ============================================================
REM 模块 7: set /a 算术地狱
REM ============================================================

echo [模块7] 算术地狱

REM 7.1 基本运算
set /a R1=10+20
set /a R2=10-20
set /a R3=10*20
set /a R4=20/3
set /a R5=20%%3

REM 7.2 括号与优先级
set /a R6=(10+20)*3
set /a R7=10+20*3
set /a R8=((10+20)*3-5)/2

REM 7.3 位运算
set /a R9=5^&3
set /a R10=5^|3
set /a R11=5^^3
set /a R12=~5
set /a R13=5^<^<2
set /a R14=20^>^>2

REM 7.4 十六进制与八进制
set /a R15=0x1F
set /a R16=010

REM 7.5 变量参与运算
set /a N1=10
set /a N2=20
set /a R17=N1+N2
set /a R18=%N1%+%N2%
set /a R19=!N1!+!N2!

REM 7.6 复合赋值
set /a N1+=5
set /a N1-=3
set /a N1*=2
set /a N1/=4
set /a N1%%=3

REM 7.7 带引号的表达式
set /a "R20=10+20"
set /a "R21=(10+20)*3"
set /a "R22=10 + 20 * 3"

REM 7.8 逗号分隔多个赋值
set /a X=1, Y=2, Z=3
echo X=%X% Y=%Y% Z=%Z%

REM 7.9 除以零（会报错）
set /a R23=10/0

REM 7.10 溢出
set /a R24=2147483647+1

REM ============================================================
REM 模块 8: 子程序与调用地狱
REM ============================================================

echo [模块8] 子程序地狱

REM 8.1 基本调用
call :SUB1
call :SUB1 arg1
call :SUB1 arg1 arg2

REM 8.2 递归调用
call :RECURSE 5

REM 8.3 子程序中修改全局变量
set "GLOBAL=before"
call :MODIFY_GLOBAL
echo GLOBAL=%GLOBAL%

REM 8.4 子程序中使用 setlocal
call :WITH_SETLOCAL
echo 外部: LOCAL_VAR=%LOCAL_VAR%

REM 8.5 子程序返回不同 errorlevel
call :RETURN_1
echo 返回码: %ERRORLEVEL%
call :RETURN_5
echo 返回码: %ERRORLEVEL%

REM 8.6 call 外部脚本
echo @echo off > external.bat
echo echo 来自外部脚本 >> external.bat
call external.bat

REM 8.7 call 带标签
call :LABEL_SUB
echo 返回

REM 8.8 子程序中的 goto :eof
call :GOTO_EOF

REM 8.9 子程序中 shift
call :SHIFT_SUB a b c d e

REM 8.10 子程序中 %* 和 %1-%9
call :ARGS_SUB 1 2 3 4 5 6 7 8 9 10 11

REM ============================================================
REM 模块 9: 参数修饰符极限
REM ============================================================

echo [模块9] 参数修饰符

echo 脚本路径: %~f0
echo 驱动器: %~d0
echo 路径: %~p0
echo 文件名: %~n0
echo 扩展名: %~x0
echo 短名: %~s0
echo 属性: %~a0
echo 时间: %~t0
echo 大小: %~z0
echo 组合: %~dp0
echo 组合: %~nx0
echo 组合: %~dpnx0

echo 参数1完整: %~f1
echo 参数1路径: %~dp1
echo 参数1文件名: %~n1
echo 参数1扩展: %~x1

echo PATH中查找: %~$PATH:notepad

REM ============================================================
REM 模块 10: 编码与 Unicode 地狱
REM ============================================================

echo [模块10] 编码地狱

REM 10.1 中文
echo 中文测试：你好世界
set "中文变量=中文值"
echo %中文变量%

REM 10.2 Emoji
echo Emoji: 😀 🎉 🚀

REM 10.3 特殊 Unicode
echo Unicode: ñ é ü ö ä ß
echo 日文: こんにちは
echo 韩文: 안녕하세요
echo 俄文: Привет

REM 10.4 混合编码
echo 中英混合 mixed 中文 English 英文

REM 10.5 编码转换
chcp 65001 >nul
echo UTF-8 模式
chcp 936 >nul
echo GBK 模式

REM ============================================================
REM 模块 11: 边界与异常
REM ============================================================

echo [模块11] 边界地狱

REM 11.1 空行和空命令
echo.

REM 11.2 只有注释的行
rem 这是注释
REM 这也是注释
:: 双冒号注释（在括号外）
echo 注释测试

REM 11.3 超长行
echo 这是一个非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长的行

REM 11.4 超长变量
set "LONGVAR=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
echo %LONGVAR%

REM 11.5 空文件操作
type nul > empty.txt
for %%f in (empty.txt) do echo 空文件大小: %%~zf

REM 11.6 路径带空格
set "PATH_WITH_SPACE=C:\Program Files\Test"
echo %PATH_WITH_SPACE%
if exist "%PATH_WITH_SPACE%" echo 存在

REM 11.7 路径带中文
set "中文路径=C:\测试目录"
echo %中文路径%

REM 11.8 未定义标签
goto :UNDEFINED_LABEL_XYZ

REM 11.9 括号不匹配（语法错误）
if 1==1 (
    echo 缺少右括号

REM 11.10 引号不匹配（语法错误）
echo "未闭合的引号

REM ============================================================
REM 子程序定义
REM ============================================================

:SUB1
echo 子程序1，参数: %1 %2
exit /b 0

:RECURSE
setlocal
set /a N=%1
if %N% leq 0 (
    endlocal
    exit /b 0
)
echo 递归: %N%
call :RECURSE %N%-1
endlocal
exit /b 0

:MODIFY_GLOBAL
set "GLOBAL=after"
exit /b 0

:WITH_SETLOCAL
setlocal
set "LOCAL_VAR=local"
echo 内部: %LOCAL_VAR%
endlocal
exit /b 0

:RETURN_1
exit /b 1

:RETURN_5
exit /b 5

:LABEL_SUB
echo 标签子程序
exit /b 0

:GOTO_EOF
echo goto :eof 测试
goto :eof

:SHIFT_SUB
echo 参数: %*
shift
echo 移动后: %*
shift
echo 再移动: %*
exit /b 0

:ARGS_SUB
echo 参数: %1 %2 %3 %4 %5 %6 %7 %8 %9
echo 第10个: %10
echo 全部: %*
exit /b 0

REM ============================================================
REM 结束
REM ============================================================

echo.
echo ============================================================
echo 极限测试完成
echo ============================================================

endlocal
exit /b 0