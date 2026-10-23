@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" -m pip install --index-url https://pypi.org/simple -r requirements-gui.txt
if errorlevel 1 goto failed
echo Cai GUI thanh cong. Mo 05_MO_GUI.bat.
exit /b 0
:missing
echo Hay chay 01_CAI_DAT.bat truoc.
pause
exit /b 1
:failed
echo Chua cai duoc GUI. Kiem tra Internet va chay lai 06_CAI_GUI.bat.
pause
exit /b 1
