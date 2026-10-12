@echo off
setlocal
title Lunaris Enterprise
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Lunaris virtual environment not found at .venv\Scripts\python.exe
    exit /b 1
)

"%~dp0.venv\Scripts\python.exe" -c "import numpy, pyttsx3, sounddevice, speech_recognition" >nul 2>&1
if errorlevel 1 (
    echo Missing voice dependencies. Install numpy, pyttsx3, sounddevice, and SpeechRecognition in .venv.
    exit /b 1
)

where ollama.exe >nul 2>&1
if errorlevel 1 (
    echo Ollama was not found on PATH.
    exit /b 1
)

curl.exe --silent --fail http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo Starting local Ollama server...
    start "" /min ollama.exe serve
    timeout /t 3 /nobreak >nul
)

echo Starting Lunaris voice service...
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0service.py"
endlocal
