"""Lunaris Enterprise v2.0 - Master System Launcher & Orchestrator.

Starts the central event bus, dynamic plugin manager, multi-tier memory,
AI planner (Qwen 2.5), TCP socket server, web dashboard, and optional voice services.
"""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import socket
import sys
import threading
import time
from typing import Any, Dict
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Lunaris.Core")

from config import (
    APP_NAME,
    DASHBOARD_PORT,
    MODEL_NAME,
    ROOT,
    SOCKET_PORT,
    USER_NAME,
    VERSION,
)
from event_bus import bus, Event, EventType
from memory import memory_manager
from permissions import permission_guard
from planner import planner
from plugin_manager import plugin_manager
from voice.earbuds import detect_preferred_input_device
from voice.listener import voice_worker


# =====================================================================
# TCP SOCKET SERVER (Compatibility port 9999)
# =====================================================================
class SocketServerThread(threading.Thread):
    def __init__(self, host: str = "127.0.0.1", port: int = SOCKET_PORT) -> None:
        super().__init__(name="LunarisSocketServer", daemon=True)
        self.host = host
        self.port = port
        self.running = True

    def run(self) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((self.host, self.port))
                s.listen(5)
                logger.info(f"Socket server listening on {self.host}:{self.port}")

                while self.running:
                    try:
                        conn, addr = s.accept()
                        threading.Thread(
                            target=self._handle_client,
                            args=(conn,),
                            daemon=True,
                        ).start()
                    except OSError:
                        break
        except Exception as exc:
            logger.error(f"Failed to start socket server on port {self.port}: {exc}")

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            try:
                chunks = []
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    chunks.append(data)
                
                raw_request = b"".join(chunks).decode("utf-8", errors="replace").strip()
                if not raw_request:
                    return

                reply = planner.think_and_act(raw_request)
                conn.sendall(reply.encode("utf-8"))
            except Exception as exc:
                logger.error(f"Error handling socket client: {exc}")


# =====================================================================
# EMBEDDED DASHBOARD HTTP SERVER (Port 8080)
# =====================================================================
class DashboardHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy HTTP request logging in console
        pass

    def send_json(self, status: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path in ("/", "/dashboard", "/dashboard.html"):
            dash_path = ROOT / "dashboard.html"
            if dash_path.exists():
                try:
                    content = dash_path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception:
                    pass
            self.send_error(404, "dashboard.html not found")
            return

        elif path == "/api/status":
            self.send_json(200, {
                "app": APP_NAME,
                "version": VERSION,
                "status": "online",
                "model": planner.model_name,
                "mode": planner.mode,
                "plugins": plugin_manager.get_status(),
            })
            return

        elif path == "/api/events":
            self.send_json(200, {"events": bus.get_recent_events(limit=30)})
            return

        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path in ("/chat", "/api/chat"):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8"))
                message = payload.get("message", "").strip()

                if not message:
                    self.send_json(400, {"error": "Message is required."})
                    return

                reply = planner.think_and_act(message)
                self.send_json(200, {"reply": reply})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        self.send_error(404, "Not Found")


class DashboardServerThread(threading.Thread):
    def __init__(self, port: int = DASHBOARD_PORT) -> None:
        super().__init__(name="LunarisDashboardServer", daemon=True)
        self.port = port
        self.server: Optional[ThreadingHTTPServer] = None

    def run(self) -> None:
        try:
            self.server = ThreadingHTTPServer(("0.0.0.0", self.port), DashboardHTTPHandler)
            logger.info(f"Dashboard web server active: http://localhost:{self.port}")
            self.server.serve_forever()
        except Exception as exc:
            logger.error(f"Dashboard server failed to bind on port {self.port}: {exc}")


# =====================================================================
# MAIN INITIALIZATION & RUNNER
# =====================================================================
def print_banner() -> None:
    print(r"""
======================================================================
  _      _   _ _   _          _____  _____  _____ 
 | |    | | | | \ | |   /\   |  __ \|_   _|/ ____|
 | |    | | | |  \| |  /  \  | |__) | | | | (___  
 | |    | | | | . ` | / /\ \ |  _  /  | |  \___ \ 
 | |____| |_| | |\  |/ ____ \| | \ \ _| |_ ____) |
 |______|\___/|_| \_/_/    \_\_|  \_\_____|_____/ 
                                ENTERPRISE v2.0
======================================================================
    """)
    print(f"  AI Model:       {planner.model_name}")
    print(f"  Owner:          {USER_NAME}")
    print(f"  Dashboard HUD:  http://localhost:{DASHBOARD_PORT}")
    print(f"  Socket Port:    {SOCKET_PORT}")
    print("======================================================================\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lunaris Enterprise Desktop Assistant")
    parser.add_argument("--cli", action="store_true", help="Launch interactive CLI prompt")
    parser.add_argument("--voice", action="store_true", help="Launch with continuous voice wake-word listening")
    parser.add_argument("--mode", type=str, default="normal", help="AI mode: normal, developer, office, study")
    args = parser.parse_args()

    print_banner()

    # 1. Discover and load modular plugins
    plugin_manager.discover_and_load()
    status = plugin_manager.get_status()
    print(f"[*] Loaded {status['total_plugins']} capability plugins with {status['total_tools']} tools.")

    # 2. Set mode
    if args.mode:
        planner.set_mode(args.mode)

    # 3. Audio detection
    dev_idx, dev_name = detect_preferred_input_device()
    print(f"[*] Preferred Audio Input: [{dev_idx}] {dev_name}")

    # 4. Start Socket Server (Thread)
    socket_srv = SocketServerThread()
    socket_srv.start()

    # 5. Start Dashboard HTTP Server (Thread)
    dash_srv = DashboardServerThread()
    dash_srv.start()

    bus.emit(EventType.SYSTEM_READY, {"version": VERSION, "tools": status["total_tools"]})

    # 6. Start Voice Worker if requested
    if args.voice:
        print("[*] Starting continuous background voice listener ('Hey Lunaris')...")
        voice_worker.start()

    # 7. Interactive CLI Loop
    print("\n[Lunaris Ready] Type your request below (or 'exit' to quit, 'mode <name>' to change mode):\n")
    try:
        while True:
            try:
                user_input = input(f"[{USER_NAME} @ {planner.mode}]> ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                print("Shutting down Lunaris...")
                break

            if user_input.lower().startswith("mode "):
                new_mode = user_input.split(" ", 1)[1]
                print(planner.set_mode(new_mode))
                continue

            # Run planner
            reply = planner.think_and_act(user_input)
            print(f"\n[Lunaris]: {reply}\n")

    except KeyboardInterrupt:
        print("\nLunaris shutdown requested.")
    finally:
        bus.stop()
        if args.voice:
            voice_worker.stop()
        print("Lunaris stopped.")


if __name__ == "__main__":
    main()
