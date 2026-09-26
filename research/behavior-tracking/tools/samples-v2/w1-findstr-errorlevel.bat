@echo off
> haystack.txt echo needle
> keep.txt echo PRECIOUS
findstr "needle" haystack.txt >nul
if errorlevel 1 del keep.txt
echo done
