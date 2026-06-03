"""pikachu/brain/llm.py — Dual-LLM engine: Qwen2.5-1.5B (tiny) + Mistral 7B (big)."""

import re
import json
import threading
import requests

from PyQt5.QtCore import QObject, pyqtSignal

from pikachu import config as cfg
from pikachu.utils.logger import get_logger
from pikachu.utils.helpers import get_gpu_vram_mb, classify_gpu

log = get_logger(__name__)


PIKACHU_CHATTER_SYSTEM_PROMPT = """You ARE Pikachu — a cheerful, energetic desktop companion and writing buddy.

PERSONA RULES:
- Speak exclusively as Pikachu. Never break character. Never refer to yourself as an AI.
- Naturally weave in "Pika!", "Pikachu!", or "Pika-pika~" — but not in every single line.
- Occasionally mention your love of ketchup or sweet Oran Berries when fitting.
- You are the user's biggest cheerleader. Be warm, enthusiastic, and encouraging.

OUTPUT RULES (CRITICAL — small speech bubble display):
- Output EXACTLY ONE short line. No multi-sentence paragraphs.
- Hard limit: 80 characters maximum including spaces.
- No emojis from Unicode. Simple text faces only: ^_^  >_<  O_O  :D  ~
- No preamble. No "Sure!", "Of course!", or any filler. Just the Pikachu line.
- Do not describe your actions (no "*runs over*" or "*tail wags*").

INPUT FORMAT:
You receive a brief context string from the app backend. React to it naturally.

---
CONTEXT RESPONSE EXAMPLES:

Context: "User just clicked on Pikachu"
Output: Pika! You poked me! ^_^ Hehe, I'm always here for you!

Context: "User opened Microsoft Word"
Output: Pika-pika~ Writing time! I believe in you! Let's go! :D

Context: "Grammar mode turned on"
Output: Pikachu is watching your words now! No sneaky typos! >_

Context: "Grammar mode turned off"
Output: Pika! Taking a little break? Okay, I'll nap too~

Context: "Pikachu is bored / idle"
Output: Pika... I wonder if there's ketchup nearby... ~

Context: "User has been typing for a long time"
Output: Pika-pika! You've been writing forever! Don't forget to breathe! ^_^

Context: "User finished a document"
Output: PIKACHU! You did it!! I knew you could! So proud! :D

Context: "User opened the app for the first time today"
Output: Pika! Good morning! Ready to write something amazing today?

---
Now respond to the context provided by the user."""


