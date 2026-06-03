"""
pikachu/ui/correction_panel.py
───────────────────────────────
Floating correction panel — the "Grammarly sidebar" for Pikachu.

Layout (right edge of screen, next to the active writing window):

  ╭──────────────────────────────────╮
  │  ⚡ Pikachu's Grammar Notes       │  ← header + close button
  │  ─────────────────────────────   │
  │  ❌ "their going to the store"   │  ← correction card 1
  │  ✅  "They're going to the store" │
  │     [ Apply ]  [ Dismiss ]       │
  │  ─────────────────────────────   │
  │  ❌ "he dont know"               │  ← correction card 2
  │  ✅  "he doesn't know"           │
  │     [ Apply ]  [ Dismiss ]       │
  ╰──────────────────────────────────╯

The panel is:
- Frameless + transparent background (rounded corners via stylesheet)
- Always-on-top but click-through when no correction is hovered
- Positioned to the right of the active writing window rect
- Falls back to the right edge of the screen if the window is maximised
- Emits signals when the user applies or dismisses a correction
"""

from dataclasses import dataclass
from typing import List, Callable

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGraphicsDropShadowEffect, QSizePolicy,
)
from PyQt5.QtCore    import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect
from PyQt5.QtGui     import QColor, QFont, QCursor

from pikachu import config as cfg
from pikachu.ui import themes
from pikachu.utils.logger import get_logger

log = get_logger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Correction:
    """A single grammar correction suggested by Mistral."""
    question:    str       # the sentence/context containing the error
    scope:       str       # "spelling", "grammar", or "style"
    error:       str       # original erroneous text/phrase
    corrected:   str       # corrected text/phrase
    explanation: str       # more details
    index:       int = 0   # unique id within the current batch

    @property
    def original(self) -> str:
        return self.error


# ── Individual correction card ────────────────────────────────────────────────

