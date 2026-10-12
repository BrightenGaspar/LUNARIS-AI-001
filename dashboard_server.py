import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = "127.0.0.1"
PORT = 8080
ENGINE_HOST = "127.0.0.1"
ENGINE_PORT = 9999
MAX_BODY_SIZE = 16 * 1024

def ask_lunaris(message):
    """Send a message to the existing Lunaris engine."""
    with socket.create_connection(
        (ENGINE_HOST, ENGINE_PORT), timeout=180
    ) as connection:
        connection.sendall(message.encode("utf-8"))
        connection.shutdown(socket.SHUT_WR)

        chunks = []
        total = 0

        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break

            total += len(chunk)
            if total > 1024 * 1024:
                raise ValueError("Lunaris response was too large.")

            chunks.append(chunk)

    return b"".join(chunks).decode("utf-8", errors="replace")

class DashboardHandler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path not in ("/", "/dashboard.html"):
            self.send_error(404, "Not found")
            return

        filepath = os.path.join(BASE_DIR, "dashboard.html")

        try:
            with open(filepath, "rb") as file:
                content = file.read()
        except OSError:
            self.send_error(500, "dashboard.html could not be read")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if urlparse(self.path).path != "/chat":
            self.send_error(404, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))

            if length < 1 or length > MAX_BODY_SIZE:
                self.send_json(400, {"error": "Invalid message size."})
                return

            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
            message = data.get("message", "")

            if not isinstance(message, str) or not message.strip():
                self.send_json(400, {"error": "Please enter a message."})
                return

            if len(message) > 4000:
                self.send_json(400, {"error": "Message is too long."})
                return

            reply = ask_lunaris(message.strip())
            self.send_json(200, {"reply": reply})

        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})
        except (OSError, TimeoutError) as error:
            self.send_json(
                502,
                {"error": "Could not connect to Lunaris engine: " + str(error)}
            )
        except Exception:
            self.send_json(500, {"error": "Unexpected dashboard server error."})

    def log_message(self, format_string, *args):
        print("[Dashboard] " + format_string % args)

if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print("=" * 48)
    print("LUNARIS DASHBOARD SERVER READY")
    print("Open http://127.0.0.1:8080 in your browser")
    print("Keep this window open while using Lunaris.")
    print("=" * 48)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server...")
    finally:
        server.server_close()