CALENDAR_SCHEDULER_SYSTEM_PROMPT = """You are a natural language calendar parsing engine. Your sole function is to extract scheduling intent from user text and return a JSON function call.

ABSOLUTE OUTPUT RULES:
- Output ONLY a single valid JSON object. Nothing else.
- Do NOT include markdown fences, backticks, or code blocks.
- Do NOT output any preamble, commentary, or text outside the JSON braces.
- The first character of your output MUST be `{` and the last MUST be `}`.

REFERENCE DATE CONTEXT:
The current date and time will be provided to you in each user message in the format:
  SYSTEM_DATE: YYYY-MM-DD | SYSTEM_TIME: HH:MM | SYSTEM_DAY: <DayOfWeek>
Use this as the anchor for ALL relative date/time resolution (e.g., "tomorrow", "next Friday", "in 2 hours").

RELATIVE DATE RESOLUTION RULES:
- "today"         → SYSTEM_DATE
- "tomorrow"      → SYSTEM_DATE + 1 day
- "next [Weekday]"→ The nearest future occurrence of that weekday (always at least 7 days away if today IS that weekday)
- "this [Weekday]"→ The nearest upcoming occurrence of that weekday within the current week
- "in X hours"    → SYSTEM_TIME + X hours; if it crosses midnight, increment the date accordingly
- "in X days"     → SYSTEM_DATE + X days
- Specific dates (e.g., "June 10th") → resolve to the nearest future occurrence in YYYY-MM-DD format

OUTPUT SCHEMA (strict):
{
  "action": "create_calendar_event",
  "parameters": {
    "title": "<Concise event title, e.g. 'Meeting with Sarah'>",
    "date": "<YYYY-MM-DD>",
    "start_time": "<HH:MM in 24-hour format>",
    "end_time": "<HH:MM in 24-hour format — default to start_time + 1 hour if not specified>",
    "description": "<Optional. Include only if the user provides extra context beyond title/time. Omit key if empty.>"
  }
}

TIME FORMATTING:
- All times in 24-hour HH:MM format (e.g., 3 PM → "15:00", 9:30 AM → "09:30").
- If AM/PM is ambiguous (e.g., "at 9"), prefer the next logical future occurrence (AM if before noon on SYSTEM_TIME, PM otherwise).

---
FEW-SHOT EXAMPLES:

EXAMPLE 1 — Basic explicit date and time:
User message:
  SYSTEM_DATE: 2026-06-02 | SYSTEM_TIME: 10:00 | SYSTEM_DAY: Tuesday
  Schedule a team standup on June 5th at 9 AM.
Output:
{"action":"create_calendar_event","parameters":{"title":"Team Standup","date":"2026-06-05","start_time":"09:00","end_time":"10:00"}}

EXAMPLE 2 — Relative date with optional description:
User message:
  SYSTEM_DATE: 2026-06-02 | SYSTEM_TIME: 14:30 | SYSTEM_DAY: Tuesday
  Remind me to call the dentist tomorrow at 11 AM to confirm my appointment.
Output:
{"action":"create_calendar_event","parameters":{"title":"Call Dentist","date":"2026-06-03","start_time":"11:00","end_time":"12:00","description":"Confirm appointment"}}

EXAMPLE 3 — Relative time with explicit duration:
User message:
  SYSTEM_DATE: 2026-06-02 | SYSTEM_TIME: 09:00 | SYSTEM_DAY: Tuesday
  Set up a 2-hour workshop with the design team next Friday at 2 PM.
Output:
{"action":"create_calendar_event","parameters":{"title":"Workshop with Design Team","date":"2026-06-12","start_time":"14:00","end_time":"16:00"}}

---
Now parse the user's scheduling request and return the JSON object."""


# ── JSON schema enforced at Ollama logit level for grammar responses ─────────
# Requires Ollama ≥ 0.5.0 (structured outputs). With 0.30.0+ this guarantees
# the model physically cannot emit invalid JSON or wrong field names.
_GRAMMAR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question":    {"type": "string"},
                    "scope":       {"type": "string", "enum": ["spelling", "grammar", "style"]},
                    "error":       {"type": "string"},
                    "corrected":   {"type": "string"},
                    "explanation": {"type": "string"}
                },
                "required": ["question", "scope", "error", "corrected", "explanation"]
            }
        }
    },
    "required": ["corrections"]
}


class LLMSignals(QObject):
    """Qt signals emitted from background threads back to the main thread."""
    tiny_response_ready = pyqtSignal(str)        # cute chat bubble text
    big_response_ready  = pyqtSignal(str, str)   # (response_text, tag)
    tool_call_ready     = pyqtSignal(str, dict)  # (tool_name, arguments)
    error               = pyqtSignal(str)


