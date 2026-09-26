@echo off
mkdir src 2>nul
mkdir src\deep 2>nul
> src\a.txt echo A
> src\deep\b.txt echo B
xcopy /e /i /y src dst
echo done
