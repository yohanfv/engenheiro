@echo off
chcp 65001 >nul
cd /d "%~dp0.."
where py >nul 2>nul
if %errorlevel%==0 (
    py engenheiro.py --ouvir-vozes
) else (
    python engenheiro.py --ouvir-vozes
)
echo.
pause
