@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" windows_standalone.py run
set "result=%errorlevel%"
pause
exit /b %result%
:missing
echo Hay chay 01_CAI_DAT.bat truoc.
pause
exit /b 1
