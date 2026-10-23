@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\pythonw.exe" goto missing
".venv\Scripts\python.exe" -c "import PySide6.QtWidgets, PySide6.QtMultimedia, PySide6.QtMultimediaWidgets" >nul 2>&1
if not errorlevel 1 goto ready
call 06_CAI_GUI.bat
if errorlevel 1 exit /b 1
:ready
start "" ".venv\Scripts\pythonw.exe" desktop_gui.py
exit /b 0
:missing
echo Hay chay 01_CAI_DAT.bat truoc.
pause
exit /b 1