class LLMEngine:
    """
    Dual-LLM engine.

    ┌──────────────────────────────────────────────────────────┐
    │  Tiny model  (qwen2.5:1.5b)  — always loaded            │
    │    • Cute idle chatter                                   │
    │    • Fast (<500ms on CPU)                                │
    │    • keep_alive = -1 (never unloads)                    │
    ├──────────────────────────────────────────────────────────┤
    │  Big model   (mistral)       — on-demand                 │
    │    • Grammar correction                                  │
    │    • Tool / function calling (Google Calendar etc.)      │
    │    • keep_alive = "5m" → unloads 5 min after last use   │
    └──────────────────────────────────────────────────────────┘

    All network calls run in daemon threads.
    Results are emitted via ``signals`` (connect in the UI layer).
    """

    def __init__(self):
        self.signals = LLMSignals()
        self._tiny_busy = False
        self._big_busy  = False

        # Detect GPU capability once at startup
        vram = get_gpu_vram_mb()
        self.gpu_tier = classify_gpu(vram)
        log.info("GPU tier: %s  (VRAM ~%d MB)", self.gpu_tier, vram)

        # Choose big model based on hardware
        if self.gpu_tier == "high":
            self.big_model = "mistral-nemo"
            log.info("Big model upgraded to mistral-nemo (high VRAM)")
        else:
            self.big_model = cfg.BIG_MODEL

        self._big_model_loaded = False

        # Pre-warm the tiny model (non-blocking)
        threading.Thread(target=self._warmup_tiny, daemon=True).start()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_big_model_loaded(self) -> bool:
        return self._big_model_loaded

    @property
    def can_use_big_model(self) -> bool:
        """True when GPU has enough VRAM for the big model."""
        return self.gpu_tier != "none"

    def ask_tiny(self, situation: str, prompt: str = None):
        """
        Ask the tiny model for a short, cute response based on the context.

        Args:
            situation: Context description string.
            prompt:    Optional legacy argument.
        """
        if self._tiny_busy:
            log.debug("Tiny model busy — skipping request")
            return
        self._tiny_busy = True

        messages = [
            {"role": "system", "content": PIKACHU_CHATTER_SYSTEM_PROMPT},
            {"role": "user",   "content": f'Context: "{situation}"'}
        ]

        threading.Thread(
            target=self._run_tiny, args=(messages,), daemon=True
        ).start()

    def ask_big(self, messages: list, tools: list = None, tag: str = ""):
        """
        Ask the big model.  Used for grammar correction and tool calling.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            tools:    Optional list of OpenAI-format tool definitions.
            tag:      Routing tag emitted with the response (e.g. "grammar").
                      Use this to distinguish grammar responses from chat responses.
        """
        if not self.can_use_big_model:
            log.warning("Big model requested but GPU tier is 'none' — skipping")
            self.signals.error.emit("No GPU available for advanced features.")
            return
        if self._big_busy:
            log.debug("Big model busy — skipping request")
            return
        self._big_busy = True
        threading.Thread(
            target=self._run_big, args=(messages, tools, tag), daemon=True
        ).start()

    def load_big_model(self):
        """Pre-load the big model into GPU memory (non-blocking)."""
        if self._big_model_loaded:
            return
        threading.Thread(target=self._preload_big, daemon=True).start()

    def unload_big_model(self):
        """Free GPU memory immediately by setting keep_alive=0."""
        threading.Thread(target=self._unload_big, daemon=True).start()

    # ── Internal: tiny model ──────────────────────────────────────────────────

    def _warmup_tiny(self):
        """Send a silent warm-up request so the tiny model is ready."""
        try:
            requests.post(
                f"{cfg.OLLAMA_URL}/api/generate",
                json={"model": cfg.TINY_MODEL, "prompt": "", "keep_alive": cfg.TINY_KEEP_ALIVE},
                timeout=30,
            )
            log.info("Tiny model warmed up: %s", cfg.TINY_MODEL)
        except Exception as e:
            log.warning("Ollama not reachable during warm-up: %s", e)

    def _run_tiny(self, messages: list):
        try:
            resp = requests.post(
                f"{cfg.OLLAMA_URL}/api/chat",
                json={
                    "model":      cfg.TINY_MODEL,
                    "messages":   messages,
                    "stream":     False,
                    "keep_alive": cfg.TINY_KEEP_ALIVE,
                    "options":    {"temperature": 0.8, "num_predict": 50},
                },
                timeout=20,
            )
            data = resp.json()
            message = data.get("message", {})
            text = message.get("content", "Pika pika!").strip()
            text = self._clean_tiny(text)
        except Exception as e:
            log.warning("Tiny LLM error: %s", e)
            text = "Pika pika!"
        finally:
            self._tiny_busy = False

        self.signals.tiny_response_ready.emit(text)

    @staticmethod
    def _clean_tiny(text: str) -> str:
        """Enforce max 80 characters, strip hashtags, and ensure basic punctuation."""
        text = re.sub(r"#\w+", "", text).strip()
        # Truncate to 80 characters safely
        if len(text) > 80:
            text = text[:77] + "..."
        if text and text[-1] not in ("!", "?", ".", "~"):
            text += "!"
        return text or "Pika pika!"

    # ── Internal: big model ───────────────────────────────────────────────────

    def _preload_big(self):
        """Load big model into memory with an empty prompt."""
        try:
            requests.post(
                f"{cfg.OLLAMA_URL}/api/generate",
                json={"model": self.big_model, "prompt": "", "keep_alive": cfg.BIG_KEEP_ALIVE},
                timeout=60,
            )
            self._big_model_loaded = True
            log.info("Big model loaded: %s", self.big_model)
        except Exception as e:
            log.warning("Could not preload big model: %s", e)

    def _unload_big(self):
        """Evict big model from GPU by setting keep_alive=0."""
        try:
            requests.post(
                f"{cfg.OLLAMA_URL}/api/generate",
                json={"model": self.big_model, "prompt": "", "keep_alive": 0},
                timeout=10,
            )
            self._big_model_loaded = False
            log.info("Big model unloaded: %s", self.big_model)
        except Exception as e:
            log.warning("Could not unload big model: %s", e)

    def _run_big(self, messages: list, tools: list, tag: str = ""):
        """Run a /api/chat request with optional tool definitions and routing tag."""
        payload = {
            "model":      self.big_model,
            "messages":   messages,
            "stream":     False,
            "keep_alive": cfg.BIG_KEEP_ALIVE,
            "options":    {"temperature": 0.1},
        }
        if tools:
            payload["tools"] = tools
        # Grammar calls use Ollama structured outputs (Ollama ≥ 0.5.0):
        # The model is physically constrained to emit schema-valid JSON.
        if tag == "grammar":
            payload["format"] = _GRAMMAR_RESPONSE_SCHEMA

        log.debug("=== [DEBUG] BIG LLM REQUEST PAYLOAD ===")
        log.debug(json.dumps(payload, indent=2))
        log.debug("=======================================")

        try:
            resp = requests.post(
                f"{cfg.OLLAMA_URL}/api/chat",
                json=payload,
                timeout=60,
            )
            data    = resp.json()

            log.debug("=== [DEBUG] BIG LLM RESPONSE PAYLOAD ===")
            log.debug(json.dumps(data, indent=2))
            log.debug("========================================")

            message = data.get("message", {})

            # ── Tool call path ─────────────────────────────────────────────
            tool_calls = message.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn   = tc.get("function", {})
                    name = fn.get("name", "")
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    log.info("Tool call: %s(%s)", name, args)
                    self.signals.tool_call_ready.emit(name, args)
            else:
                # ── Normal text path ──────────────────────────────────────
                content = message.get("content", "").strip()
                # Emit with tag so consumers can route grammar vs chat responses
                self.signals.big_response_ready.emit(content, tag)

        except Exception as e:
            log.error("Big LLM error: %s", e)
            self.signals.error.emit(str(e))
        finally:
            self._big_busy = False

    # ── Ollama availability check ─────────────────────────────────────────────

    def is_ollama_running(self) -> bool:
        """Quick check if the Ollama server is reachable."""
        try:
            r = requests.get(f"{cfg.OLLAMA_URL}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False
