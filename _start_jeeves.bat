@echo off
cd /d "%~dp0"
title Jeeves AI Assistant
python -m src.main
if errorlevel 1 (
    echo.
    echo Jeeves narazil na chybu pri spousteni.
    pause
)
