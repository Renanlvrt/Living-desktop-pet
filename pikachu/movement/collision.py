"""pikachu/movement/collision.py — Window detection and escape vector logic."""

import ctypes
import ctypes.wintypes
import win32gui

from pikachu import config as cfg
from pikachu.utils.logger import get_logger

log = get_logger(__name__)


class CollisionDetector:
    """
    Detects foreground window geometry and computes escape vectors
    so Pikachu can avoid being covered by open windows.
    """

    def __init__(self, screen_w: int, screen_h: int,
                 sprite_w: int, sprite_h: int):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.sw = sprite_w
        self.sh = sprite_h

    # ── Foreground window ─────────────────────────────────────────────────────

    def get_foreground_info(self) -> tuple:
        """
        Return (rect | None, is_fullscreen).
        rect is (left, top, right, bottom) of the foreground window,
        or None if the foreground is just the desktop / taskbar.
        """
        fg = win32gui.GetForegroundWindow()
        if not fg:
            return None, False
        if win32gui.GetClassName(fg) in cfg.DESKTOP_CLASSES:
            return None, False
        try:
            l, t, r, b = win32gui.GetWindowRect(fg)
        except Exception:
            return None, False

        if (r - l) < 150 or (b - t) < 80:
            return None, False
        if b < 0 or r < 0 or l > self.screen_w:
            return None, False

        fullscreen = (
            l <= 0 and t <= 0
            and r >= self.screen_w
            and b >= self.screen_h
        )
        return (l, t, r, b), fullscreen

    # ── Overlap checks ────────────────────────────────────────────────────────

    def is_covered(self, x: float, y: float, rect) -> bool:
        """True if Pikachu's bounding box overlaps *rect*."""
        if rect is None:
            return False
        wl, wt, wr, wb = rect
        return x < wr and x + self.sw > wl and y < wb and y + self.sh > wt

    def escape_vector(self, x: float, y: float, rect) -> tuple:
        """
        Return (evx, evy) — the smallest movement that takes Pikachu
        out of the window overlap.
        """
        wl, wt, wr, wb = rect
        spd = cfg.ESCAPE_SPEED

        d_left  = (x + self.sw) - wl
        d_right = wr - x
        d_up    = (y + self.sh) - wt
        d_down  = wb - y

        # Don't escape toward a screen edge we're already touching
        if x <= 0:                d_left  = float("inf")
        if x + self.sw >= self.screen_w: d_right = float("inf")
        if y <= 0:                d_up    = float("inf")
        if y + self.sh >= self.screen_h: d_down  = float("inf")

        min_d = min(d_left, d_right, d_up, d_down)

        if min_d == d_left:  return (-spd, 0.0)
        if min_d == d_right: return ( spd, 0.0)
        if min_d == d_up:    return (0.0, -spd)
        return                      (0.0,  spd)

    # ── Screen clamping ───────────────────────────────────────────────────────

    def clamp(self, x: float, y: float) -> tuple:
        """Hard-clamp so Pikachu never leaves screen bounds."""
        x = max(0.0, min(x, float(self.screen_w - self.sw)))
        y = max(0.0, min(y, float(self.screen_h - self.sh)))
        return x, y