class CorrectionCard(QFrame):
    """
    A single card inside the correction panel showing one error + fix.
    """
    apply_clicked   = pyqtSignal(object)   # emits the Correction
    dismiss_clicked = pyqtSignal(object)
    show_clicked    = pyqtSignal(object)

    def __init__(self, correction: Correction, parent=None):
        super().__init__(parent)
        self.correction = correction
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("correction_card")
        self.setStyleSheet(f"""
            #correction_card {{
                background-color: {themes.PANEL_BG_INNER};
                border: 1px solid {themes.PANEL_BORDER};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        font_body = QFont(cfg.FONT_FAMILY, 9)
        font_bold = QFont(cfg.FONT_FAMILY, 9, QFont.Bold)
        font_small_bold = QFont(cfg.FONT_FAMILY, 8, QFont.Bold)

        # ── Header ────────────────────────────────────────────────────────────
        header_lbl = QLabel(f"✏️ {self.correction.scope.title()} Suggestion")
        header_lbl.setFont(font_small_bold)
        header_lbl.setStyleSheet(f"color: {themes.PANEL_DIM}; background: transparent;")
        layout.addWidget(header_lbl)
        
        question_text = self.correction.question
        error_text = self.correction.error

        # ── Original (wrong) ──────────────────────────────────────────────────
        if self.correction.scope != "style":
            orig_row = QHBoxLayout()
            orig_label = QLabel("●")
            orig_label.setFont(font_bold)
            orig_label.setStyleSheet(f"color: {themes.PANEL_ERROR_FG}; background: transparent;")
            orig_label.setFixedWidth(16)
            orig_label.setAlignment(Qt.AlignTop)
            
            if error_text and error_text in question_text:
                # Use HTML to underline just the error
                styled_q = question_text.replace(
                    error_text, 
                    f'<u style="text-decoration-color: {themes.PANEL_ERROR_FG};">{error_text}</u>'
                )
            else:
                styled_q = question_text
                
            orig_text = QLabel(styled_q)
            orig_text.setFont(font_body)
            orig_text.setStyleSheet(f"color: {themes.PANEL_BODY_FG}; background: transparent;")
            orig_text.setWordWrap(True)
            
            orig_row.addWidget(orig_label)
            orig_row.addWidget(orig_text, 1)
            layout.addLayout(orig_row)

        # ── Corrected ─────────────────────────────────────────────────────────
        fix_row = QHBoxLayout()
        fix_label = QLabel("✓")
        fix_label.setFont(font_bold)
        fix_label.setStyleSheet(f"color: {themes.PANEL_OK_FG}; background: transparent;")
        fix_label.setFixedWidth(16)
        fix_label.setAlignment(Qt.AlignTop)

        if self.correction.scope == "style":
            styled_fix = f'You can say this instead:\n{self.correction.corrected}'
            fix_color = themes.PANEL_OK_FG
        else:
            if error_text and error_text in question_text:
                styled_fix = question_text.replace(error_text, self.correction.corrected)
            else:
                styled_fix = self.correction.corrected
            fix_color = themes.PANEL_OK_FG
            
        fix_text = QLabel(styled_fix)
        fix_text.setFont(font_body)
        fix_text.setStyleSheet(f"color: {fix_color}; background: transparent;")
        fix_text.setWordWrap(True)
        
        fix_row.addWidget(fix_label)
        fix_row.addWidget(fix_text, 1)
        layout.addLayout(fix_row)

        # ── Explanation (Expandable) ──────────────────────────────────────────
        if self.correction.explanation:
            self.exp_btn = QPushButton("▶ More details...")
            self.exp_btn.setCursor(Qt.PointingHandCursor)
            self.exp_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {themes.PANEL_DIM};
                    background: transparent;
                    border: none;
                    text-align: left;
                    font-size: 11px;
                    padding: 0;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    color: {themes.PANEL_TITLE_FG};
                }}
            """)
            
            self.exp_lbl = QLabel(self.correction.explanation)
            self.exp_lbl.setFont(QFont(cfg.FONT_FAMILY, 8))
            self.exp_lbl.setStyleSheet(f"color: {themes.PANEL_BODY_FG}; background: transparent; padding-left: 10px;")
            self.exp_lbl.setWordWrap(True)
            self.exp_lbl.setVisible(False)
            
            def toggle_exp():
                is_visible = self.exp_lbl.isVisible()
                self.exp_lbl.setVisible(not is_visible)
                self.exp_btn.setText("▼ Hide details" if not is_visible else "▶ More details...")
                
                # Resize the panel itself to fit the newly revealed/hidden content
                p = self.parent()
                while p:
                    if hasattr(p, "_cards_layout") and hasattr(p, "_reposition"):
                        p.adjustSize()
                        break
                    p = p.parent()

            self.exp_btn.clicked.connect(toggle_exp)
            layout.addWidget(self.exp_btn)
            layout.addWidget(self.exp_lbl)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        show_btn = QPushButton("Show")
        show_btn.setFixedHeight(30)
        show_btn.setCursor(Qt.PointingHandCursor)
        show_btn.setStyleSheet(themes.btn_style(
            themes.BTN_DIM_BG, themes.BTN_DIM_FG, themes.BTN_DIM_HOVER, radius=6
        ))
        show_btn.clicked.connect(lambda: self.show_clicked.emit(self.correction))

        apply_btn = QPushButton("✓ Apply")
        apply_btn.setFixedHeight(30)
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.setStyleSheet(themes.btn_style(
            themes.BTN_APPLY_BG, themes.BTN_APPLY_FG, themes.BTN_APPLY_HOVER, radius=6
        ))
        apply_btn.clicked.connect(lambda: self.apply_clicked.emit(self.correction))

        dismiss_btn = QPushButton("✕ Dismiss")
        dismiss_btn.setFixedHeight(30)
        dismiss_btn.setCursor(Qt.PointingHandCursor)
        dismiss_btn.setStyleSheet(themes.btn_style(
            themes.BTN_DIM_BG, themes.BTN_DIM_FG, themes.BTN_DIM_HOVER, radius=6
        ))
        dismiss_btn.clicked.connect(lambda: self.dismiss_clicked.emit(self.correction))

        btn_row.addWidget(show_btn)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(dismiss_btn)
        layout.addLayout(btn_row)


