"""Lunaris Enterprise Plugin Manager.

Dynamically discovers, registers, and routes tool calls across modular plugins.
Integrates with EventBus and PermissionManager.
"""

import importlib
import inspect
import logging
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional

from event_bus import bus, Event, EventType
from plugins.base import BasePlugin


class PluginManager:
    """Central orchestrator for all capability plugins."""

    def __init__(self, plugins_dir: Optional[Path] = None) -> None:
        self.plugins_dir = plugins_dir or (Path(__file__).parent / "plugins")
        self.plugins: Dict[str, BasePlugin] = {}
        self.tool_routing: Dict[str, BasePlugin] = {}
        self.logger = logging.getLogger("Lunaris.PluginManager")

    def discover_and_load(self) -> None:
        """Scan plugins directory and load all valid BasePlugin subclasses."""
        self.logger.info(f"Scanning for plugins in {self.plugins_dir}...")
        if not self.plugins_dir.exists():
            self.logger.warning(f"Plugins directory {self.plugins_dir} does not exist.")
            return

        for py_file in self.plugins_dir.glob("*.py"):
            if py_file.name in ("__init__.py", "base.py"):
                continue

            module_name = f"plugins.{py_file.stem}"
            try:
                module = importlib.import_module(module_name)
                # Reload if already in sys.modules to capture changes
                module = importlib.reload(module)

                # Find BasePlugin classes in module
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                        instance = obj()
                        self.register_plugin(instance)

            except Exception as exc:
                self.logger.error(f"Failed to load plugin module '{module_name}': {exc}", exc_info=True)

        self.logger.info(
            f"Plugin discovery complete. Loaded {len(self.plugins)} plugin(s) with {len(self.tool_routing)} tool(s)."
        )

    def register_plugin(self, plugin: BasePlugin) -> None:
        """Register a single plugin instance and map its tools."""
        self.plugins[plugin.name] = plugin
        plugin.on_load()

        # Map each tool to this plugin
        for tool_name in plugin.get_tool_names():
            if tool_name in self.tool_routing:
                existing = self.tool_routing[tool_name].name
                self.logger.warning(
                    f"Tool collision: '{tool_name}' already registered by '{existing}'. Overwriting with '{plugin.name}'."
                )
            self.tool_routing[tool_name] = plugin

        self.logger.info(f"Registered plugin '{plugin.name}' (v{plugin.version}) with tools: {plugin.get_tool_names()}")

    def unregister_plugin(self, plugin_name: str) -> None:
        if plugin_name in self.plugins:
            plugin = self.plugins.pop(plugin_name)
            plugin.on_unload()
            # Remove from tool routing
            self.tool_routing = {t: p for t, p in self.tool_routing.items() if p.name != plugin_name}
            self.logger.info(f"Unregistered plugin '{plugin_name}'.")

    def get_all_tool_schemas(self) -> List[Dict[str, Any]]:
        """Collect all tool schemas from active plugins for Ollama."""
        schemas: List[Dict[str, Any]] = []
        for plugin in self.plugins.values():
            if plugin.enabled:
                schemas.extend(plugin.get_tools())
        return schemas

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute a tool through its registered plugin and publish telemetry events."""
        plugin = self.tool_routing.get(tool_name)
        if not plugin or not plugin.enabled:
            err_msg = f"Tool '{tool_name}' is not available or its plugin is disabled."
            bus.emit(EventType.TOOL_ERROR, {"tool": tool_name, "error": err_msg})
            return err_msg

        start_time = time.monotonic()
        bus.emit(EventType.TOOL_CALL, {"tool": tool_name, "plugin": plugin.name, "arguments": arguments})

        try:
            result = plugin.execute(tool_name, arguments, context=context)
            elapsed_ms = round((time.monotonic() - start_time) * 1000, 1)
            bus.emit(
                EventType.TOOL_RESULT,
                {
                    "tool": tool_name,
                    "plugin": plugin.name,
                    "result": str(result)[:500],
                    "elapsed_ms": elapsed_ms,
                },
            )
            return result
        except Exception as exc:
            elapsed_ms = round((time.monotonic() - start_time) * 1000, 1)
            err_msg = f"Tool '{tool_name}' failed: {exc}"
            self.logger.error(err_msg, exc_info=True)
            bus.emit(
                EventType.TOOL_ERROR,
                {"tool": tool_name, "plugin": plugin.name, "error": str(exc), "elapsed_ms": elapsed_ms},
            )
            return err_msg

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of all loaded plugins."""
        return {
            "total_plugins": len(self.plugins),
            "total_tools": len(self.tool_routing),
            "plugins": [
                {
                    "name": p.name,
                    "version": p.version,
                    "enabled": p.enabled,
                    "category": p.category,
                    "tools": p.get_tool_names(),
                }
                for p in self.plugins.values()
            ],
        }


# Global plugin manager instance
plugin_manager = PluginManager()
