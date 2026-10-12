@echo off
setlocal
title Lunaris Enterprise Console
cd /d "%~dp0"

where ollama.exe >nul 2>&1
if errorlevel 1 (
    echo [!] Ollama was not found on PATH.
    pause
    exit /b 1
)

curl.exe --silent --fail http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [*] Starting Ollama server in background...
    start "" /min ollama.exe serve
    timeout /t 3 /nobreak >nul
)

"%~dp0.venv\Scripts\python.exe" lunaris.py
pause
