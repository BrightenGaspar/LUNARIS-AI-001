"""Lunaris Enterprise Voice Background Service."""

import re
import sys
import time
import urllib.error
import speech_recognition as sr

from config import CONFIRMATION_TIMEOUT_SEC, USER_NAME
from event_bus import bus, Event, EventType
from permissions import permission_guard
from planner import planner
from plugin_manager import plugin_manager
from voice.earbuds import detect_preferred_input_device
from voice.speech import listener
from voice.tts import speaker
from voice.wakeword import wake_detector

_AFFIRMATIVE_CONFIRMATIONS = {"yes confirm", "confirm", "yes", "proceed"}


def _normalize_confirmation(text: str) -> str:
    return re.sub(r"[^a-z ]", "", text.lower()).strip()


def _request_voice_approval(message: str) -> bool:
    speaker.speak(f"{message} Say 'yes confirm' to approve.")
    bus.emit(EventType.VOICE_STATE, {"state": "awaiting_confirmation", "prompt": message})
    audio = listener.capture_pcm_stream(
        min_record_sec=0.2,
        max_record_sec=float(CONFIRMATION_TIMEOUT_SEC),
    )
    transcript = listener.transcribe(audio)
    return (
        transcript is not None
        and _normalize_confirmation(transcript) in _AFFIRMATIVE_CONFIRMATIONS
    )


def run_service_loop() -> None:
    print("=" * 60)
    print("LUNARIS ENTERPRISE v2.0 - VOICE SERVICE ACTIVE")
    print("=" * 60)
    
    # Initialize and load capability plugins
    plugin_manager.discover_and_load()
    permission_guard.set_prompt_handler(_request_voice_approval)
    
    dev_idx, dev_name = detect_preferred_input_device()
    print(f"Audio Input Device: [{dev_idx}] {dev_name}")
    
    bus.emit(EventType.SYSTEM_READY, {"service": "voice", "device": dev_name})
    speaker.speak(f"Lunaris enterprise online. Listening on {dev_name.split('(')[0].strip()}.")

    follow_up_until = 0.0
    follow_up_timeout = 8.0

    while True:
        try:
            audio = listener.capture_pcm_stream()
            transcript = listener.transcribe(audio)
            if not transcript:
                continue

            print(f"\n[Heard]: {transcript}", flush=True)
            clean_prompt = transcript
            has_wake = wake_detector.has_wake_word(transcript)
            is_follow_up = time.monotonic() < follow_up_until

            if has_wake:
                clean_prompt = listener.strip_wake_word(transcript)
                if not clean_prompt.strip():
                    speaker.speak(f"Yes, {USER_NAME}?")
                    follow_up_until = time.monotonic() + follow_up_timeout
                    continue
            elif is_follow_up:
                clean_prompt = transcript
            else:
                continue

            print(f"[Executing Directive]: {clean_prompt}", flush=True)
            reply = planner.think_and_act(clean_prompt)
            speaker.speak(reply)
            follow_up_until = time.monotonic() + follow_up_timeout

        except KeyboardInterrupt:
            speaker.speak("Lunaris audio link paused.")
            break
        except (OSError, RuntimeError, sr.RequestError, urllib.error.URLError) as exc:
            message = f"Lunaris service error: {type(exc).__name__}: {exc}"
            print(message, file=sys.stderr, flush=True)
            time.sleep(1)


if __name__ == "__main__":
    run_service_loop()
