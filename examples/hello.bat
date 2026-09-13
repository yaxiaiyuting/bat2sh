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
