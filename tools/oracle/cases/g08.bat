@echo off
set n=
:Top
set n=%n%x
echo %n%
if not "%n%"=="xxx" goto Top
echo done
