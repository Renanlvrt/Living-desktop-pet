"""
pikachu/utils/app_monitor.py
─────────────────────────────
Event-driven foreground window monitor using Windows SetWinEventHook.

Uses EVENT_SYSTEM_FOREGROUND (0x0003) — the OS fires our callback
whenever the focused window changes. Zero polling, zero CPU cost.

Because the hook requires a Windows message pump to deliver events,
we run it in a dedicated background thread with its own message loop.
Qt signals are used to deliver results safely to the main thread.
"""

import ctypes
import ctypes.wintypes
import threading
import os

import win32gui
import win32process
import psutil

from PyQt5.QtCore import QObject, pyqtSignal

from pikachu import config as cfg
from pikachu.utils.logger import get_logger

log = get_logger(__name__)

# ── Win32 constants ───────────────────────────────────────────────────────────
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT   = 0x0000

user32  = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WinEventProcType = ctypes.WINFUNCTYPE(
    None,
    ctypes.wintypes.HANDLE,  # hWinEventHook
    ctypes.wintypes.DWORD,   # event
    ctypes.wintypes.HWND,    # hwnd
    ctypes.wintypes.LONG,    # idObject
    ctypes.wintypes.LONG,    # idChild
    ctypes.wintypes.DWORD,   # idEventThread
    ctypes.wintypes.DWORD,   # dwmsEventTime
)


class AppMonitorSignals(QObject):
    """Qt signals delivered to the main thread."""
    app_changed          = pyqtSignal(str, str, int)   # friendly_name, class_name, hwnd
    writing_app_detected = pyqtSignal(str)             # app name (e.g. "Microsoft Word")
    writing_app_closed   = pyqtSignal()


class AppMonitor:
    """
    Background monitor that emits a signal whenever the foreground app changes.
    Uses SetWinEventHook — no polling, no CPU cost.

    Usage:
        monitor = AppMonitor()
        monitor.signals.writing_app_detected.connect(my_slot)
        monitor.start()
        ...
        monitor.stop()
    """

    def __init__(self):
        self.signals     = AppMonitorSignals()
        self._hook       = None
        self._thread     = None
        self._thread_id  = None
        self._running    = False
        self._last_class = ""

        # Keep a strong reference to the ctypes callback so GC doesn't collect it
        self._callback_ref = WinEventProcType(self._on_foreground_change)

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start the background message pump thread."""
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._pump_loop, daemon=True)
        self._thread.start()
        log.info("AppMonitor started")

    def stop(self):
        """Stop the hook and message pump."""
        self._running = False
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
        log.info("AppMonitor stopped")

    def get_current_app(self) -> dict:
        """
        Synchronously query the current foreground window.
        Returns a dict with keys: process, name, class_name, title, pid, hwnd.
        """
        try:
            hwnd = win32gui.GetForegroundWindow()
            return self._hwnd_to_info(hwnd)
        except Exception as e:
            log.warning("get_current_app failed: %s", e)
            return {}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _pump_loop(self):
        """Background thread: install hook, run message pump, clean up."""
        self._thread_id = kernel32.GetCurrentThreadId()

        self._hook = user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            0,
            self._callback_ref,
            0, 0,
            WINEVENT_OUTOFCONTEXT,
        )
        if not self._hook:
            log.error("SetWinEventHook failed")
            return

        log.debug("WinEventHook installed (thread %d)", self._thread_id)

        msg = ctypes.wintypes.MSG()
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnhookWinEvent(self._hook)
        self._hook = None
        log.debug("WinEventHook uninstalled")

    def _on_foreground_change(self, hWinEventHook, event, hwnd,
                               idObject, idChild, dwEventThread, dwmsEventTime):
        """Called by Windows every time the foreground window changes."""
        try:
            info = self._hwnd_to_info(hwnd)
            if not info:
                return

            if info.get("pid") == os.getpid():
                # Ignore our own windows (like GrammarOfferCard or panels) taking focus
                return

            class_name    = info.get("class_name", "")
            friendly_name = info.get("name", "")

            self.signals.app_changed.emit(friendly_name, class_name, hwnd)

            # Detect writing apps
            if class_name in cfg.WRITING_APPS:
                if class_name != self._last_class:
                    self._last_class = class_name
                    app_name = cfg.WRITING_APPS[class_name]
                    log.info("Writing app detected: %s", app_name)
                    self.signals.writing_app_detected.emit(app_name)
            else:
                if self._last_class in cfg.WRITING_APPS:
                    self._last_class = ""
                    self.signals.writing_app_closed.emit()

        except Exception as e:
            log.debug("_on_foreground_change error: %s", e)

    def _hwnd_to_info(self, hwnd: int) -> dict:
        """Convert a HWND to a rich info dict."""
        if not hwnd:
            return {}
        try:
            _, pid        = win32process.GetWindowThreadProcessId(hwnd)
            proc          = psutil.Process(pid)
            proc_name     = proc.name().lower()
            class_name    = win32gui.GetClassName(hwnd)
            title         = win32gui.GetWindowText(hwnd)
            friendly_name = cfg.WRITING_APPS.get(class_name, proc_name)
            return {
                "process":    proc_name,
                "name":       friendly_name,
                "class_name": class_name,
                "title":      title,
                "pid":        pid,
                "hwnd":       hwnd,
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {}
        except Exception as e:
            log.debug("_hwnd_to_info error: %s", e)
            return {}
