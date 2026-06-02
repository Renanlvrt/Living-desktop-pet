"""pikachu/brain/context.py — Pikachu's memory and mood tracking."""

import time
from collections import deque
from pikachu import config as cfg
from pikachu.utils.logger import get_logger

log = get_logger(__name__)

# ── Mood constants ────────────────────────────────────────────────────────────
MOOD_HAPPY     = "happy"
MOOD_BORED     = "bored"
MOOD_SURPRISED = "surprised"
MOOD_FOCUSED   = "focused"
MOOD_EXCITED   = "excited"


class PikachuContext:
    """
    Tracks Pikachu's current mood, recent event history, and the active
    application so the LLM engine can build context-aware prompts.
    """

    def __init__(self):
        self.mood: str             = MOOD_HAPPY
        self.active_app: str       = ""
        self.grammar_mode: bool    = False
        self._events: deque        = deque(maxlen=10)  # last 10 events
        self._messages: deque      = deque(maxlen=5)   # last 5 chat turns

    # ── Events ────────────────────────────────────────────────────────────────

    def record_event(self, event: str):
        """Log a named event, e.g. 'clicked', 'escaped', 'grammar_corrected'."""
        self._events.append({"ts": time.time(), "event": event})
        log.debug("Event recorded: %s", event)

        # Mood transitions
        if event == "clicked":
            self.mood = MOOD_SURPRISED
        elif event == "escaped_window":
            self.mood = MOOD_EXCITED
        elif event in ("grammar_activated", "grammar_corrected"):
            self.mood = MOOD_FOCUSED
        elif event == "idle_too_long":
            self.mood = MOOD_BORED

    def record_message(self, role: str, text: str):
        """Store a conversation turn for multi-turn continuity."""
        self._messages.append({"role": role, "text": text})

    # ── Prompt builder ────────────────────────────────────────────────────────

    def build_tiny_prompt(self, situation: str) -> str:
        """
        Build the full prompt string for the tiny chatter model.
        Keeps the system prompt small for fast inference.
        """
        mood_desc = {
            MOOD_HAPPY:     "cheerful and playful",
            MOOD_BORED:     "a little bored and restless",
            MOOD_SURPRISED: "surprised and a bit flustered",
            MOOD_FOCUSED:   "focused and helpful",
            MOOD_EXCITED:   "excited and energetic",
        }.get(self.mood, "cheerful")

        return (
            f"You are Pikachu, a tiny cute Pokémon living on someone's desktop. "
            f"Right now you feel {mood_desc}. "
            f"RULES: max 10 words total. Max 1 emoji (optional). "
            f"No hashtags. No punctuation except ! or ?. Cute and expressive. "
            f"Situation: {situation}"
        )

    def build_big_system_prompt(self) -> str:
        """
        Build the system prompt for the big (Mistral) model used in
        grammar correction and tool-calling tasks.
        """
        app_line = f" The user is currently working in {self.active_app}." if self.active_app else ""
        return (
            "You are Pikachu, an intelligent desktop assistant and Pokémon companion."
            + app_line
            + " You are helpful, concise, and always keep Pikachu's cheerful personality."
        )

    # ── Accessors ─────────────────────────────────────────────────────────────

    def set_app(self, app_name: str):
        self.active_app = app_name
        log.info("Active app → %s", app_name)

    def set_grammar_mode(self, active: bool):
        self.grammar_mode = active
        self.mood = MOOD_FOCUSED if active else MOOD_HAPPY
        self.record_event("grammar_activated" if active else "grammar_deactivated")

    @property
    def recent_events(self) -> list:
        return list(self._events)
