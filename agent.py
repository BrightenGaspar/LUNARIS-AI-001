"""Lunaris Text Agent Brain (v1.0)
Integrates:
- Application Control (Chrome, VS Code, Calculator, Notepad, etc.)
- Web & Portal Search (Google, YouTube)
- File System Automation (Create folder/file, read, list)
- Real-time System Vitals (CPU, RAM, Battery)
- Memory Persistence (SQLite + JSON)
- Task Automation (Multi-step chained commands)
- Local AI Brain (Ollama Qwen 2.5)
"""

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

# Import existing Lunaris configuration and memory
try:
    from config import MODEL_NAME, OLLAMA_API, ROOT
except ImportError:
    MODEL_NAME = "qwen2.5:7b-instruct-q4_K_M"
    OLLAMA_API = "http://127.0.0.1:11434/api/chat"
    ROOT = Path(__file__).parent.resolve()

try:
    from memory import MemoryManager
    memory_manager = MemoryManager()
except ImportError:
    memory_manager = None

WORKSPACE_DIR = ROOT / "workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

APP_MAP = {
    "chrome": "start chrome",
    "google chrome": "start chrome",
    "browser": "start chrome",
    "code": "code",
    "vscode": "code",
    "vs code": "code",
    "calc": "calc",
    "calculator": "calc",
    "notepad": "notepad",
    "terminal": "cmd.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "explorer": "explorer.exe",
    "files": "explorer.exe",
}

WEB_PORTALS = {
    "youtube": "https://www.youtube.com",
    "github": "https://www.github.com",
    "google": "https://www.google.com",
    "chatgpt": "https://chatgpt.com",
    "reddit": "https://www.reddit.com",
    "whatsapp": "https://web.whatsapp.com",
}


