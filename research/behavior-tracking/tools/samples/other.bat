@echo off
rem Sample B (isolation probe): distinct artifacts in distinct directories.
rem Isolation criterion: this sample's after_manifest must NOT contain A's
rem   C:\poc\samples\work\a.txt, C:\poc\samples\work\c.txt, C:\iso-probe\from-a.txt
setlocal
set "WORK=%~dp0work"
set "PAY=%~dp0payload"
if not exist "%WORK%" mkdir "%WORK%"
if not exist "%PAY%" mkdir "%PAY%"
if not exist "C:\iso-probe" mkdir "C:\iso-probe"
echo b-marker>"%WORK%\b-marker.txt"
echo b-payload>"%PAY%\b-data.txt"
echo from-sample-B>"C:\iso-probe\from-b.txt"
type "%WORK%\b-marker.txt"
endlocal
exit /b 0
