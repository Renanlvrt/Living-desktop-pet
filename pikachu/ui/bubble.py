"""pikachu/ui/bubble.py — Speech bubble widget with typewriter effect."""

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore    import Qt
from PyQt5.QtGui     import QFont

from pikachu import config as cfg
from pikachu.ui import themes


class SpeechBubble(QWidget):
    """
    Frameless, transparent speech bubble window that sits above Pikachu.

    Features:
    - Typewriter character-by-character reveal
    - Blinking cursor while typing
    - Auto-hides after BUBBLE_SHOW_MS milliseconds
    - Follows Pikachu's position every tick
    """

    def __init__(self, screen_w: int, screen_h: int):
        super().__init__()
        self._screen_w  = screen_w
        self._screen_h  = screen_h

        # Window setup
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_StyledBackground, True)

        # Layout to wrap the child label cleanly
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Child QLabel for drawing background and text
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setFont(QFont(cfg.FONT_FAMILY_MONO, 9, QFont.Bold))
        self._label.setStyleSheet(themes.BUBBLE_STYLE)
        self._label.setMaximumWidth(cfg.BUBBLE_MAX_WIDTH)
        layout.addWidget(self._label)

        self.hide()

        # Typewriter state
        self._full_text  = ""
        self._char_index = 0
        self._char_delay = 0
        self._ticks_left = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def show_text(self, text: str):
        """Start displaying *text* with the typewriter effect."""
        self._full_text  = text
        self._char_index = 0
        self._char_delay = 0
        self._ticks_left = cfg.BUBBLE_SHOW_MS // cfg.TICK_MS
        self._label.setText("")
        self._label.adjustSize()
        self.adjustSize()
        self.show()

    def tick(self, pikachu_x: int, pikachu_y: int, sprite_w: int):
        """
        Called every game tick.
        Advances the typewriter and repositions the bubble above Pikachu.
        """
        if self._ticks_left <= 0:
            return

        self._ticks_left -= 1

        # Typewriter advance
        if self._char_index < len(self._full_text):
            self._char_delay -= 1
            if self._char_delay <= 0:
                self._char_index += 1
                cursor = "_" if self._char_index < len(self._full_text) else ""
                self._label.setText(self._full_text[: self._char_index] + cursor)
                self._label.adjustSize()
                self.adjustSize()
                self._char_delay = cfg.TYPE_SPEED
        else:
            self._label.setText(self._full_text)   # remove blinking cursor when done

        self._reposition(pikachu_x, pikachu_y, sprite_w)

        if self._ticks_left == 0:
            self.hide()

    def force_hide(self):
        self._ticks_left = 0
        self.hide()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _reposition(self, px: int, py: int, sprite_w: int):
        bw = self.width()
        bh = self.height()
        bx = px + sprite_w // 2 - bw // 2
        by = py - bh - 10
        # Clamp to screen
        bx = max(0, min(bx, self._screen_w - bw))
        by = max(0, by)
        self.move(bx, by)
