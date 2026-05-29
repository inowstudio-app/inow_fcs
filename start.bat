@echo off
REM ===== DCR Feasibility System launcher (Windows) =====
cd /d "%~dp0backend"
echo Installing/updating dependencies...
python -m pip install --quiet -r requirements.txt
echo.
echo Starting DCR Feasibility System...
echo Open your browser at:  http://127.0.0.1:8000
echo (Press Ctrl+C in this window to stop.)
echo.
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
pause
