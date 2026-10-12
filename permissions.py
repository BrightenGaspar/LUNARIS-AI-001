import os
from pathlib import Path
from typing import Callable, Optional

from config import (
    ALLOWED_FOLDERS,
    REQUIRE_CONFIRMATION_FOR_DESTRUCTIVE,
)

SENSITIVE_ACTIONS = {
    "shutdown": "Shut down the computer",
    "restart": "Restart the system",
    "close_application": "Close a running application",
    "delete": "Delete filesystem items",
    "write_file": "Write or overwrite a file",
    "purchase": "Execute online checkout or financial transactions",
    "format": "Disk format operation",
    "terminal_exec": "Execute arbitrary shell script",
}


class PermissionManager:
    def __init__(self):
        self._pending_confirmation: Optional[str] = None
        self._prompt_user_fn: Optional[Callable[[str], bool]] = None

    def set_prompt_handler(
        self, prompt_user_fn: Optional[Callable[[str], bool]]
    ) -> None:
        """Configure the interactive confirmation provider."""
        self._prompt_user_fn = prompt_user_fn

    def is_path_allowed(self, target_path: str) -> bool:
        """Check whether a path is inside one of the approved folders."""
        target = Path(os.path.realpath(target_path))
        for folder in ALLOWED_FOLDERS:
            allowed = Path(os.path.realpath(folder))
            try:
                target.relative_to(allowed)
            except ValueError:
                continue
            return True
        return False

    def requires_approval(self, action_key: str) -> bool:
        """Check whether an action requires explicit user authorization."""
        return (
            REQUIRE_CONFIRMATION_FOR_DESTRUCTIVE
            and action_key.lower() in SENSITIVE_ACTIONS
        )

    def request_approval(
        self,
        action_key: str,
        prompt_user_fn: Optional[Callable[[str], bool]] = None,
    ) -> bool:
        """Ask the UI or voice interface to obtain user consent."""
        key = action_key.lower().strip()
        if not self.requires_approval(key):
            return False
        prompt = prompt_user_fn or self._prompt_user_fn
        if prompt is None:
            return False
        description = SENSITIVE_ACTIONS.get(key, action_key)
        message = f"Warning: Authorization requested to {description}. Do you confirm?"
        return bool(prompt(message))


permission_guard = PermissionManager()
