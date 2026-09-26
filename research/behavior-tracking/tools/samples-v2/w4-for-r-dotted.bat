@echo off
mkdir "my.project\samples" 2>nul
cd "my.project\samples"
for /r %%i in (.) do @echo %%~ni
echo done
