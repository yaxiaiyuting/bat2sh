@echo off
mkdir sub 2>nul
> sub\data.txt echo data
> top.txt echo top
for /r %%i in (.) do rd /s /q "%%i"
echo done
