@echo off
rem 原创测试夹具：CJK 变量名（对应 backlog P-1）
rem 内容由本项目自行编写，不复用任何第三方语料
set 源目录=C:\data
set 目标目录=D:\backup
echo 源目录是 %源目录%
echo 目标目录是 %目标目录%
if exist "%源目录%" echo 源目录存在
