@echo off
setlocal enabledelayedexpansion
set str1=
for %%i in (a b) do set str1=!str1!%%i
echo [%str1%]
