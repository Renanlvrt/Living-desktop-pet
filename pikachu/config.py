"""pikachu/config.py — Central configuration for the Living Desktop Pet."""

import os

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = ROOT_DIR
DATA_DIR   = os.path.join(os.path.expanduser("~"), ".pikachu")
LOGS_DIR   = os.path.join(DATA_DIR, "logs")
TOKEN_PATH = os.path.join(DATA_DIR, "token.json")
CREDS_PATH = os.path.join(DATA_DIR, "credentials.json")
CACHE_DB   = os.path.join(DATA_DIR, "calendar_cache.db")

# Ensure data dirs exist
os.makedirs(LOGS_DIR, exist_ok=True)

# ── Sprite ───────────────────────────────────────────────────────────────────
SPRITE_PATH = os.path.join(ASSETS_DIR, "pikachu.png")
SCALE       = 0.3          # sprite scale factor

# ── Movement ─────────────────────────────────────────────────────────────────
TICK_MS       = 20         # main loop interval in ms
RANDOM_SEED   = 42

SPEED         = 2.0        # normal roaming speed (px/tick)
ESCAPE_SPEED  = 5.0        # speed when escaping window coverage

BOB_RANGE     = 5          # px up/down for idle bob

IDLE_CHANCE      = 0.002   # probability per tick of randomly pausing
IDLE_MIN_MS      = 1500
IDLE_MAX_MS      = 5000
IDLE_TALK_TICKS  = 200     # ticks idle before Pikachu says something

DIR_MIN_TICKS    = 60      # ticks before direction can change
DIR_MAX_TICKS    = 250

# ── LLM ──────────────────────────────────────────────────────────────────────
OLLAMA_URL      = "http://localhost:11434"

# Tiny model — always loaded, cute chat, runs on CPU if needed
TINY_MODEL      = "qwen2.5:1.5b"
TINY_KEEP_ALIVE = -1        # keep loaded indefinitely

# Big model — loaded on demand for grammar/tool use
BIG_MODEL       = "mistral"
BIG_KEEP_ALIVE  = "5m"     # unload 5 minutes after last request

# GPU VRAM thresholds (in MB)
GPU_LOW_VRAM_MB  = 6000    # minimum to run BIG_MODEL
GPU_HIGH_VRAM_MB = 12000   # enough for mistral-nemo upgrade

# ── Speech Bubble ─────────────────────────────────────────────────────────────
BUBBLE_SHOW_MS   = 7000    # how long the bubble stays visible
TYPE_SPEED       = 2       # ticks between typewriter characters
BUBBLE_MAX_WIDTH = 200     # px

# ── Grammar ───────────────────────────────────────────────────────────────────
GRAMMAR_POLL_INTERVAL_S = 5   # seconds between text snapshots
GRAMMAR_PAUSE_THRESHOLD = 3   # seconds of no change before suggesting

# ── App detection ─────────────────────────────────────────────────────────────
# Maps Windows class names → friendly names for known writing apps
WRITING_APPS = {
    "OpusApp":             "Microsoft Word",
    "Notepad":             "Notepad",
    "Notepad++":           "Notepad++",
    "Qt5152QWindowIcon":   "TeXstudio",
    "TeXworks":            "TeXworks",
    "Emacs":               "Emacs",
    "gVim":                "Vim",
}

# Desktop/taskbar class names to ignore entirely
DESKTOP_CLASSES = {
    "Progman", "WorkerW", "Shell_TrayWnd", "Button",
    "DV2ControlHost", "MsgrIMEWindowClass", "",
}

# ── Shortcuts ────────────────────────────────────────────────────────────────
SHORTCUT_GRAMMAR_TOGGLE = "ctrl+shift+p"   # toggle grammar mode

# ── Google Calendar ───────────────────────────────────────────────────────────
CALENDAR_SCOPES     = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_SYNC_EVERY = 900   # seconds between background syncs (15 min)
CALENDAR_CACHE_DAYS = 7     # days of events to keep in local cache

# ── UI / Theme ────────────────────────────────────────────────────────────────
FONT_FAMILY         = "Segoe UI"
FONT_FAMILY_MONO    = "Courier New"

# Pikachu brand colours
COLOR_YELLOW        = "#FFD700"
COLOR_YELLOW_LIGHT  = "#FFF3B0"
COLOR_CREAM         = "#fdf6e3"
COLOR_DARK          = "#1a1a1a"
COLOR_BORDER        = "#2b2b2b"

# Card (confirmation dialog) colours — dark theme
CARD_BG             = "#1e1e2e"
CARD_BORDER         = "#313244"
CARD_TEXT           = "#cdd6f4"
CARD_SUBTEXT        = "#a6adc8"
CARD_INNER_BG       = "#181825"
CARD_CONFIRM_BTN    = "#a6e3a1"
CARD_CONFIRM_TEXT   = "#1e1e2e"
CARD_CANCEL_BTN     = "#313244"
CARD_CANCEL_BORDER  = "#45475a"

CARD_RADIUS         = 16   # px
CARD_WIDTH          = 360  # px
CARD_SHADOW_BLUR    = 30
CARD_SHADOW_OFFSET  = 8
