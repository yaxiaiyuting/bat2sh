@echo off
setlocal
call :greet world
if errorlevel 1 goto :fail
call :greet again
goto :done

:greet
echo 你好, %1
exit /b 0

:fail
echo 失败
exit /b 1

:done
echo 结束
endlocal
