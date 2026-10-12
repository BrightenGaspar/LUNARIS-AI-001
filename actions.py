import ctypes
import os
import shutil
import subprocess
import urllib.parse
import webbrowser
from ctypes import wintypes
from typing import Any, Callable, Dict, Optional

import psutil

from config import CHROME_PATHS
from permissions import permission_guard

_APP_COMMANDS = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "files": ["explorer.exe"],
    "terminal": ["wt.exe"],
    "cmd": ["cmd.exe"],
    "task manager": ["taskmgr.exe"],
    "code": ["code"],
    "vs code": ["code"],
    "vscode": ["code"],
    "chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
}

_CLOSEABLE_APPS = {
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "notepad": "notepad.exe",
    "spotify": "spotify.exe",
    "code": "Code.exe",
    "vs code": "Code.exe",
    "calculator": "CalculatorApp.exe",
    "terminal": "WindowsTerminal.exe",
}

_WEB_PORTALS = {
    "youtube": "https://www.youtube.com",
    "github": "https://www.github.com",
    "google": "https://www.google.com",
    "chatgpt": "https://chatgpt.com",
    "whatsapp": "https://web.whatsapp.com",
    "reddit": "https://www.reddit.com",
}


def set_approval_prompt(prompt: Optional[Callable[[str], bool]]) -> None:
    """Set the runtime callback used to confirm high-impact actions."""
    permission_guard.set_prompt_handler(prompt)


def _approved(action_key: str) -> bool:
    if not permission_guard.requires_approval(action_key):
        return True
    return permission_guard.request_approval(action_key)


def get_system_vitals() -> str:
    """Read current CPU load, RAM usage, and battery status."""
    cpu = psutil.cpu_percent(interval=0.2)
    memory = psutil.virtual_memory()
    try:
        battery = psutil.sensors_battery()
    except (AttributeError, NotImplementedError, OSError):
        battery = None
    battery_level = f"{battery.percent}%" if battery else "unavailable"
    power_state = (
        "charging"
        if battery and battery.power_plugged
        else "on battery"
        if battery
        else "AC or battery status unavailable"
    )
    used_gb = round(memory.used / (1024**3), 1)
    total_gb = round(memory.total / (1024**3), 1)
    return (
        f"CPU load is {cpu} percent. Memory usage is {used_gb} of "
        f"{total_gb} gigabytes. Battery is at {battery_level}; {power_state}."
    )


def _launch_browser(target_url: Optional[str] = None) -> bool:
    chrome_bin = next((path for path in CHROME_PATHS if os.path.isfile(path)), None)
    if chrome_bin:
        command = [chrome_bin]
        if target_url:
            command.append(target_url)
        subprocess.Popen(command)
        return True
    return bool(webbrowser.open(target_url or "https://www.google.com"))


def open_application_or_search(app_name: str = "", query: str = "") -> str:
    """Open an allow-listed application or web portal, or search the web."""
    app = (app_name or "").lower().strip()
    search_text = (query or "").strip()

    if search_text:
        target_url = (
            "https://www.google.com/search?q="
            + urllib.parse.quote_plus(search_text)
        )
        if not _launch_browser(target_url):
            return "Could not open a browser for the requested search."
        return f"Searching Google for '{search_text}'."

    for site, url in _WEB_PORTALS.items():
        if app == site:
            if not webbrowser.open(url):
                return f"Could not open {site.capitalize()} in a browser."
            return f"Opening {site.capitalize()} in your default browser."

    if app in {"browser", "chrome"}:
        if not _launch_browser():
            return "Could not open a browser."
        return "Launching Google Chrome or the default browser."

    command = _APP_COMMANDS.get(app)
    if command is None:
        return f"'{app_name}' is not on the approved application list."
    if command[0] == "code" and shutil.which("code") is None:
        return "VS Code command-line launcher was not found."

    try:
        subprocess.Popen(command)
    except OSError as exc:
        return f"Could not launch {app_name}: {exc}"
    return f"Successfully opened {app_name}."


def close_application(app_name: str) -> str:
    """Close an allow-listed application after explicit user approval."""
    app = (app_name or "").lower().replace(".exe", "").strip()
    executable = _CLOSEABLE_APPS.get(app)
    if executable is None:
        return f"'{app_name}' is not on the approved application list."
    if not _approved("close_application"):
        return "Application close was not approved."

    process_ids = set()
    access_denied = 0
    for process in psutil.process_iter(["name"]):
        try:
            process_name = process.info.get("name")
            if process_name and process_name.lower() == executable.lower():
                process_ids.add(process.pid)
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            access_denied += 1

    if process_ids:
        user32 = ctypes.windll.user32
        close_message = 0x0010
        windows_signaled = 0
        process_id_type = wintypes.DWORD

        def request_window_close(window, _):
            nonlocal windows_signaled
            process_id = process_id_type()
            user32.GetWindowThreadProcessId(
                window, ctypes.byref(process_id)
            )
            if process_id.value in process_ids:
                user32.PostMessageW(window, close_message, 0, 0)
                windows_signaled += 1
            return True

        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )
        user32.EnumWindows(
            callback_type(request_window_close), 0
        )
        result = (
            f"Sent a graceful close request to {windows_signaled} "
            f"{app_name} window(s)."
        )
        if access_denied:
            result += f" Access was denied for {access_denied} process(es)."
        return result
    if access_denied:
        return f"Could not access {app_name} process(es) to close them."
    return f"No running {app_name} process was found."


