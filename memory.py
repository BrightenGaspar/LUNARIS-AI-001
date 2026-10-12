"""Lunaris Enterprise Multi-tiered Memory Architecture.

Provides:
1. Working Memory (in-RAM bounded context for active LLM generation)
2. Conversation Memory (recent turns with JSON/SQLite persistence)
3. Long-term Fact Memory (persistent user preferences, system facts, entities)
4. Project Memory (tracking active workspace paths and recent projects)
"""

from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).parent.resolve()
LOG_DIR = BASE_DIR / "logs"
MEMORY_FILE = LOG_DIR / "memory.json"
SQLITE_DB = LOG_DIR / "lunaris_memory.db"

_lock = threading.RLock()
MAX_JSON_MESSAGES = 500


class MemoryManager:
    """Multi-tiered memory store for Lunaris."""

    def __init__(self) -> None:
        self.log_dir = LOG_DIR
        self.memory_file = MEMORY_FILE
        self.db_path = SQLITE_DB
        self._init_storage()

    @contextmanager
    def _db_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_storage(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with _lock:
            with self._db_connection() as conn:
                cursor = conn.cursor()
                # Conversations table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Long-term Key-Value facts and user preferences
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS memory_facts (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        category TEXT DEFAULT 'general',
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Project workspaces table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS project_workspaces (
                        name TEXT PRIMARY KEY,
                        path TEXT NOT NULL,
                        description TEXT,
                        last_opened DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()

    # -------------------------------------------------------------
    # Conversation History Tier
    # -------------------------------------------------------------
    def store_turn(self, role: str, content: str, session_id: str = "default") -> None:
        """Store a user or assistant message to both SQLite and JSON cache."""
        if role not in {"user", "assistant", "system", "tool"}:
            role = "user"

        clean_content = str(content)
        ts = datetime.now().isoformat(timespec="seconds")

        with _lock:
            # 1. Write to SQLite
            try:
                with self._db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO conversation_history (session_id, role, content) VALUES (?, ?, ?)",
                        (session_id, role, clean_content),
                    )
                    conn.commit()
            except Exception:
                pass

            # 2. Update JSON for quick access
            messages = self._load_json_messages()
            messages.append({"role": role, "content": clean_content, "timestamp": ts})
            messages = messages[-MAX_JSON_MESSAGES:]

            temp_file = str(self.memory_file) + ".tmp"
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(messages, f, ensure_ascii=False, indent=2)
                os.replace(temp_file, self.memory_file)
            except Exception:
                pass

    def get_recent_history(self, limit: int = 6) -> List[Dict[str, str]]:
        """Return the most recent messages formatted for Ollama chat context."""
        with _lock:
            messages = self._load_json_messages()

        result: List[Dict[str, str]] = []
        for item in messages[-max(0, int(limit)):]:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and content is not None:
                result.append({"role": role, "content": str(content)})
        return result

    def search_history(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search past conversations in SQLite for a specific term."""
        with _lock:
            try:
                with self._db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT role, content, timestamp FROM conversation_history WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
                        (f"%{keyword}%", limit),
                    )
                    rows = cursor.fetchall()
                    return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]
            except Exception:
                return []

    def clear_conversation_memory(self) -> None:
        """Clear conversation memory files."""
        with _lock:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
            try:
                with self._db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM conversation_history")
                    conn.commit()
            except Exception:
                pass

    def _load_json_messages(self) -> List[Dict[str, Any]]:
        if not self.memory_file.exists():
            return []
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    # -------------------------------------------------------------
    # Long-term Fact & Preference Tier
    # -------------------------------------------------------------
    def remember_fact(self, key: str, value: str, category: str = "general") -> None:
        """Save a long-term fact or user preference."""
        clean_key = key.lower().strip()
        with _lock:
            try:
                with self._db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO memory_facts (key, value, category, updated_at) 
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET value=excluded.value, category=excluded.category, updated_at=CURRENT_TIMESTAMP
                        """,
                        (clean_key, str(value), category),
                    )
                    conn.commit()
            except Exception:
                pass

    def recall_fact(self, key: str) -> Optional[str]:
        """Retrieve a stored fact by key."""
        clean_key = key.lower().strip()
        with _lock:
            try:
                with self._db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT value FROM memory_facts WHERE key = ?", (clean_key,))
                    row = cursor.fetchone()
                    return row[0] if row else None
            except Exception:
                return None

    def get_all_facts(self, category: Optional[str] = None) -> Dict[str, str]:
        """Return all stored facts."""
        with _lock:
            try:
                with self._db_connection() as conn:
                    cursor = conn.cursor()
                    if category:
                        cursor.execute("SELECT key, value FROM memory_facts WHERE category = ?", (category,))
                    else:
                        cursor.execute("SELECT key, value FROM memory_facts")
                    return dict(cursor.fetchall())
            except Exception:
                return {}

    # -------------------------------------------------------------
    # Project Workspace Tier
    # -------------------------------------------------------------
    def register_project(self, name: str, path: str, description: str = "") -> None:
        """Register a project folder so Lunaris can reference it by name."""
        clean_name = name.lower().strip()
        with _lock:
            try:
                with self._db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO project_workspaces (name, path, description, last_opened)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(name) DO UPDATE SET path=excluded.path, description=excluded.description, last_opened=CURRENT_TIMESTAMP
                        """,
                        (clean_name, str(path), description),
                    )
                    conn.commit()
            except Exception:
                pass

    def get_project_path(self, name: str) -> Optional[str]:
        clean_name = name.lower().strip()
        with _lock:
            try:
                with self._db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT path FROM project_workspaces WHERE name = ?", (clean_name,))
                    row = cursor.fetchone()
                    return row[0] if row else None
            except Exception:
                return None


# Global singleton instance
memory_manager = MemoryManager()

# Backward-compatibility functional aliases
def store_message(role: str, content: str) -> None:
    memory_manager.store_turn(role, content)

def get_recent_history(limit: int = 6) -> List[Dict[str, str]]:
    return memory_manager.get_recent_history(limit)

def clear_memory() -> None:
    memory_manager.clear_conversation_memory()