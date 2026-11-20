@echo off
setlocal
cd /d "%~dp0"
title EthicsGovern-NG
echo ==============================================================
echo   EthicsGovern-NG  -  AI governance dashboard (prototype)
echo ==============================================================

rem ---- find a suitable Python (3.10 to 3.12 recommended) ----
set PY=
for %%V in (3.12 3.11 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set PY=py -%%V
  )
)
if not defined PY (
  python -c "import sys; assert (3,10)<=sys.version_info[:2]<=(3,13)" >nul 2>&1 && set PY=python
)
if not defined PY (
  echo.
  echo Python 3.10, 3.11 or 3.12 was not found.
  echo Install Python 3.12 from https://www.python.org/downloads/windows/
  echo During installation, tick "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)

rem ---- first run: create a private environment and install packages ----
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo First run: installing components. This takes 3 to 8 minutes and needs internet.
  %PY% -m venv .venv
  if errorlevel 1 ( echo Could not create the environment. & pause & exit /b 1 )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Installation failed. Check your internet connection and run this file again.
    rmdir /s /q .venv
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" launcher.py %*
echo.
pause
