"""
pikachu/ui/window.py
─────────────────────
Main PyQt5 window: the frameless Pikachu label, z-order management
(desktop pinning via WorkerW / foreground via HWND_TOPMOST),
and right-click context menu.

No game logic lives here — this is purely a rendering + input bridge.
"""

import ctypes
import ctypes.wintypes

import win32con
import win32gui

from PyQt5.QtWidgets import QLabel, QMenu, QApplication
from PyQt5.QtCore    import Qt, pyqtSignal, QObject
from PyQt5.QtGui     import QPixmap

from pikachu.utils.logger import get_logger

log = get_logger(__name__)


class WindowSignals(QObject):
    clicked        = pyqtSignal()         # left-click on Pikachu
    grammar_toggle = pyqtSignal()         # Ctrl+Shift+P shortcut


class PikachuWindow:
    """
    Wraps a frameless QLabel that renders Pikachu on the desktop.

    Z-order states
    ──────────────
    Background (default): SetParent(hwnd, WorkerW)
        Pikachu lives behind desktop icons, above wallpaper.
    Foreground (fullscreen): SetParent(hwnd, 0) + HWND_TOPMOST
        Pikachu floats above fullscreen apps.
    """

    def __init__(self, screen_w: int, screen_h: int):
        self._screen_w  = screen_w
        self._screen_h  = screen_h
        self.signals    = WindowSignals()
        self._is_topmost = False
        self._workerw    = None

        # ── Label ─────────────────────────────────────────────────────────────
        self._label = QLabel()
        self._label.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self._label.setAttribute(Qt.WA_TranslucentBackground)
        self._label.mousePressEvent  = self._on_click
        self._label.contextMenuEvent = self._on_context_menu
        self._label.show()

        # ── HWND ──────────────────────────────────────────────────────────────
        self._hwnd = int(self._label.winId())

        # ── Find WorkerW and pin to desktop ───────────────────────────────────
        self._find_workerw()
        self.go_to_background()

        log.debug("PikachuWindow created (hwnd=%d)", self._hwnd)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_pixmap(self, pixmap: QPixmap):
        self._label.setPixmap(pixmap)
        self._label.resize(pixmap.size())

    def move(self, x: int, y: int):
        self._label.move(x, y)

    def go_to_background(self):
        """Pin Pikachu behind desktop icons (default desktop layer)."""
        if self._workerw:
            ctypes.windll.user32.SetParent(self._hwnd, self._workerw)
        self._is_topmost = False
        log.debug("z-order → background")

    def go_to_foreground(self):
        """Bring Pikachu above all windows (used during fullscreen apps)."""
        ctypes.windll.user32.SetParent(self._hwnd, 0)
        ctypes.windll.user32.SetWindowPos(
            self._hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )
        self._is_topmost = True
        log.debug("z-order → foreground (topmost)")

    def update_zorder(self, is_fullscreen: bool):
        """Call every tick to ensure z-order matches current state."""
        if is_fullscreen and not self._is_topmost:
            self.go_to_foreground()
        elif not is_fullscreen and self._is_topmost:
            self.go_to_background()

    @property
    def is_topmost(self) -> bool:
        return self._is_topmost

    # ── Input handlers ────────────────────────────────────────────────────────

    def _on_click(self, event):
        if event.button() == Qt.LeftButton:
            self.signals.clicked.emit()

    def _on_context_menu(self, event):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 8px;
                padding: 4px;
                color: #cdd6f4;
                font-family: 'Segoe UI';
                font-size: 10pt;
            }
            QMenu::item:selected {
                background-color: #313244;
                border-radius: 4px;
            }
        """)
        grammar_action = menu.addAction("⚡  Grammar Mode  (Ctrl+Shift+P)")
        grammar_action.triggered.connect(self.signals.grammar_toggle.emit)
        menu.addSeparator()
        menu.addAction("✕  Close", QApplication.instance().quit)
        menu.exec_(event.globalPos())

    # ── WorkerW discovery ─────────────────────────────────────────────────────

    def _find_workerw(self):
        """
        Locate the WorkerW handle so we can parent Pikachu's window to it,
        placing Pikachu behind desktop icons but above the wallpaper.
        """
        progman = win32gui.FindWindow("Progman", None)
        # Send the magic message that makes Explorer create a WorkerW
        ctypes.windll.user32.SendMessageTimeoutW(
            progman, 0x052C, 0, 0, 0, 1000, None
        )

        result = ctypes.c_ulonglong(0)

        def enum_cb(hwnd, _):
            if win32gui.FindWindowEx(hwnd, 0, "SHELLDLL_DefView", None):
                result.value = win32gui.FindWindowEx(0, hwnd, "WorkerW", None)

        win32gui.EnumWindows(enum_cb, None)
        self._workerw = result.value
        log.debug("WorkerW hwnd = %d", self._workerw)
