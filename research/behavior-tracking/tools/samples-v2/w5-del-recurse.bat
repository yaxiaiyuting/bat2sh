@echo off
mkdir sub 2>nul
> sub\x.tmp echo x
> root.tmp echo y
del /s /q *.tmp
echo done
