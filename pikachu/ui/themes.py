"""pikachu/ui/themes.py — Centralised colour palette and stylesheet fragments."""

from pikachu import config as cfg

# ── Colour tokens ─────────────────────────────────────────────────────────────
# Speech bubble (warm cream — Pikachu's classic style)
BUBBLE_BG       = cfg.COLOR_CREAM
BUBBLE_BORDER   = cfg.COLOR_BORDER
BUBBLE_TEXT     = cfg.COLOR_DARK

# Correction panel (dark, premium glassmorphism-style)
PANEL_BG        = "#16161e"
PANEL_BG_INNER  = "#1a1a2e"
PANEL_BORDER    = "#2a2a3e"
PANEL_TITLE_FG  = "#e2e2f0"
PANEL_BODY_FG   = "#b0b0cc"
PANEL_ACCENT    = "#FFD700"        # Pikachu yellow
PANEL_ERROR_FG  = "#ff7eb6"        # soft pink for "original wrong text"
PANEL_OK_FG     = "#a6e3a1"        # soft green for "corrected text"
PANEL_DIM       = "#5a5a78"

# Buttons
BTN_APPLY_BG    = "#a6e3a1"
BTN_APPLY_FG    = "#16161e"
BTN_APPLY_HOVER = "#7ecf7a"
BTN_DIM_BG      = "#2a2a3e"
BTN_DIM_FG      = "#b0b0cc"
BTN_DIM_HOVER   = "#3a3a52"
BTN_CLOSE_BG    = "#3a2a3e"
BTN_CLOSE_FG    = "#ff7eb6"
BTN_CLOSE_HOVER = "#5a2a4e"

# Cards (confirmation dialogs)
CARD_BG         = cfg.CARD_BG
CARD_INNER      = cfg.CARD_INNER_BG
CARD_BORDER     = cfg.CARD_BORDER
CARD_TITLE      = cfg.CARD_TEXT
CARD_BODY       = cfg.CARD_SUBTEXT
CARD_CONFIRM_BG = cfg.CARD_CONFIRM_BTN
CARD_CONFIRM_FG = cfg.CARD_CONFIRM_TEXT
CARD_CANCEL_BG  = cfg.CARD_CANCEL_BTN

# ── Shared button helper ──────────────────────────────────────────────────────
def btn_style(bg: str, fg: str, hover_bg: str,
              radius: int = 10, border: str = "none") -> str:
    return f"""
        QPushButton {{
            background-color: {bg};
            color: {fg};
            border: {border};
            border-radius: {radius}px;
            padding: 0 16px;
            font-family: '{cfg.FONT_FAMILY}';
            font-size: 10pt;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {hover_bg};
        }}
        QPushButton:pressed {{
            background-color: {bg};
            opacity: 0.8;
        }}
    """


# ── Bubble stylesheet ─────────────────────────────────────────────────────────
BUBBLE_STYLE = f"""
    QLabel {{
        background-color: {BUBBLE_BG};
        border: 2px solid {BUBBLE_BORDER};
        border-radius: 6px;
        padding: 7px 11px;
        color: {BUBBLE_TEXT};
        font-family: '{cfg.FONT_FAMILY_MONO}';
        font-size: 9pt;
        font-weight: bold;
        letter-spacing: 1px;
    }}
"""

# ── Correction panel base stylesheet ─────────────────────────────────────────
PANEL_CONTAINER_STYLE = f"""
    #panel_container {{
        background-color: {PANEL_BG};
        border: 1px solid {PANEL_BORDER};
        border-radius: 14px;
    }}
"""
