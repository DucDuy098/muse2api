@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
chcp 65001 >nul
py -3.11 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto py311
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto py3
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto python
 echo Chua tim thay Python 3.10+. Hay cai Python 3.11 va chon Add Python to PATH.
 echo Huong dan: HUONG_DAN_TIENG_VIET.txt
pause
exit /b 1
:py311
py -3.11 windows_standalone.py install
goto done
:py3
py -3 windows_standalone.py install
goto done
:python
python windows_standalone.py install
:done
set "result=%errorlevel%"
if not "%result%"=="0" echo Cai dat chua thanh cong. Xem loi o tren, kiem tra Internet roi thu lai.
pause
exit /b %result%
