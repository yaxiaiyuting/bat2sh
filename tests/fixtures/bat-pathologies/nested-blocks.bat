@echo off
setlocal
set MODE=full
if "%MODE%"=="full" (
    echo 完整模式
    for %%i in (a b c) do (
        if exist "%%i.txt" (
            echo 找到 %%i
        ) else (
            echo 缺少 %%i
        )
    )
) else (
    echo 快速模式
)
endlocal
