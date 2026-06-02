"""
pikachu/main.py
────────────────
Orchestrator — wires all modules together and starts the Qt event loop.

Module graph:
  PikachuWindow ←── MovementEngine ←── CollisionDetector
       ↑                                      ↑
  SpeechBubble                         AppMonitor (bg thread)
  CorrectionPanel ←── GrammarEngine ←── TextReader
  GrammarOfferCard ←── AppMonitor
  CalendarConfirmCard ←── LLMEngine (tool calls)
  LLMEngine ←── PikachuContext
"""

import sys
import ctypes
import ctypes.wintypes

from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtCore    import QTimer

from pikachu import config as cfg
from pikachu.brain.context    import PikachuContext
from pikachu.brain.llm        import LLMEngine
from pikachu.brain.grammar    import GrammarEngine
from pikachu.character.sprite_2d import Sprite2D
from pikachu.movement.collision  import CollisionDetector
from pikachu.movement.engine     import MovementEngine, ESCAPING
from pikachu.ui.window           import PikachuWindow
from pikachu.ui.bubble           import SpeechBubble
from pikachu.ui.correction_panel import CorrectionPanel
from pikachu.ui.cards            import GrammarOfferCard, CalendarConfirmCard
from pikachu.utils.app_monitor   import AppMonitor
from pikachu.utils.logger        import get_logger

log = get_logger(__name__)


