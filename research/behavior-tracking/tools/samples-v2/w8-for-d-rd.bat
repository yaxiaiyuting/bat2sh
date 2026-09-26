@echo off
mkdir old1 2>nul
mkdir old2 2>nul
mkdir new1 2>nul
> old1\f.txt echo x
for /d %%d in (old*) do rd /s /q "%%d"
echo done
