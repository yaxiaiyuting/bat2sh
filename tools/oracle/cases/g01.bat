@echo off
for %%i in (a b) do if %%i==a (echo A ) else (if %%i==b (echo B ) else (
echo body1
echo body2
))
echo after
