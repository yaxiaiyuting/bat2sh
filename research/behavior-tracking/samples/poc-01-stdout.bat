@echo off
rem PoC P1: output-effect layer -- stdout, special chars, exit code
echo POC-01-START
echo plain line
echo tab	separated
echo caret ^& ampersand
echo percent %% literal
echo POC-01-END
exit /b 7
