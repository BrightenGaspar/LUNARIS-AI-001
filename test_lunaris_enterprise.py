"""Comprehensive verification test suite for Lunaris Enterprise v2.0."""

import unittest
import os
import sys

# Ensure C:\Lunaris is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from event_bus import bus, Event, EventType
from memory import memory_manager
from plugin_manager import plugin_manager
from planner import planner
from voice.earbuds import detect_preferred_input_device


class TestLunarisEnterprise(unittest.TestCase):

    def test_01_event_bus(self):
        """Verify EventBus publish and subscribe functionality."""
        received = []

        def on_event(evt):
            received.append(evt.data.get("msg"))

        bus.subscribe(EventType.USER_PROMPT, on_event)
        bus.emit(EventType.USER_PROMPT, {"msg": "hello_event_bus"})
        
        # Give async queue a moment or check sync
        import time
        time.sleep(0.1)
        self.assertIn("hello_event_bus", received)

    def test_02_memory_manager(self):
        """Verify multi-tier memory persistence and fact recall."""
        # Test conversation storage
        memory_manager.store_turn("user", "Test message from unit test")
        history = memory_manager.get_recent_history(limit=5)
        self.assertTrue(len(history) > 0)
        self.assertEqual(history[-1]["role"], "user")

        # Test long-term facts
        memory_manager.remember_fact("favorite_editor", "VS Code", category="preference")
        fact = memory_manager.recall_fact("favorite_editor")
        self.assertEqual(fact, "VS Code")

        # Test project workspace
        memory_manager.register_project("lunaris_core", "C:\\Lunaris", "Core desktop assistant")
        path = memory_manager.get_project_path("lunaris_core")
        self.assertEqual(path, "C:\\Lunaris")

    def test_03_plugin_discovery(self):
        """Verify plugin manager discovery and tool registration."""
        plugin_manager.discover_and_load()
        status = plugin_manager.get_status()
        
        self.assertGreaterEqual(status["total_plugins"], 6)
        self.assertGreaterEqual(status["total_tools"], 15)
        
        tool_names = list(plugin_manager.tool_routing.keys())
        self.assertIn("get_system_vitals", tool_names)
        self.assertIn("open_application", tool_names)
        self.assertIn("search_files", tool_names)
        self.assertIn("search_web", tool_names)

    def test_04_windows_plugin(self):
        """Verify system vitals execution."""
        vitals = plugin_manager.execute_tool("get_system_vitals", {})
        self.assertIn("CPU Load", str(vitals))
        self.assertIn("RAM", str(vitals))

    def test_05_files_plugin_search(self):
        """Verify file search capability."""
        search_res = plugin_manager.execute_tool("search_files", {"pattern": "*.py", "directory": "C:\\Lunaris", "max_results": 5})
        self.assertIn("matching file(s)", str(search_res))

    def test_06_earbuds_detection(self):
        """Verify smart Bluetooth earbuds / mic detection."""
        idx, name = detect_preferred_input_device()
        self.assertIsNotNone(name)
        print(f"\n[Verified Audio Device]: [{idx}] {name}")

    def test_07_planner_mode_switching(self):
        """Verify AI modes support in planner."""
        reply = planner.set_mode("developer")
        self.assertEqual(planner.mode, "developer")
        planner.set_mode("normal")
        self.assertEqual(planner.mode, "normal")


if __name__ == "__main__":
    unittest.main()
