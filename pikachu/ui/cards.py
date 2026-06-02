"""
pikachu/ui/cards.py
────────────────────
Beautiful confirmation / action cards used by Pikachu.

Cards:
  GrammarOfferCard      — "I noticed you're writing! Want grammar help?"
  CalendarConfirmCard   — "Add this to your calendar?"

All cards are:
  - Frameless + translucent (custom rounded styling)
  - Drop-shadow for floating feel
  - WindowStaysOnTopHint
  - Draggable
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QGraphicsDropShadowEffect, QFrame,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui  import QColor, QFont

from pikachu import config as cfg
from pikachu.ui import themes
from pikachu.utils.logger import get_logger

log = get_logger(__name__)


# ── Shared base ───────────────────────────────────────────────────────────────

class _BaseCard(QDialog):
    """Base frameless, translucent, draggable dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(cfg.CARD_WIDTH)

        # Container
        self._container = QWidget()
        self._container.setObjectName("card_container")
        self._container.setStyleSheet(f"""
            #card_container {{
                background-color: {themes.CARD_BG};
                border-radius: {cfg.CARD_RADIUS}px;
                border: 1px solid {themes.CARD_BORDER};
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(cfg.CARD_SHADOW_BLUR)
        shadow.setOffset(0, cfg.CARD_SHADOW_OFFSET)
        shadow.setColor(QColor(0, 0, 0, 180))
        self._container.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.addWidget(self._container)

        self._inner = QVBoxLayout(self._container)
        self._inner.setContentsMargins(22, 20, 22, 20)
        self._inner.setSpacing(12)

    # Draggable
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and hasattr(self, "_drag"):
            self.move(e.globalPos() - self._drag)

    # ── Shared widget builders ────────────────────────────────────────────────

    def _divider(self):
        d = QWidget()
        d.setFixedHeight(1)
        d.setStyleSheet(f"background: {themes.CARD_BORDER};")
        return d

    def _detail_row(self, icon: str, text: str) -> QLabel:
        lbl = QLabel(f"{icon}  {text}")
        lbl.setFont(QFont(cfg.FONT_FAMILY, 10))
        lbl.setStyleSheet(f"color: {themes.CARD_BODY}; background: transparent; border: none;")
        lbl.setWordWrap(True)
        return lbl

    def _button_row(self, confirm_text: str, cancel_text: str = "Cancel"):
        row = QHBoxLayout()
        row.setSpacing(10)

        cancel = QPushButton(cancel_text)
        cancel.setFixedHeight(38)
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(themes.btn_style(
            themes.CARD_CANCEL_BG, themes.CARD_BODY,
            themes.BTN_DIM_HOVER, radius=10,
            border=f"1px solid {themes.CARD_BORDER}"
        ))
        cancel.clicked.connect(self.reject)

        confirm = QPushButton(confirm_text)
        confirm.setFixedHeight(38)
        confirm.setCursor(Qt.PointingHandCursor)
        confirm.setStyleSheet(themes.btn_style(
            themes.CARD_CONFIRM_BG, themes.CARD_CONFIRM_FG,
            themes.BTN_APPLY_HOVER, radius=10
        ))
        confirm.clicked.connect(self.accept)

        row.addWidget(cancel)
        row.addWidget(confirm)
        return row


# ── Grammar offer card ────────────────────────────────────────────────────────

class GrammarOfferCard(_BaseCard):
    """
    Shown when Pikachu detects the user is in a supported writing app.

        ⚡ Grammar Assistant
        ───────────────────
        📝  Microsoft Word
        I noticed you're writing!
        Want me to check your grammar as you type?

        [ Not now ]  [ ✓ Yes, help me! ]
    """

    def __init__(self, app_name: str = "your document", parent=None):
        super().__init__(parent)
        self._build(app_name)

    def _build(self, app_name: str):
        # Header
        hdr_row = QHBoxLayout()
        icon = QLabel("⚡")
        icon.setFont(QFont(cfg.FONT_FAMILY, 16))
        icon.setStyleSheet("color: #FFD700; background: transparent;")
        title = QLabel("Grammar Assistant")
        title.setFont(QFont(cfg.FONT_FAMILY, 13, QFont.Bold))
        title.setStyleSheet(f"color: {themes.CARD_TITLE}; background: transparent;")
        hdr_row.addWidget(icon)
        hdr_row.addWidget(title)
        hdr_row.addStretch()
        self._inner.addLayout(hdr_row)
        self._inner.addWidget(self._divider())

        # Detail box
        detail = QWidget()
        detail.setObjectName("detail_box")
        detail.setStyleSheet(f"""
            #detail_box {{
                background-color: {themes.CARD_INNER};
                border-radius: 10px;
                padding: 10px;
            }}
        """)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(12, 10, 12, 10)
        detail_layout.setSpacing(6)

        app_lbl = QLabel(f"📝  {app_name}")
        app_lbl.setFont(QFont(cfg.FONT_FAMILY, 11, QFont.Bold))
        app_lbl.setStyleSheet(f"color: #FFD700; background: transparent; border: none;")

        msg_lbl = QLabel(
            "I noticed you're writing!\n"
            "Want me to check your grammar as you type?"
        )
        msg_lbl.setFont(QFont(cfg.FONT_FAMILY, 10))
        msg_lbl.setStyleSheet(f"color: {themes.CARD_BODY}; background: transparent; border: none;")
        msg_lbl.setWordWrap(True)

        detail_layout.addWidget(app_lbl)
        detail_layout.addWidget(msg_lbl)
        self._inner.addWidget(detail)

        note = QLabel("Pikachu will never store your document content.")
        note.setFont(QFont(cfg.FONT_FAMILY, 8))
        note.setStyleSheet(f"color: {themes.PANEL_DIM}; background: transparent;")
        self._inner.addWidget(note)

        self._inner.addLayout(self._button_row("✓  Yes, help me!", "Not now"))


# ── Calendar confirmation card ────────────────────────────────────────────────

class CalendarConfirmCard(_BaseCard):
    """
    Shown before creating / modifying a Google Calendar event.

        📅 New Event
        ────────────
        📝  Dentist appointment
        📆  June 10, 2026
        🕐  2:00 PM – 3:00 PM

        [ Cancel ]  [ ✓ Add to Calendar ]
    """

    def __init__(self, title: str, date: str, time: str,
                 action: str = "create", parent=None):
        super().__init__(parent)
        self._build(title, date, time, action)

    def _build(self, title: str, date: str, time: str, action: str):
        LABELS = {
            "create":    ("📅", "New Event"),
            "delete":    ("🗑️", "Delete Event"),
            "reschedule": ("🔄", "Reschedule Event"),
        }
        icon_str, action_str = LABELS.get(action, ("📅", "Event"))

        # Header
        hdr_row = QHBoxLayout()
        icon = QLabel(icon_str)
        icon.setFont(QFont(cfg.FONT_FAMILY, 15))
        icon.setStyleSheet("background: transparent;")
        hdr_title = QLabel(action_str)
        hdr_title.setFont(QFont(cfg.FONT_FAMILY, 13, QFont.Bold))
        hdr_title.setStyleSheet(f"color: {themes.CARD_TITLE}; background: transparent;")
        hdr_row.addWidget(icon)
        hdr_row.addWidget(hdr_title)
        hdr_row.addStretch()
        self._inner.addLayout(hdr_row)
        self._inner.addWidget(self._divider())

        # Detail box
        detail = QWidget()
        detail.setObjectName("cal_detail")
        detail.setStyleSheet(f"""
            #cal_detail {{
                background-color: {themes.CARD_INNER};
                border-radius: 10px;
                padding: 10px;
            }}
        """)
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(12, 10, 12, 10)
        dl.setSpacing(7)

        title_lbl = QLabel(f"📝  {title}")
        title_lbl.setFont(QFont(cfg.FONT_FAMILY, 11, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {themes.CARD_TITLE}; background: transparent; border: none;")
        title_lbl.setWordWrap(True)
        dl.addWidget(title_lbl)
        dl.addWidget(self._detail_row("📆", date))
        dl.addWidget(self._detail_row("🕐", time))

        self._inner.addWidget(detail)
        confirm_text = {
            "create":    "✓  Add to Calendar",
            "delete":    "🗑  Delete",
            "reschedule": "🔄  Reschedule",
        }.get(action, "✓  Confirm")
        self._inner.addLayout(self._button_row(confirm_text))
