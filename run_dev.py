"""Lunaris Enterprise v2.0 - Development Runner (run_dev.py).

Provides one-command dev environment startup:
- Pre-flight verification (Ollama status, model availability, audio hardware)
- Real-time EventBus streaming logger to console
- Starts TCP Socket Server (port 9999)
- Starts Dashboard Web Server (port 8080)
- Interactive Dev Console with live tool execution tracing
"""

import os
import sys
import time
import socket
import urllib.request
import urllib.error
import json
import subprocess
import threading
from pathlib import Path

# Ensure C:\Lunaris is in sys.path
ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

from config import (
    APP_NAME,
    VERSION,
    MODEL_NAME,
    OLLAMA_API,
    DASHBOARD_PORT,
    SOCKET_PORT,
    USER_NAME,
)
from event_bus import bus, Event, EventType
from memory import memory_manager
from plugin_manager import plugin_manager
from planner import planner
from voice.earbuds import detect_preferred_input_device
from lunaris import SocketServerThread, DashboardServerThread


def check_and_start_ollama() -> bool:
    """Ensure Ollama daemon is active and responsive."""
    try:
        req = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        data = json.loads(req.read().decode())
        models = [m.get("name", "") for m in data.get("models", [])]
        print(f"  [+] Ollama is online with {len(models)} model(s).")
        return True
    except Exception:
        print("  [!] Ollama is not running. Attempting to start 'ollama serve'...")
        try:
            subprocess.Popen(["ollama", "serve"], shell=True)
            for _ in range(10):
                time.sleep(1)
                try:
                    urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
                    print("  [+] Ollama server started successfully.")
                    return True
                except Exception:
                    pass
        except Exception as exc:
            print(f"  [-] Failed to automatically start Ollama: {exc}")
    return False


def setup_dev_event_logger() -> None:
    """Stream event bus notifications to console with formatted tags."""
    def on_event(event: Event) -> None:
        etype = event.type.value if hasattr(event.type, "value") else str(event.type)
        if etype == EventType.TOOL_CALL:
            tool = event.data.get("tool", "")
            args = event.data.get("arguments", {})
            print(f"  >>> [TRACE] Tool Call: {tool}({args})", flush=True)
        elif etype == EventType.TOOL_RESULT:
            tool = event.data.get("tool", "")
            elapsed = event.data.get("elapsed_ms", 0)
            res = str(event.data.get("result", ""))[:120]
            print(f"  <<< [TRACE] Tool Result ({tool}) [{elapsed}ms]: {res}...", flush=True)
        elif etype == EventType.TOOL_ERROR:
            tool = event.data.get("tool", "")
            err = event.data.get("error", "")
            print(f"  [!] [TRACE] Tool Error ({tool}): {err}", flush=True)
        elif etype == EventType.PLANNER_START:
            prompt = event.data.get("prompt", "")
            print(f"  [*] [PLANNER] Reasoning on prompt: '{prompt}'", flush=True)

    bus.subscribe("*", on_event)


def print_dev_header() -> None:
    print("\n" + "=" * 65)
    print("   LUNARIS ENTERPRISE v2.0 - DEVELOPMENT RUNNER (DEV MODE)")
    print("=" * 65)


def run_dev() -> None:
    print_dev_header()
    print("[1/5] Checking environment & Ollama runtime...")
    ollama_ok = check_and_start_ollama()
    if not ollama_ok:
        print("  [-] WARNING: Ollama API is offline. Tool calls may fail.")

    print("\n[2/5] Inspecting audio input devices...")
    dev_idx, dev_name = detect_preferred_input_device()
    print(f"  [+] Audio Microphone: [{dev_idx}] {dev_name}")

    print("\n[3/5] Initializing Plugin Registry & Capabilities...")
    plugin_manager.discover_and_load()
    status = plugin_manager.get_status()
    for p in status["plugins"]:
        tools_str = ", ".join(p["tools"][:4])
        if len(p["tools"]) > 4:
            tools_str += f", +{len(p['tools']) - 4} more"
        print(f"  [+] Plugin [{p['name']} v{p['version']}]: {tools_str}")

    print("\n[4/5] Launching Background Servers...")
    setup_dev_event_logger()

    socket_srv = SocketServerThread(port=SOCKET_PORT)
    socket_srv.start()
    print(f"  [+] Socket Server listening on 127.0.0.1:{SOCKET_PORT}")

    dash_srv = DashboardServerThread(port=DASHBOARD_PORT)
    dash_srv.start()
    print(f"  [+] Dashboard HUD serving on http://localhost:{DASHBOARD_PORT}")

    print("\n[5/5] Running Self-Diagnostic Smoke Test...")
    smoke_reply = planner.think_and_act("System self-test: please acknowledge readiness.")
    print(f"  [+] Diagnostic Reply: {smoke_reply.strip()}")

    print("\n" + "-" * 65)
    print("   DEVELOPMENT ENVIRONMENT READY!")
    print(f"   Model: {planner.model_name} | Mode: {planner.mode} | Owner: {USER_NAME}")
    print("   Commands:")
    print("     - Type any query to execute (e.g. 'check vitals', 'open notepad')")
    print("     - 'status'  : Display loaded plugins & tool registry")
    print("     - 'vitals'  : Display real-time CPU, RAM, battery")
    print("     - 'mode <name>' : Switch mode (normal, developer, office, study)")
    print("     - 'web'     : Open dashboard in browser")
    print("     - 'exit'    : Stop runner")
    print("-" * 65 + "\n")

    try:
        while True:
            try:
                line = input(f"lunaris-dev [{planner.mode}]> ").strip()
            except EOFError:
                break

            if not line:
                continue

            if line.lower() in ("exit", "quit", "q"):
                print("Stopping development runner...")
                break

            if line.lower() == "status":
                st = plugin_manager.get_status()
                print(f"\nPlugins Loaded: {st['total_plugins']}, Total Tools: {st['total_tools']}")
                for pl in st["plugins"]:
                    print(f"  - {pl['name']}: {pl['tools']}")
                print()
                continue

            if line.lower() == "vitals":
                v = plugin_manager.execute_tool("get_system_vitals", {})
                print(f"\n{v}\n")
                continue

            if line.lower() == "web":
                import webbrowser
                webbrowser.open(f"http://localhost:{DASHBOARD_PORT}")
                print(f"Opened http://localhost:{DASHBOARD_PORT}")
                continue

            if line.lower().startswith("mode "):
                m = line.split(" ", 1)[1]
                print(f"\n{planner.set_mode(m)}\n")
                continue

            # Run planner with real-time tracing
            reply = planner.think_and_act(line)
            print(f"\n[Lunaris]: {reply}\n")

    except KeyboardInterrupt:
        print("\nDev runner interrupted.")
    finally:
        bus.stop()
        print("Dev runner terminated.")


if __name__ == "__main__":
    run_dev()
