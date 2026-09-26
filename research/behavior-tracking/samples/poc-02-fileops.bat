@echo off
rem PoC P2: output-effect layer -- filesystem diff (mkdir/write/copy/read/delete)
setlocal
set "WORK=%~dp0work"
if not exist "%WORK%" mkdir "%WORK%"
echo alpha>"%WORK%\a.txt"
echo beta>"%WORK%\b.txt"
copy /y "%WORK%\a.txt" "%WORK%\c.txt" >nul
type "%WORK%\b.txt"
del "%WORK%\b.txt"
endlocal
exit /b 0
