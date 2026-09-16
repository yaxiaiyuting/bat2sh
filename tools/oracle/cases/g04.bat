@echo off
setlocal enabledelayedexpansion
set v=1
for %%i in (a b) do (set v=2 & echo d=!v!)
