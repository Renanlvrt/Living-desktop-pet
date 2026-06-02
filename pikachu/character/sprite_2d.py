"""pikachu/character/sprite_2d.py — 2D static sprite character."""

import os
from PyQt5.QtGui import QPixmap, QTransform
from PyQt5.QtCore import Qt

from pikachu.character.base import Character
from pikachu import config as cfg
from pikachu.utils.logger import get_logger

log = get_logger(__name__)


class Sprite2D(Character):
    """
    Simple 2D sprite character using a single PNG image.

    The sprite supports:
    - Horizontal flipping (left/right movement)
    - Scale factor from config
    - Named animation stubs (for future sprite-sheet support)
    """

    def __init__(self, image_path: str = None, scale: float = None):
        path  = image_path or cfg.SPRITE_PATH
        scale = scale or cfg.SCALE

        self._base = QPixmap(path)
        if not self._base:
            raise FileNotFoundError(f"Sprite image not found: {path}")

        if scale != 1.0:
            self._base = self._base.scaled(
                int(self._base.width()  * scale),
                int(self._base.height() * scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        self._flipped = self._base.transformed(QTransform().scale(-1, 1))
        self._current_anim = "idle"
        log.debug(
            "Sprite2D loaded: %s  size=%dx%d",
            os.path.basename(path), self._base.width(), self._base.height(),
        )

    # ── Character interface ───────────────────────────────────────────────────

    def get_pixmap(self, flip: bool = False) -> QPixmap:
        return self._flipped if flip else self._base

    def get_bounds(self) -> tuple:
        return self._base.width(), self._base.height()

    def play_animation(self, name: str, loop: bool = True):
        """
        Stub — with a single sprite there are no animation frames.
        Future: swap sprite sheet row based on *name*.
        """
        self._current_anim = name

    def update(self, dt: float):
        """No-op for static sprite. Future: advance animation frame."""
        pass
