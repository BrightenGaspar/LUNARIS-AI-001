import os
import sys
import time
import json
import socket
import threading
import urllib.request
from actions import NATIVE_TOOLS
import memory

OLLAMA_API = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:7b-instruct-q4_K_M"

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_system_vitals",
            "description": "Get current CPU, RAM, and battery levels.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_local_app",
            "description": "Launch an application on the laptop (e.g., vs code, notepad, cmd, browser).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "The target application name."}
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Execute a shell or PowerShell command on the host OS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The exact shell command to run."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_file",
            "description": "Read or write a local text or code file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["read", "write"]},
                    "filepath": {"type": "string", "description": "Path to the file."},
                    "content": {"type": "string", "description": "Content to write (optional if reading)."}
                },
                "required": ["action", "filepath"]
            }
        }
    }
]

def call_ollama(messages: list, tools: list = None):
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False
    }
    if tools:
        payload["tools"] = tools

    req = urllib.request.Request(
        OLLAMA_API,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))["message"]

def execute_lunaris_turn(user_prompt: str) -> str:
    """Full reasoning + tool execution + response synthesis turn."""
    memory.store_message("user", user_prompt)
    past_context = memory.get_recent_history(limit=6)

    system_instruction = {
        "role": "system",
        "content": (
            "You are Lunaris, a sophisticated and independent local AI. "
            "You have direct execution access to this computer via tools. "
            "Use tools when asked to check the system, open software, write files, or execute commands. "
            "Give direct, helpful, and concise answers."
        )
    }

    messages = [system_instruction] + past_context

    try:
        # Step 1: Model decides whether to invoke tools
        response = call_ollama(messages, tools=TOOL_DEFINITIONS)

        # Step 2: Handle tool calls if triggered
        if "tool_calls" in response and response["tool_calls"]:
            messages.append(response)
            for tool_call in response["tool_calls"]:
                fn_name = tool_call["function"]["name"]
                fn_args = tool_call["function"]["arguments"]
                
                target_fn = NATIVE_TOOLS.get(fn_name)
                tool_output = target_fn(**fn_args) if target_fn else "Error: Tool not found."
                
                messages.append({
                    "role": "tool",
                    "content": str(tool_output)
                })

            # Step 3: Second pass so the model synthesizes the tool result into a natural response
            final_turn = call_ollama(messages)
            final_reply = final_turn.get("content", "Task executed successfully.")
        else:
            final_reply = response.get("content", "Command received.")

        memory.store_message("assistant", final_reply)
        return final_reply

    except Exception as e:
        err_msg = f"[Lunaris Error]: {str(e)}"
        print(err_msg, flush=True)
        return err_msg

# ==========================================
# Socket Server for Background IPC
# ==========================================
def handle_client(conn):
    try:
        data = conn.recv(8192).decode('utf-8').strip()
        if data:
            print(f"[Engine Dispatch]: {data}", flush=True)
            result = execute_lunaris_turn(data)
            conn.sendall(result.encode('utf-8'))
    except Exception as e:
        conn.sendall(f"Server Error: {str(e)}".encode('utf-8'))
    finally:
        conn.close()

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 9999))
    server.listen(5)
    print("=== LUNARIS HIGH-PERFORMANCE ENGINE ACTIVE ON PORT 9999 ===", flush=True)
    
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()

if __name__ == "__main__":
    start_server()