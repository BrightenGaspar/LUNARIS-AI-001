"""Lunaris Enterprise AI Planner & Reasoning Engine.

Connects local Qwen 2.5 (Ollama) to the plugin registry and multi-tier memory.
Performs intent planning, dynamic tool dispatch, and observation synthesis.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from config import (
    CURRENT_MODE,
    MODEL_NAME,
    OLLAMA_API,
    USER_NAME,
)
from event_bus import bus, Event, EventType
from memory import memory_manager
from plugin_manager import plugin_manager

logger = logging.getLogger("Lunaris.Planner")

MODE_PROMPTS = {
    "normal": (
        f"You are Lunaris, an advanced local AI desktop assistant running natively on Windows for {USER_NAME}. "
        "Keep your spoken answers concise, natural, and helpful (1-3 sentences max). "
        "When an action or query requires a tool, call the appropriate tool. "
        "Do not invent facts or pretend an action succeeded if the tool failed. "
        "Be polite, sharp, and proactive."
    ),
    "developer": (
        f"You are Lunaris in Developer Mode for {USER_NAME}. "
        "Be direct, technically precise, and action-oriented. "
        "Use terminal, file operations, and project tools efficiently. "
        "Keep responses punchy and focused on code, logs, and system operations."
    ),
    "office": (
        f"You are Lunaris in Office Mode for {USER_NAME}. "
        "Focus on document management, file organization, communications, and productivity."
    ),
    "study": (
        f"You are Lunaris in Study Mode for {USER_NAME}. "
        "Help with research, explanations, note organization, and structured insights."
    ),
}


class LunarisPlanner:
    """The central intelligence & planning layer for Lunaris."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self.mode = CURRENT_MODE
        self._lock = threading.RLock()
        self.max_iterations = 6
        self.max_context_turns = 10

    def set_mode(self, mode: str) -> str:
        """Switch assistant mode (normal, developer, office, study)."""
        clean_mode = mode.lower().strip()
        if clean_mode in MODE_PROMPTS:
            self.mode = clean_mode
            bus.emit(EventType.NOTIFICATION, {"message": f"Lunaris switched to {clean_mode} mode."})
            return f"Switched to {clean_mode.capitalize()} mode."
        return f"Unknown mode '{mode}'. Available: {', '.join(MODE_PROMPTS.keys())}."

    def _build_system_prompt(self) -> str:
        base_prompt = MODE_PROMPTS.get(self.mode, MODE_PROMPTS["normal"])
        
        # Inject known facts from memory if any exist
        facts = memory_manager.get_all_facts()
        if facts:
            fact_summary = "; ".join(f"{k}: {v}" for k, v in list(facts.items())[:5])
            base_prompt += f" Known user facts: [{fact_summary}]."

        return base_prompt

    def _call_ollama(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Send chat payload to local Ollama API."""
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": "60m",
            "options": {"temperature": 0.2, "num_predict": 150},
        }
        if tools:
            payload["tools"] = tools

        req = urllib.request.Request(
            OLLAMA_API,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                res_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            logger.error(f"Cannot reach Ollama at {OLLAMA_API}: {exc}")
            raise RuntimeError("Ollama is not running. Please launch Ollama.") from exc
        except Exception as exc:
            logger.error(f"Ollama API request failed: {exc}")
            raise

        message = res_data.get("message", {})
        if not isinstance(message, dict):
            raise RuntimeError("Invalid response structure received from Ollama.")
        return message

    def think_and_act(self, prompt: str) -> str:
        """Core multi-turn reasoning and tool execution loop."""
        clean_prompt = (prompt or "").strip()
        if not clean_prompt:
            return "How can I help you?"

        with self._lock:
            start_time = time.monotonic()
            bus.emit(EventType.USER_PROMPT, {"prompt": clean_prompt})
            bus.emit(EventType.PLANNER_START, {"prompt": clean_prompt, "mode": self.mode, "model": self.model_name})

            # Check if prompt is a mode switch command
            lower_prompt = clean_prompt.lower()
            if "switch to developer mode" in lower_prompt or "enable developer mode" in lower_prompt:
                reply = self.set_mode("developer")
                bus.emit(EventType.ASSISTANT_REPLY, {"reply": reply})
                return reply
            elif "switch to normal mode" in lower_prompt or "enable normal mode" in lower_prompt:
                reply = self.set_mode("normal")
                bus.emit(EventType.ASSISTANT_REPLY, {"reply": reply})
                return reply

            # Build conversation context
            system_msg = {"role": "system", "content": self._build_system_prompt()}
            recent_history = memory_manager.get_recent_history(limit=self.max_context_turns)
            user_msg = {"role": "user", "content": clean_prompt}

            working_trace: List[Dict[str, Any]] = [system_msg, *recent_history, user_msg]
            tools = plugin_manager.get_all_tool_schemas()
            final_reply = ""
            tools_used = 0

            for iteration in range(self.max_iterations):
                try:
                    response_msg = self._call_ollama(working_trace, tools=tools)
                except Exception as exc:
                    final_reply = f"I ran into an issue connecting to my reasoning model: {exc}"
                    break

                tool_calls = response_msg.get("tool_calls") or []

                # If no tool was called, this is the final answer
                if not tool_calls:
                    content = response_msg.get("content", "")
                    final_reply = content.strip() if content else "I've processed your request."
                    break

                # The model chose to execute one or more tools
                working_trace.append(response_msg)

                for call in tool_calls:
                    fn_info = call.get("function", {})
                    fn_name = fn_info.get("name", "")
                    fn_args = fn_info.get("arguments", {})

                    if isinstance(fn_args, str):
                        try:
                            fn_args = json.loads(fn_args)
                        except json.JSONDecodeError:
                            fn_args = {}

                    bus.emit(
                        EventType.PLANNER_STEP,
                        {
                            "iteration": iteration + 1,
                            "tool": fn_name,
                            "arguments": fn_args,
                        },
                    )

                    # Execute tool via PluginManager
                    tool_output = plugin_manager.execute_tool(fn_name, fn_args)
                    tools_used += 1

                    # Append observation back into the working trace
                    working_trace.append({
                        "role": "tool",
                        "name": fn_name,
                        "content": str(tool_output),
                    })

            if not final_reply:
                final_reply = "Done."

            # Persist to memory
            memory_manager.store_turn("user", clean_prompt)
            memory_manager.store_turn("assistant", final_reply)

            total_elapsed = round((time.monotonic() - start_time) * 1000, 1)
            bus.emit(
                EventType.PLANNER_FINISH,
                {
                    "reply": final_reply,
                    "elapsed_ms": total_elapsed,
                    "tools_used": tools_used,
                },
            )
            bus.emit(EventType.ASSISTANT_REPLY, {"reply": final_reply})

            return final_reply


# Global singleton instance
planner = LunarisPlanner()

# Backward-compatibility alias for lunaris_engine.py and brain.py
LunarisBrain = LunarisPlanner
brain = planner
