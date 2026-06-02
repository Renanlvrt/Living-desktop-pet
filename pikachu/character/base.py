"""pikachu/character/base.py — Abstract base class for all character types."""

from abc import ABC, abstractmethod
from PyQt5.QtGui import QPixmap


class Character(ABC):
    """
    Interface that both the 2D sprite and future 3D character must implement.
    This ensures the movement engine can drive any visual representation
    without knowing the rendering details.
    """

    @abstractmethod
    def get_pixmap(self, flip: bool = False) -> QPixmap:
        """
        Return the QPixmap to display for the current animation frame.

        Args:
            flip: If True, return the horizontally mirrored version.
        """

    @abstractmethod
    def get_bounds(self) -> tuple:
        """Return (width, height) of the sprite bounding box in pixels."""

    @abstractmethod
    def play_animation(self, name: str, loop: bool = True):
        """
        Request a named animation clip.

        Args:
            name: e.g. 'walk', 'idle', 'think', 'celebrate', 'surprised'
            loop: Whether the animation should loop.
        """

    @abstractmethod
    def update(self, dt: float):
        """
        Advance the animation by dt seconds.
        Called every tick before get_pixmap().
        """
