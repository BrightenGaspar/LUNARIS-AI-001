@echo off
setlocal
title Lunaris Enterprise Control Center
cd /d "%~dp0"

curl.exe --silent --fail http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [*] Starting Ollama server in background...
    start "" /min ollama.exe serve
    timeout /t 3 /nobreak >nul
)

echo [*] Starting Lunaris Engine & Dashboard...
start "" "%~dp0.venv\Scripts\python.exe" lunaris.py
timeout /t 2 /nobreak >nul
start http://localhost:8080
