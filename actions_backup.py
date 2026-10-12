import os
import subprocess
import psutil
import datetime

def get_system_vitals():
    """Reads live hardware metrics."""
    cpu = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory().percent
    battery = psutil.sensors_battery()
    bat = f"{battery.percent}%" if battery else "AC Connected"
    is_plugged = "Plugged in" if battery and battery.power_plugged else "Discharging"
    return f"CPU: {cpu}% | RAM: {ram}% | Battery: {bat} ({is_plugged})"

def open_local_app(app_name: str):
    """Launches local software directly via system path."""
    app = app_name.lower().strip()
    try:
        if "code" in app or "vs" in app:
            subprocess.Popen("code", shell=True)
        elif "terminal" in app or "cmd" in app:
            subprocess.Popen("start cmd", shell=True)
        elif "notepad" in app:
            subprocess.Popen("notepad", shell=True)
        elif "explorer" in app or "files" in app:
            subprocess.Popen("explorer", shell=True)
        else:
            subprocess.Popen(f"start {app}", shell=True)
        return f"Launched {app_name}."
    except Exception as e:
        return f"Failed to launch: {str(e)}"

def run_terminal_command(command: str):
    """Executes a local command and captures the output."""
    try:
        res = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=10
        )
        out = res.stdout.strip() or res.stderr.strip()
        return out[:600] if out else "Executed successfully with no output."
    except Exception as e:
        return f"Execution error: {str(e)}"

def manage_file(action: str, filepath: str, content: str = ""):
    """Reads or writes files locally."""
    try:
        if action == "write":
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Wrote {len(content)} characters to {filepath}."
        elif action == "read":
            if not os.path.exists(filepath):
                return "File does not exist."
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()[:600]
    except Exception as e:
        return f"File operation failed: {str(e)}"

NATIVE_TOOLS = {
    "get_system_vitals": get_system_vitals,
    "open_local_app": open_local_app,
    "run_terminal_command": run_terminal_command,
    "manage_file": manage_file
}