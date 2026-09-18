@echo off
set x=2
if %x%==1 goto A
if %x%==2 goto B
:A
echo a
goto :eof
:B
echo b