def control_media_and_volume(action: str) -> str:
    """Send a media or volume key to the local Windows session."""
    if os.name != "nt":
        return "Media and volume controls are only available on Windows."

    normalized = (action or "").lower().strip()
    key_codes = {
        "mute": 0xAD,
        "unmute": 0xAD,
        "volume up": 0xAF,
        "volume down": 0xAE,
        "play": 0xB3,
        "pause": 0xB3,
        "next": 0xB0,
        "previous": 0xB1,
    }
    virtual_key = next(
        (code for label, code in key_codes.items() if label in normalized),
        None,
    )
    if virtual_key is None:
        return f"Audio action '{action}' not recognized."

    user32 = ctypes.windll.user32
    repeats = 5 if "volume" in normalized else 1
    for _ in range(repeats):
        user32.keybd_event(virtual_key, 0, 0, 0)
        user32.keybd_event(virtual_key, 0, 2, 0)
    return f"Audio directive executed: {action}."


def control_power(state: str) -> str:
    """Lock, sleep, restart, or shut down Windows with approval where needed."""
    normalized = (state or "").lower().strip()
    commands = {
        "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    }

    if normalized in {"shutdown", "restart"}:
        if not _approved(normalized):
            return f"{normalized.capitalize()} was not approved."
        command = ["shutdown", "/s" if normalized == "shutdown" else "/r", "/t", "10"]
    else:
        command = commands.get(normalized)

    if command is None:
        return f"Power action '{state}' not recognized."

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return f"Could not perform power action '{normalized}': {exc}"
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        return f"Power action '{normalized}' failed: {detail or result.returncode}."
    if normalized in {"shutdown", "restart"}:
        return f"System scheduled to {normalized} in 10 seconds."
    return "Workstation locked." if normalized == "lock" else "System entering sleep mode."


def open_local_app(app_name: str) -> str:
    """Compatibility wrapper for Lunaris's existing allow-listed app tool."""
    return open_application_or_search(app_name=app_name)


def run_terminal_command(command: str) -> str:
    """Run a shell command only after explicit confirmation is configured."""
    if not isinstance(command, str) or not command.strip():
        return "A non-empty terminal command is required."
    if not _approved("terminal_exec"):
        return "Terminal execution was not approved."
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Execution error: {exc}"
    output = result.stdout.strip() or result.stderr.strip()
    if result.returncode:
        return f"Command failed ({result.returncode}): {output[:600]}"
    return output[:600] if output else "Executed successfully with no output."


def manage_file(action: str, filepath: str, content: str = "") -> str:
    """Read or write a file within an approved user folder."""
    if not permission_guard.is_path_allowed(filepath):
        return "File access is outside the approved folders."

    normalized_action = (action or "").lower().strip()
    if normalized_action == "write":
        if not _approved("write_file"):
            return "File write was not approved."
        try:
            with open(filepath, "w", encoding="utf-8") as file:
                file.write(content)
        except OSError as exc:
            return f"File write failed: {exc}"
        return f"Wrote {len(content)} characters to {filepath}."

    if normalized_action == "read":
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                return file.read()[:600]
        except FileNotFoundError:
            return "File does not exist."
        except OSError as exc:
            return f"File read failed: {exc}"
    return f"Unsupported file action: {action}"


NATIVE_TOOLS: Dict[str, Callable[..., Any]] = {
    "get_system_vitals": get_system_vitals,
    "open_local_app": open_local_app,
    "run_terminal_command": run_terminal_command,
    "manage_file": manage_file,
}

AVAILABLE_TOOLS: Dict[str, Callable[..., Any]] = {
    "get_system_vitals": get_system_vitals,
    "open_application_or_search": open_application_or_search,
    "close_application": close_application,
    "control_media_and_volume": control_media_and_volume,
    "control_power": control_power,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "open_application_or_search",
            "description": "Open an approved Windows app or web destination, or search Google.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_application",
            "description": "Request approval, then close an allow-listed desktop application.",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string"}},
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_media_and_volume",
            "description": "Adjust volume, mute, or control media playback.",
            "parameters": {
                "type": "object",
                "properties": {"action": {"type": "string"}},
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_vitals",
            "description": "Query current CPU, RAM, and battery status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_power",
            "description": "Lock, sleep, restart, or shut down the Windows computer.",
            "parameters": {
                "type": "object",
                "properties": {"state": {"type": "string"}},
                "required": ["state"],
            },
        },
    },
]