# ── Main panel ────────────────────────────────────────────────────────────────

class CorrectionPanel(QWidget):
    """
    Floating panel showing all grammar corrections for the current document.

    Signals:
        apply_correction(Correction)    — user wants to apply this fix
        dismiss_correction(Correction)  — user dismissed this suggestion
        closed()                        — user clicked the X button
    """
    apply_correction   = pyqtSignal(object)
    dismiss_correction = pyqtSignal(object)
    show_correction    = pyqtSignal(object)
    closed             = pyqtSignal()

    _PANEL_WIDTH  = 420
    _PANEL_MAX_H  = 600

    def __init__(self, screen_w: int, screen_h: int):
        super().__init__()
        self._screen_w = screen_w
        self._screen_h = screen_h

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(self._PANEL_WIDTH)

        self._build_ui()
        self._add_shadow()
        self.hide()

        log.debug("CorrectionPanel created")

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)   # space for shadow

        # Container (rounded, dark bg)
        self._container = QWidget()
        self._container.setObjectName("panel_container")
        self._container.setStyleSheet(themes.PANEL_CONTAINER_STYLE)

        inner = QVBoxLayout(self._container)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)

        inner.addLayout(self._build_header())

        # Divider
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {themes.PANEL_BORDER};")
        inner.addWidget(div)

        # Scroll area for correction cards
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                background: {themes.PANEL_BG};
                width: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {themes.PANEL_BORDER};
                border-radius: 3px; min-height: 20px;
            }}
        """)

        self._cards_widget = QWidget()
        self._cards_widget.setStyleSheet("background: transparent;")
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(10, 10, 10, 10)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch()

        self._scroll.setWidget(self._cards_widget)
        inner.addWidget(self._scroll)

        outer.addWidget(self._container)

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setContentsMargins(14, 12, 10, 12)

        icon = QLabel("⚡")
        icon.setFont(QFont(cfg.FONT_FAMILY, 11))
        icon.setStyleSheet("background: transparent; color: #88C0D0;")

        title = QLabel("Grammar Assistant")
        title.setFont(QFont(cfg.FONT_FAMILY, 10, QFont.Bold))
        title.setStyleSheet(f"color: {themes.PANEL_TITLE_FG}; background: transparent;")

        self._count_lbl = QLabel("")
        self._count_lbl.setFont(QFont(cfg.FONT_FAMILY, 9))
        self._count_lbl.setStyleSheet(f"color: {themes.PANEL_DIM}; background: transparent;")

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(themes.btn_style(
            themes.BTN_CLOSE_BG, themes.BTN_CLOSE_FG, themes.BTN_CLOSE_HOVER, radius=6
        ))
        close_btn.clicked.connect(self._on_close)

        header.addWidget(icon)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._count_lbl)
        header.addSpacing(6)
        header.addWidget(close_btn)
        return header

    def _add_shadow(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(cfg.CARD_SHADOW_BLUR)
        shadow.setOffset(0, cfg.CARD_SHADOW_OFFSET)
        shadow.setColor(QColor(0, 0, 0, 180))
        self._container.setGraphicsEffect(shadow)

    # ── Public API ────────────────────────────────────────────────────────────

    def show_corrections(self, corrections: List[Correction], window_rect=None):
        """
        Populate the panel with new corrections, appending them without clearing old ones.
        """
        if not corrections:
            return

        for c in corrections:
            # Check for duplicates by index
            exists = False
            for i in range(self._cards_layout.count()):
                item = self._cards_layout.itemAt(i)
                if item and isinstance(item.widget(), CorrectionCard):
                    if item.widget().correction.index == c.index:
                        exists = True
                        break
            if not exists:
                card = CorrectionCard(c)
                card.apply_clicked.connect(self._on_apply)
                card.dismiss_clicked.connect(self._on_dismiss)
                card.show_clicked.connect(self._on_show)
                # Insert before the trailing stretch
                self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

        remaining = sum(
            1 for i in range(self._cards_layout.count())
            if isinstance(self._cards_layout.itemAt(i).widget() if self._cards_layout.itemAt(i) else None, CorrectionCard)
        )
        self._count_lbl.setText(f"{remaining} issue{'s' if remaining != 1 else ''}")
        self._reposition(window_rect)
        self.show()
        self._animate_in()

    def clear(self):
        """Remove all cards and hide the panel."""
        self._clear_cards()
        self.hide()

    def restore_visibility(self, window_rect=None):
        """Show the panel again if it has cards, repositioning next to the window."""
        remaining = sum(
            1 for i in range(self._cards_layout.count())
            if isinstance(self._cards_layout.itemAt(i).widget() if self._cards_layout.itemAt(i) else None, CorrectionCard)
        )
        if remaining > 0:
            self._reposition(window_rect)
            self.show()

    def remove_card(self, correction: Correction):
        """Remove a single card after it has been applied/dismissed."""
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            if item and isinstance(item.widget(), CorrectionCard):
                card: CorrectionCard = item.widget()
                if card.correction.index == correction.index:
                    card.hide()
                    self._cards_layout.removeItem(item)
                    card.deleteLater()
                    break

        remaining = sum(
            1 for i in range(self._cards_layout.count())
            if isinstance(self._cards_layout.itemAt(i).widget() if self._cards_layout.itemAt(i) else None, CorrectionCard)
        )
        if remaining == 0:
            self.hide()
        else:
            self._count_lbl.setText(f"{remaining} issue{'s' if remaining != 1 else ''}")

    def apply_top_card(self):
        """Apply the top-most visible correction card (triggered via hotkey)."""
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            if item and isinstance(item.widget(), CorrectionCard) and item.widget().isVisible():
                card: CorrectionCard = item.widget()
                card._on_apply()
                break

    def dismiss_top_card(self):
        """Dismiss the top-most visible correction card (triggered via hotkey)."""
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            if item and isinstance(item.widget(), CorrectionCard) and item.widget().isVisible():
                card: CorrectionCard = item.widget()
                card._on_dismiss()
                break

    # ── Internal ──────────────────────────────────────────────────────────────

    def _clear_cards(self):
        for i in reversed(range(self._cards_layout.count())):
            item = self._cards_layout.itemAt(i)
            if item and isinstance(item.widget(), CorrectionCard):
                item.widget().deleteLater()
                self._cards_layout.removeItem(item)

    def _reposition(self, window_rect):
        """Position panel to the right of the writing window, or screen edge."""
        panel_h = min(self._PANEL_MAX_H, 200 + self._cards_layout.count() * 110)
        self.setFixedHeight(panel_h)

        if window_rect:
            _, wt, wr, wb = window_rect
            x = min(wr + 8, self._screen_w - self._PANEL_WIDTH - 12)
            y = max(8, wt + (wb - wt) // 2 - panel_h // 2)
        else:
            x = self._screen_w - self._PANEL_WIDTH - 12
            y = self._screen_h // 2 - panel_h // 2

        self.move(int(x), int(y))

    def _animate_in(self):
        """Slide-in from right with opacity fade."""
        self.show()
        anim = QPropertyAnimation(self, b"geometry", self)
        start = self.geometry().adjusted(40, 0, 40, 0)
        anim.setStartValue(start)
        anim.setEndValue(self.geometry())
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim   # keep reference

    def _on_apply(self, correction: Correction):
        self.remove_card(correction)
        self.apply_correction.emit(correction)

    def _on_dismiss(self, correction: Correction):
        self.remove_card(correction)
        self.dismiss_correction.emit(correction)

    def _on_show(self, correction: Correction):
        self.show_correction.emit(correction)

    def _on_close(self):
        self.hide()
        self.closed.emit()

    # Allow dragging the panel
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and hasattr(self, "_drag_pos"):
            self.move(e.globalPos() - self._drag_pos)
