@echo off
chcp 65001 >nul
title Engenheiro
cd /d "%~dp0.."
where py >nul 2>nul
if %errorlevel%==0 (
    py engenheiro.py %*
) else (
    python engenheiro.py %*
)
if errorlevel 9009 (
    echo.
    echo Python nao encontrado. Instale pelo site python.org e marque "Add python.exe to PATH".
)
echo.
pause
