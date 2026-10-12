@echo off
setlocal
title Lunaris Enterprise - Development Runner
cd /d "%~dp0"

"%~dp0.venv\Scripts\python.exe" run_dev.py
pause
