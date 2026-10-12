"""Re-export wake detector from voice subsystem."""
from voice.wakeword import wake_detector, WakeWordDetector

__all__ = ["wake_detector", "WakeWordDetector"]
