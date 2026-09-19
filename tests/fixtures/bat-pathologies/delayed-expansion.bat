@echo off
rem 原创测试夹具：延迟展开 !VAR!（对应 backlog P-2）
setlocal enabledelayedexpansion
set 计数=0
for %%f in (*.txt) do (
    set /a 计数+=1
    echo 第 !计数! 个: %%f
)
echo 合计 !计数!
endlocal