class LunarisBrain:
    def __init__(self):
        self.workspace = WORKSPACE_DIR
        self.model = MODEL_NAME
        self.ollama_api = OLLAMA_API

    def execute(self, user_input: str) -> str:
        """Main entry point: parses compound or single commands."""
        text = (user_input or "").strip()
        if not text:
            return "Please enter a valid command."

        # MODULE 8: Check for multi-step task automation (compound commands)
        if self._is_compound_command(text):
            return self._execute_multi_step(text)

        # Execute single command
        return self._execute_single(text)

    def _is_compound_command(self, text: str) -> bool:
        """Detect whether text contains multiple chained instructions."""
        lower = text.lower()
        if " and search " in lower or " then search " in lower:
            return True
        if " and open " in lower or " then open " in lower:
            return True
        if " and create " in lower or " then create " in lower:
            return True
        if " and check " in lower or " then check " in lower:
            return True
        return False

    def _execute_multi_step(self, text: str) -> str:
        """Split and execute multi-step commands sequentially."""
        parts = re.split(r"\s+(?:and then|then|and)\s+", text, flags=re.IGNORECASE)
        results = []
        for i, sub_cmd in enumerate(parts, 1):
            sub_clean = sub_cmd.strip()
            if not sub_clean:
                continue
            res = self._execute_single(sub_clean)
            results.append(f"Step {i}: [{sub_clean}] → {res}")
        return "\n".join(results)

    def _execute_single(self, text: str) -> str:
        """Route a single command to the appropriate module."""
        lower = text.lower().strip()

        # -------------------------------------------------------------
        # MODULE 5: System Information (CPU, RAM, Battery)
        # -------------------------------------------------------------
        if any(w in lower for w in ["vitals", "system status", "battery status", "cpu usage", "ram usage"]) or lower in ["status", "battery", "cpu", "ram"]:
            return self._get_system_vitals()

        # -------------------------------------------------------------
        # MODULE 2: Application Control
        # -------------------------------------------------------------
        app_res = self._handle_app_control(lower)
        if app_res:
            return app_res

        # -------------------------------------------------------------
        # MODULE 3: Web Search & Portals
        # -------------------------------------------------------------
        search_res = self._handle_web_search(text, lower)
        if search_res:
            return search_res

        # -------------------------------------------------------------
        # MODULE 4: File Control
        # -------------------------------------------------------------
        file_res = self._handle_file_control(text, lower)
        if file_res:
            return file_res

        # -------------------------------------------------------------
        # MODULE 7: Memory (Remember & Recall)
        # -------------------------------------------------------------
        memory_res = self._handle_memory(text, lower)
        if memory_res:
            return memory_res

        # Greetings
        if lower in ["hello", "hi", "hey", "greetings"]:
            return "🌙 Greetings, Gaspar! Lunaris Text Agent is online and ready to control your laptop."

        # -------------------------------------------------------------
        # MODULE 6: AI Brain Connection (Local Ollama Qwen)
        # -------------------------------------------------------------
        return self._query_ai(text)

    # -----------------------------------------------------------------
    # Implementation: Application Control
    # -----------------------------------------------------------------
    def _handle_app_control(self, lower: str) -> Optional[str]:
        if lower.startswith("open ") or lower.startswith("launch ") or lower.startswith("start "):
            app_target = re.sub(r"^(open|launch|start)\s+", "", lower).strip()

            # Check web portals first
            if app_target in WEB_PORTALS:
                webbrowser.open(WEB_PORTALS[app_target])
                return f"Opening {app_target.capitalize()} in your browser ✓"

            # Check desktop apps
            for key, cmd in APP_MAP.items():
                if app_target == key or app_target.startswith(key):
                    try:
                        subprocess.Popen(cmd, shell=True)
                        return f"Opening {key.title()} ✓"
                    except Exception as e:
                        return f"Error opening {key}: {e}"

        # Close app command
        if lower.startswith("close ") or lower.startswith("kill "):
            app_target = re.sub(r"^(close|kill)\s+", "", lower).strip()
            return self._close_app(app_target)

        return None

    def _close_app(self, app_name: str) -> str:
        closed = 0
        for proc in psutil.process_iter(["name"]):
            try:
                pname = proc.info.get("name", "").lower()
                if app_name in pname:
                    proc.kill()
                    closed += 1
            except Exception:
                continue
        if closed > 0:
            return f"Closed {closed} instance(s) of '{app_name}' ✓"
        return f"No running processes matching '{app_name}' found."

    # -----------------------------------------------------------------
    # Implementation: Web Search
    # -----------------------------------------------------------------
    def _handle_web_search(self, text: str, lower: str) -> Optional[str]:
        if lower.startswith("search ") or lower.startswith("google "):
            query = re.sub(r"^(search|google)\s+", "", text, flags=re.IGNORECASE).strip()
            if not query:
                return "Please specify what you want to search for."
            url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
            webbrowser.open(url)
            return f"Searching Google for '{query}' ✓"

        if lower.startswith("youtube ") or lower.startswith("play on youtube "):
            query = re.sub(r"^(youtube|play on youtube)\s+", "", text, flags=re.IGNORECASE).strip()
            if not query:
                return "Please specify what you want to search on YouTube."
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
            webbrowser.open(url)
            return f"Searching YouTube for '{query}' ✓"

        return None

    # -----------------------------------------------------------------
    # Implementation: File Control
    # -----------------------------------------------------------------
    def _handle_file_control(self, text: str, lower: str) -> Optional[str]:
        # Create folder
        if lower.startswith("create folder ") or lower.startswith("make folder ") or lower.startswith("mkdir "):
            folder_name = re.sub(r"^(create folder|make folder|mkdir)\s+", "", text, flags=re.IGNORECASE).strip()
            target_path = self.workspace / folder_name
            try:
                target_path.mkdir(parents=True, exist_ok=True)
                return f"Folder '{folder_name}' created successfully at workspace ✓"
            except Exception as e:
                return f"Could not create folder: {e}"

        # Create file with optional content
        if lower.startswith("create file ") or lower.startswith("write file ") or lower.startswith("make file "):
            rest = re.sub(r"^(create file|write file|make file)\s+", "", text, flags=re.IGNORECASE).strip()
            if " with content " in rest.lower():
                fname, content = re.split(r"\s+with content\s+", rest, flags=re.IGNORECASE, maxsplit=1)
            elif " content " in rest.lower():
                fname, content = re.split(r"\s+content\s+", rest, flags=re.IGNORECASE, maxsplit=1)
            else:
                fname, content = rest, ""

            fname = fname.strip()
            target_file = self.workspace / fname
            try:
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"File '{fname}' created successfully ✓"
            except Exception as e:
                return f"Could not create file: {e}"

        # Read file
        if lower.startswith("read file ") or lower.startswith("open file "):
            fname = re.sub(r"^(read file|open file)\s+", "", text, flags=re.IGNORECASE).strip()
            target_file = self.workspace / fname
            if not target_file.exists():
                # Check root directory as well
                target_file = ROOT / fname

            if not target_file.exists():
                return f"File '{fname}' does not exist in workspace."

            try:
                with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(1500)
                return f"--- Content of {fname} ---\n{content}"
            except Exception as e:
                return f"Could not read file: {e}"

        # List files
        if lower in ["list files", "show files", "workspace files", "dir"]:
            files = list(self.workspace.iterdir())
            if not files:
                return f"Workspace ({self.workspace.name}) is currently empty."
            file_list = "\n".join([f"• {'[DIR] ' if f.is_dir() else '[FILE] '}{f.name}" for f in files])
            return f"Workspace Contents:\n{file_list}"

        return None

    # -----------------------------------------------------------------
    # Implementation: System Information (Module 5)
    # -----------------------------------------------------------------
    def _get_system_vitals(self) -> str:
        cpu = psutil.cpu_percent(interval=0.2)
        ram = psutil.virtual_memory()
        used_gb = round(ram.used / (1024**3), 1)
        total_gb = round(ram.total / (1024**3), 1)

        try:
            battery = psutil.sensors_battery()
            b_level = f"{battery.percent}%" if battery else "N/A"
            b_state = "Charging ⚡" if battery and battery.power_plugged else "On Battery 🔋"
        except Exception:
            b_level = "N/A"
            b_state = "AC Power"

        return (
            f"🌙 Lunaris System Vitals:\n"
            f"• CPU Load: {cpu}%\n"
            f"• RAM: {used_gb} GB / {total_gb} GB ({ram.percent}% used)\n"
            f"• Battery: {b_level} ({b_state})\n"
            f"• Status: All systems operational ✓"
        )

    # -----------------------------------------------------------------
    # Implementation: Memory (Module 7)
    # -----------------------------------------------------------------
    def _handle_memory(self, text: str, lower: str) -> Optional[str]:
        # Save memory
        if lower.startswith("remember "):
            data = text[len("remember "):].strip()
            if " is " in data:
                key, val = data.split(" is ", 1)
            elif " are " in data:
                key, val = data.split(" are ", 1)
            else:
                key, val = data, "Saved"

            key = key.strip()
            val = val.strip()

            if memory_manager:
                memory_manager.remember_fact(key, val)
            return f"Saved to memory: '{key}' is '{val}' ✓"

        # Recall memory
        if lower.startswith("what is ") or lower.startswith("who is ") or lower.startswith("recall "):
            prefix = "what is " if lower.startswith("what is ") else "who is " if lower.startswith("who is ") else "recall "
            key = text[len(prefix):].strip().rstrip("?").strip()
            if memory_manager:
                val = memory_manager.recall_fact(key)
                if val:
                    return f"Memory Recall: '{key}' is '{val}' ✓"

        if lower in ["show memories", "list memory", "show memory", "what do you remember"]:
            if memory_manager:
                try:
                    with memory_manager._db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT key, value FROM memory_facts ORDER BY updated_at DESC LIMIT 15")
                        rows = cursor.fetchall()
                        if rows:
                            facts = "\n".join([f"• {r[0]}: {r[1]}" for r in rows])
                            return f"Stored Memories:\n{facts}"
                except Exception:
                    pass
            return "No persistent memories found."

        return None

    # -----------------------------------------------------------------
    # Implementation: Local AI Brain (Module 6: Ollama Qwen2.5)
    # -----------------------------------------------------------------
    def _query_ai(self, text: str) -> str:
        prompt_payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Lunaris, a sophisticated local desktop AI assistant for Gaspar. "
                        "Respond clearly, concisely, and helpfully. Do not include markdown code block "
                        "wrappers unless writing code."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 250},
        }

        try:
            req = urllib.request.Request(
                self.ollama_api,
                data=json.dumps(prompt_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as res:
                data = json.loads(res.read().decode("utf-8"))
                reply = data.get("message", {}).get("content", "").strip()
                if reply:
                    return reply
        except Exception as e:
            # Fallback if Ollama is unreachable
            return (
                f"🌙 Lunaris Core processed: '{text}'.\n"
                f"(Note: Local Ollama AI currently offline or busy: {e})"
            )

        return "🌙 Lunaris could not generate a response."
