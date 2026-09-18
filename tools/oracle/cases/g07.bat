@echo off
for %%i in (a b c) do (
  echo %%i
  goto Out
)
:Out
echo out
