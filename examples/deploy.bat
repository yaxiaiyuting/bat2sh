@echo off
setlocal enabledelayedexpansion
set "SRC=.\build\release"
set "DST=.\deploy"
if not exist "%DST%" mkdir "%DST%"
call :copy_files
if errorlevel 1 exit /b 1
call :summary
goto :eof

:copy_files
for %%F in ("%SRC%\*.exe" "%SRC%\*.dll") do (
    echo 复制 %%~nxF
    copy /y "%%F" "%DST%\"
)
goto :eof

:summary
echo 部署目录内容:
dir /b "%DST%"
echo 部署完成
pause
goto :eof
