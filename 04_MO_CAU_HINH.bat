@echo off
setlocal
cd /d "%~dp0"
if not exist ".env" goto missing
start "" notepad.exe "%~dp0.env"
exit /b
:missing
echo Hay chay 01_CAI_DAT.bat truoc de tao cau hinh rieng.
pause
exit /b 1
