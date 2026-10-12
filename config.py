import os
from pathlib import Path

# =====================================================
# LUNARIS ENTERPRISE CONFIGURATION
# =====================================================
APP_NAME = "Lunaris"
VERSION = "2.0"
AUTHOR = "Gaspar"

# AI Model Selection
MODEL_NAME = os.getenv("LUNARIS_MODEL", "qwen2.5:7b-instruct-q4_K_M")
FALLBACK_MODEL = "llama3.2:latest"
EMBEDDING_MODEL = "nomic-embed-text:latest"
OLLAMA_API = os.getenv("OLLAMA_API", "http://127.0.0.1:11434/api/chat")

# Network Ports
ENGINE_PORT = 9999
SOCKET_PORT = 9999
DASHBOARD_PORT = 8080
FASTAPI_PORT = 8000

# Paths
ROOT = Path(__file__).parent.resolve()
LOGS_DIR = ROOT / "logs"

# AI Personality & Mode Settings
CURRENT_MODE = "normal"  # 'normal', 'developer', 'office', 'study'
USER_NAME = "Gaspar"

# Telemetry & Persistence
PERSIST_LOGS_TO_DISK = True
PERSIST_CONVERSATIONS = True

# Voice & Audio Configuration
WAKE_WORDS = [
    "hey lunaris",
    "lunaris",
    "hey jarvis",
    "jarvis",
    "lunar",
]

VOICE_RATE = 185
VOICE_VOLUME = 1.0
PREFERRED_AUDIO_DEVICE = None  # None = auto-detect Bluetooth earbuds or default

# Security & Permissions
REQUIRE_CONFIRMATION_FOR_DESTRUCTIVE = True
CONFIRMATION_TIMEOUT_SEC = 10

ALLOWED_FOLDERS = [
    str(ROOT),
    str(Path.home() / "Desktop"),
    str(Path.home() / "Documents"),
    str(Path.home() / "Downloads"),
    str(Path.home() / "OneDrive" / "Desktop"),
]

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
]
