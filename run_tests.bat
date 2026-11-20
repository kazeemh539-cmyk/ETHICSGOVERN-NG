@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo Run run.bat once first. & pause & exit /b 1 )
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt --quiet
echo Starting Model API for the tests...
start "model-api" /min ".venv\Scripts\python.exe" model_api\serve.py
timeout /t 6 >nul
".venv\Scripts\python.exe" -m pytest tests -v -p no:warnings
taskkill /fi "windowtitle eq model-api*" /f >nul 2>&1
pause
