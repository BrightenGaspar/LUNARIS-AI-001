import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask, render_template, request, jsonify
from agent import LunarisBrain

app = Flask(__name__)
brain = LunarisBrain()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/command", methods=["POST"])
def command():
    data = request.get_json(silent=True) or {}
    text = data.get("command", "")
    result = brain.execute(text)
    return jsonify({
        "response": result
    })

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status": "online",
        "agent": "Lunaris Text Agent v1.0",
        "model": brain.model
    })

if __name__ == "__main__":
    print("""
=====================================================
🌙 LUNARIS TEXT AGENT v1.0 ONLINE
=====================================================
• Mode: Text & Desktop Automation (No Voice)
• AI Brain: Ollama Qwen2.5 (7B)
• Memory: Multi-tiered SQLite + JSON
• Web UI: http://127.0.0.1:5000
=====================================================
Ready for commands. Keep this CMD window open.
""")
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
