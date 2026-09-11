@echo off
chcp 65001 > nul
echo =======================================================
echo   ASOL Casual Scout — Thu Thap & Phan Tich Tu Dong
echo =======================================================
echo.

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [1/3] Dang thu thap Top 100 11 thi truong ASEAN + US...
"%PYTHON_EXE%" -m casual_scout collect --data-dir .\data
if %errorlevel% neq 0 (
    echo [CANH BAO] Thu thap du lieu co the gap canh bao mang hoac hoan thanh mot phan.
)

echo.
echo [2/3] Dang chay Engine Phan tich & Opportunity Radar...
"%PYTHON_EXE%" -m casual_scout analyze --data-dir .\data
if %errorlevel% neq 0 (
    echo [CANH BAO] Engine phan tich co the chua tim thay du lieu cu de so sanh delta.
)

echo.
echo [3/3] Dang mo Web Dashboard tren trinh duyet...
start "" "http://127.0.0.1:8000/dashboard"
"%PYTHON_EXE%" -m casual_scout serve --host 127.0.0.1 --port 8000 --data-dir .\data

pause
