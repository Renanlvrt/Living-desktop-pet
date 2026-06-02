"""pikachu/utils/logger.py — Rotating file logger with console fallback."""

import logging
import logging.handlers
import os

from pikachu import config as cfg

_log = None


def get_logger(name: str = "pikachu") -> logging.Logger:
    """Return (or create) the application-wide logger."""
    global _log
    if _log is not None:
        return logging.getLogger(name)

    logger = logging.getLogger("pikachu")
    logger.setLevel(logging.DEBUG)

    # ── File handler (rotating, max 5 MB × 3 files) ──────────────────────────
    log_file = os.path.join(cfg.LOGS_DIR, "pikachu.log")
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # ── Console handler ───────────────────────────────────────────────────────
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)

    _log = logger
    return logger
