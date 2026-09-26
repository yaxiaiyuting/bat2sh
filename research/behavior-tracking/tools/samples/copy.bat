@echo off
rem Sample A (copy-class): create -> copy -> read.
rem Also drops a probe OUTSIDE C:\poc to verify WHOLE-DISK CoW reversion,
rem not merely "the harness's own directory got cleaned".
setlocal
set "WORK=%~dp0work"
if not exist "%WORK%" mkdir "%WORK%"
if not exist "C:\iso-probe" mkdir "C:\iso-probe"
echo source-alpha>"%WORK%\a.txt"
copy /y "%WORK%\a.txt" "%WORK%\c.txt" >nul
echo from-sample-A>"C:\iso-probe\from-a.txt"
type "%WORK%\c.txt"
endlocal
exit /b 0