class PikachuApp:
    """
    Top-level application object.
    Owns all subsystems and wires their signals/callbacks together.
    """

    def __init__(self, app: QApplication):
        self._app = app

        screen      = app.primaryScreen().geometry()
        screen_w    = screen.width()
        screen_h    = screen.height()

        log.info("Screen: %dx%d", screen_w, screen_h)

        # ── Character ─────────────────────────────────────────────────────────
        self._sprite    = Sprite2D()
        sprite_w, sprite_h = self._sprite.get_bounds()

        # ── Movement ──────────────────────────────────────────────────────────
        self._collision = CollisionDetector(screen_w, screen_h, sprite_w, sprite_h)
        self._movement  = MovementEngine(screen_w, screen_h, sprite_w, sprite_h)

        # ── Window (main Pikachu label) ────────────────────────────────────────
        self._window    = PikachuWindow(screen_w, screen_h)
        self._window.set_pixmap(self._sprite.get_pixmap())

        # ── Speech bubble ─────────────────────────────────────────────────────
        self._bubble    = SpeechBubble(screen_w, screen_h)

        # ── Floating correction panel ─────────────────────────────────────────
        self._panel     = CorrectionPanel(screen_w, screen_h)

        # ── Brain ─────────────────────────────────────────────────────────────
        self._context   = PikachuContext()
        self._llm       = LLMEngine()
        self._grammar   = GrammarEngine(self._llm)

        # ── App monitor ───────────────────────────────────────────────────────
        self._monitor   = AppMonitor()

        # Track last writing app for grammar mode
        self._current_class_name = ""
        self._current_app_name   = ""
        self._prev_state         = ""

        # ── Wire everything ───────────────────────────────────────────────────
        self._connect_signals()

        # ── Start subsystems ──────────────────────────────────────────────────
        self._monitor.start()

        # Global shortcut — Ctrl+Shift+P via context menu signal
        self._window.signals.grammar_toggle.connect(self._on_grammar_toggle)

        # ── Main timer ────────────────────────────────────────────────────────
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(cfg.TICK_MS)

        log.info("Pikachu is alive!")

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self):
        # Click → say something
        self._window.signals.clicked.connect(self._on_clicked)

        # LLM responses → speech bubble
        self._llm.signals.tiny_response_ready.connect(self._bubble.show_text)
        self._llm.signals.big_response_ready.connect(self._on_big_response)
        self._llm.signals.tool_call_ready.connect(self._on_tool_call)
        self._llm.signals.error.connect(self._on_llm_error)

        # Grammar corrections → panel + bubble
        self._grammar.signals.correction_ready.connect(self._on_corrections_ready)
        self._grammar.signals.status_changed.connect(self._on_grammar_status_changed)
        self._grammar.signals.gpu_released.connect(self._on_gpu_released)

        # App monitor → writing app detection
        self._monitor.signals.writing_app_detected.connect(self._on_writing_app)
        self._monitor.signals.writing_app_closed.connect(self._on_writing_app_closed)

        # Correction panel actions
        self._panel.apply_correction.connect(self._on_apply_correction)
        self._panel.dismiss_correction.connect(self._on_dismiss_correction)
        self._panel.closed.connect(lambda: self._grammar.deactivate())

    # ── Main tick ─────────────────────────────────────────────────────────────

    def _tick(self):
        rx, ry, flip, state, idle_talk_fired = self._movement.update(self._collision)

        # Sprite direction
        self._window.set_pixmap(self._sprite.get_pixmap(flip=flip))
        self._window.move(rx, ry)

        # Z-order
        _, fullscreen = self._collision.get_foreground_info()
        self._window.update_zorder(fullscreen)

        # Idle talk
        if idle_talk_fired:
            self._llm.ask_tiny("Pikachu is bored / idle")

        # "Escaped!" comment
        if self._prev_state == ESCAPING and state != ESCAPING:
            self._llm.ask_tiny("I just escaped from behind a window!")

        self._prev_state = state

        # Bubble follows Pikachu
        sprite_w, _ = self._sprite.get_bounds()
        self._bubble.tick(rx, ry, sprite_w)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_clicked(self):
        self._context.record_event("clicked")
        self._llm.ask_tiny("User just clicked on Pikachu")

    def _on_writing_app(self, app_name: str):
        """User switched to a writing app — offer grammar help."""
        self._current_app_name   = app_name
        self._current_class_name = next(
            (cls for cls, name in cfg.WRITING_APPS.items() if name == app_name), ""
        )
        self._context.set_app(app_name)

        if not self._grammar.is_active:
            self._show_grammar_offer(app_name)
        else:
            # Word got focus back, show panel again if we have active corrections
            rect, _ = self._collision.get_foreground_info()
            self._panel.restore_visibility(window_rect=rect)

    def _on_writing_app_closed(self):
        """Writing app lost focus — hide panel, but keep Mistral loaded in memory."""
        self._current_app_name   = ""
        self._current_class_name = ""
        self._context.set_app("")
        # We temporarily hide the panel so it doesn't overlap other active windows,
        # but we keep Mistral loaded in memory (self._grammar stays active)
        self._panel.hide()

    def _on_gpu_released(self):
        """Mistral was automatically unloaded to free VRAM for other GPU tasks."""
        self._panel.clear()
        self._llm.ask_tiny("Pikachu released the GPU for other heavy tasks")

    def _show_grammar_offer(self, app_name: str):
        """Show the GrammarOfferCard and handle the response."""
        card = GrammarOfferCard(app_name)
        if card.exec_() == QDialog.Accepted:
            self._grammar.activate(self._current_app_name, self._current_class_name)
            self._llm.ask_tiny(f"User opened {app_name} and grammar mode turned on")
        else:
            self._llm.ask_tiny("Grammar mode declined")

    def _on_grammar_toggle(self):
        """Ctrl+Shift+P — toggle grammar mode."""
        if self._grammar.is_active:
            self._grammar.deactivate()
            self._panel.clear()
            self._llm.ask_tiny("Grammar mode turned off")
        else:
            if self._current_app_name:
                self._grammar.activate(self._current_app_name, self._current_class_name)
                self._llm.ask_tiny("Grammar mode turned on")

    def _on_grammar_status_changed(self, active: bool):
        self._context.set_grammar_mode(active)

    def _on_corrections_ready(self, corrections: list):
        """New batch of corrections: show in panel + announce via bubble."""
        if not corrections:
            return

        # Show first correction in speech bubble (cute in-character format requested by user)
        first = corrections[0]
        scope_text = first.scope.lower()
        if scope_text in ["spelling", "grammar"]:
            short = (
                "Oh! You've made a mistake.\n"
                f"{scope_text}: {first.error} -> {first.corrected}"
            )
        else:  # style ("just not well written")
            short = (
                "You can say that instead:\n"
                f"{first.corrected}"
            )
        self._bubble.show_text(short)

        # Show all corrections in the floating panel
        rect, _ = self._collision.get_foreground_info()
        self._panel.show_corrections(corrections, window_rect=rect)

    def _on_apply_correction(self, correction):
        """User clicked Apply — use COM to replace text in document."""
        log.info("Apply: '%s' → '%s'", correction.original, correction.corrected)
        success = self._grammar.replace_text(correction)
        if success:
            log.info("Successfully applied text correction to Word document.")
            # Force snapshot update to prevent re-triggering
            self._grammar._last_text = self._grammar._reader.read_active_app(self._grammar._class_name)
        else:
            log.warning("Failed to apply text correction to Word document.")
        self._llm.ask_tiny("User corrected a grammar mistake")

    def _on_dismiss_correction(self, correction):
        log.info("Dismissed correction: '%s'", correction.original)
        self._grammar.dismiss_correction(correction)

    def _on_big_response(self, text: str):
        """Non-tool response from Mistral (e.g. general query)."""
        if self._grammar.is_active:
            return  # The grammar engine is handling this response; don't show it as a chat bubble.
        self._bubble.show_text(text[:80])

    def _on_tool_call(self, tool_name: str, args: dict):
        """Mistral wants to call a calendar function — show confirmation card."""
        log.info("Tool call: %s(%s)", tool_name, args)

        if tool_name == "create_calendar_event":
            date = args.get("date", "")
            time = f"{args.get('start_time', '')} – {args.get('end_time', '')}"
            card = CalendarConfirmCard(
                title  = args.get("title", "Event"),
                date   = date,
                time   = time,
                action = "create",
            )
            if card.exec_() == QDialog.Accepted:
                self._execute_calendar_tool(tool_name, args)

        elif tool_name == "delete_calendar_event":
            card = CalendarConfirmCard(
                title  = args.get("event_id", "this event"),
                date   = "", time = "",
                action = "delete",
            )
            if card.exec_() == QDialog.Accepted:
                self._execute_calendar_tool(tool_name, args)

    def _execute_calendar_tool(self, tool_name: str, args: dict):
        """Actually call the Calendar API after user confirmation."""
        from pikachu.integrations.calendar import CalendarService
        try:
            svc = CalendarService()
            if not svc.is_authenticated():
                self._bubble.show_text("Need Calendar access first!")
                return
            if tool_name == "create_calendar_event":
                url = svc.create_event(**args)
                if url:
                    self._bubble.show_text("Added to your calendar!")
            elif tool_name == "delete_calendar_event":
                svc.delete_event(args.get("event_id", ""))
                self._bubble.show_text("Event deleted!")
        except Exception as e:
            log.error("Calendar tool error: %s", e)
            self._bubble.show_text("Oops, Calendar error!")

    def _on_llm_error(self, msg: str):
        log.warning("LLM error: %s", msg)
        # Silently ignore LLM errors (Ollama might not be running)


def run():
    """Entry point — called from pikachu_widget.py or directly."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    pikachu = PikachuApp(app)   # noqa: F841 — keep reference alive

    sys.exit(app.exec_())
