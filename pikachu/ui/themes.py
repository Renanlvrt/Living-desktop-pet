"""pikachu/ui/themes.py — Centralised colour palette and stylesheet fragments."""

from pikachu import config as cfg

# ── Colour tokens ─────────────────────────────────────────────────────────────
# Speech bubble (warm cream — Pikachu's classic style)
BUBBLE_BG       = "#FFFFFF"
BUBBLE_BORDER   = "#FFD700"
BUBBLE_TEXT     = "#1A1A1A"

# Correction panel (Minimalist Nord aesthetic)
PANEL_BG        = "#2E3440"        # Nord0 (Outer container background)
PANEL_BG_INNER  = "#3B4252"        # Nord1 (Card background)
PANEL_BORDER    = "#4C566A"        # Nord3 (Subtle borders)
PANEL_TITLE_FG  = "#D8DEE9"        # Nord4 (Light grey/white for title)
PANEL_BODY_FG   = "#ECEFF4"        # Nord6 (White for main text)
PANEL_ACCENT    = "#88C0D0"        # Nord8 (Frost blue accent)
PANEL_ERROR_FG  = "#BF616A"        # Nord11 (Red for errors)
PANEL_OK_FG     = "#A3BE8C"        # Nord14 (Green for fixes)
PANEL_DIM       = "#D8DEE9"        # Nord4 (Dim text)

# Buttons (Minimalist, rounded rects)
BTN_APPLY_BG    = "#81A1C1"        # Nord9 (Soft blue for primary action)
BTN_APPLY_FG    = "#ECEFF4"        # White text
BTN_APPLY_HOVER = "#8FBCBB"        # Nord7 (Lighter frost for hover)
BTN_DIM_BG      = "#4C566A"        # Nord3 (Dark grey for secondary)
BTN_DIM_FG      = "#ECEFF4"        # White text
BTN_DIM_HOVER   = "#434C5E"        # Nord2 (Slightly darker for hover)
BTN_CLOSE_BG    = "transparent"
BTN_CLOSE_FG    = "#BF616A"        # Nord11
BTN_CLOSE_HOVER = "#4C566A"        # Nord3

# Cards (confirmation dialogs)
CARD_BG         = "#FFFFFF"
CARD_INNER      = "#FAFAFA"
CARD_BORDER     = "#FFE566"
CARD_TITLE      = "#B8860B"
CARD_BODY       = "#4A4A4A"
CARD_CONFIRM_BG = "#FFD700"
CARD_CONFIRM_FG = "#1A1A1A"
CARD_CANCEL_BG  = "#F0F3F4"

# ── Shared button helper ──────────────────────────────────────────────────────
def btn_style(bg: str, fg: str, hover_bg: str,
              radius: int = 14, border: str = "none") -> str:
    return f"""
        QPushButton {{
            background-color: {bg};
            color: {fg};
            border: {border};
            border-radius: {radius}px;
            padding: 4px 16px;
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
            padding-top: 5px; /* cute pressed effect */
            padding-bottom: 3px;
        }}
    """


# ── Bubble stylesheet ─────────────────────────────────────────────────────────
BUBBLE_STYLE = f"""
    QLabel {{
        background-color: {BUBBLE_BG};
        border: 3px solid {BUBBLE_BORDER};
        border-radius: 12px;
        padding: 10px 14px;
        color: {BUBBLE_TEXT};
        font-family: '{cfg.FONT_FAMILY_MONO}';
        font-size: 9pt;
        font-weight: bold;
        letter-spacing: 0.5px;
    }}
"""

# ── Correction panel base stylesheet ─────────────────────────────────────────
PANEL_CONTAINER_STYLE = f"""
    #panel_container {{
        background-color: {PANEL_BG_INNER};
        border: 2px solid {PANEL_BORDER};
        border-radius: 20px;
    }}
"""
