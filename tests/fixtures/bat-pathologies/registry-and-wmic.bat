@echo off
rem 原创测试夹具：环境依赖命令（reg / wmic / sc / net）
rem 预期：产生诚实 TODO，且 todo_count 必须 > 0（报告诚实性不变量）
reg query "HKLM\Software\Microsoft\Windows NT\CurrentVersion" /v ProductName
reg add "HKCU\Software\Bat2shFixture" /v Demo /t REG_SZ /d 1 /f
wmic os get Caption,Version
sc query wuauserv
net user demo /delete
