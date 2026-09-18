@echo off
for %%i in (a b) do (
  for %%j in (x y) do (
    echo %%i %%j
    goto Out
  )
)
:Out
echo out
