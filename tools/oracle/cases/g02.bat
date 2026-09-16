@echo off
for %%i in (a b c) do if %%i==a (echo skipA) else (if %%i==b (echo skipB) else (
echo body=%%i
))
echo done
