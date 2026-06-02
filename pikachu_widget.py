import sys, os, ctypes, win32gui, win32con, random, threading, textwrap, re
import requests
from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtGui import QPixmap, QTransform, QFont
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject

# ── Config ─────────────────────────────────────────
SCALE        = 0.3
TICK_MS      = 20
RANDOM_SEED  = 42

SPEED        = 2.0          # normal roaming speed (px/tick)
ESCAPE_SPEED = 5.0          # speed when escaping window coverage

BOB_RANGE    = 5            # px up/down for idle bob

IDLE_CHANCE     = 0.002     # probability per tick of randomly pausing
IDLE_MIN_MS     = 1500
IDLE_MAX_MS     = 5000
IDLE_TALK_TICKS = 200       # ticks idle before he says something

DIR_MIN_TICKS   = 60        # ticks before direction can change
DIR_MAX_TICKS   = 250

OLLAMA_MODEL    = "tinyllama"
OLLAMA_URL      = "http://localhost:11434/api/generate"
BUBBLE_SHOW_MS  = 7000
TYPE_SPEED      = 2         # ticks between typewriter characters
# ───────────────────────────────────────────────────

rng = random.Random(RANDOM_SEED)

ROAMING  = "roaming"
IDLE     = "idle"
ESCAPING = "escaping"

script_dir = os.path.dirname(os.path.abspath(__file__))
img_path   = os.path.join(script_dir, "pikachu.png")

app = QApplication(sys.argv)
screen_w = app.primaryScreen().geometry().width()
screen_h = app.primaryScreen().geometry().height()

# ── Pikachu label ──────────────────────────────────
label = QLabel()
label.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
label.setAttribute(Qt.WA_TranslucentBackground)

base_pixmap = QPixmap(img_path)
if SCALE != 1.0:
    base_pixmap = base_pixmap.scaled(
        int(base_pixmap.width() * SCALE),
        int(base_pixmap.height() * SCALE),
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation
    )
flipped_pixmap = base_pixmap.transformed(QTransform().scale(-1, 1))
label.setPixmap(base_pixmap)
label.resize(base_pixmap.size())
label.move(100, screen_h // 2)
label.show()

# ── Speech bubble ──────────────────────────────────
bubble = QLabel()
bubble.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
bubble.setWordWrap(True)
bubble.setFont(QFont("Courier New", 9, QFont.Bold))
bubble.setStyleSheet("""
    QLabel {
        background-color: #fdf6e3;
        border: 2px solid #2b2b2b;
        border-radius: 2px;
        padding: 7px 10px;
        color: #1a1a1a;
        letter-spacing: 1px;
    }
""")
bubble.setMaximumWidth(180)
bubble.hide()

bubble_ticks    = 0
llm_busy        = False
idle_talk_count = 0
_type_full      = ""
_type_index     = 0
_type_delay     = 0

# ── Z-order ────────────────────────────────────────
_hwnd       = int(label.winId())
_workerw    = None
_is_topmost = False

def find_workerw():
    global _workerw
    progman = win32gui.FindWindow("Progman", None)
    ctypes.windll.user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, None)
    result = ctypes.c_ulonglong(0)
    def enum_cb(h, _):
        if win32gui.FindWindowEx(h, 0, "SHELLDLL_DefView", None):
            result.value = win32gui.FindWindowEx(0, h, "WorkerW", None)
    win32gui.EnumWindows(enum_cb, None)
    _workerw = result.value

def go_to_background():
    global _is_topmost
    if _workerw:
        ctypes.windll.user32.SetParent(_hwnd, _workerw)
    _is_topmost = False

def go_to_foreground():
    global _is_topmost
    ctypes.windll.user32.SetParent(_hwnd, 0)
    ctypes.windll.user32.SetWindowPos(
        _hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
    )
    _is_topmost = True

find_workerw()
go_to_background()

# ── Window detection ───────────────────────────────
DESKTOP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Button",
                   "DV2ControlHost", "MsgrIMEWindowClass", ""}

def get_foreground_info():
    """Returns (rect | None, is_fullscreen)."""
    fg = win32gui.GetForegroundWindow()
    if not fg or win32gui.GetClassName(fg) in DESKTOP_CLASSES:
        return None, False
    try:
        l, t, r, b = win32gui.GetWindowRect(fg)
    except:
        return None, False
    if (r - l) < 150 or (b - t) < 80 or b < 0 or r < 0 or l > screen_w:
        return None, False
    fullscreen = (l <= 0 and t <= 0 and r >= screen_w and b >= screen_h)
    return (l, t, r, b), fullscreen

# ── LLM ───────────────────────────────────────────
class LLMSignal(QObject):
    response_ready = pyqtSignal(str)

llm_signal = LLMSignal()

def ask_llm(context):
    global llm_busy
    if llm_busy:
        return
    llm_busy = True
    def run():
        global llm_busy
        try:
            resp = requests.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "prompt": (
                    "You are Pikachu, a tiny cute Pokemon living on someone's desktop. "
                    "RULES: max 10 words total. Max 1 emoji (optional). No hashtags. "
                    "No punctuation other than ! or ?. Cute and expressive. "
                    f"Situation: {context}"
                ),
                "stream": False
            }, timeout=15)
            text = resp.json().get("response", "Pika pika!").strip()
            text = re.sub(r'#\w+', '', text).strip()
            words = text.split()[:10]
            text = " ".join(words)
            if not text.endswith(("!", "?")):
                text += "!"
        except Exception:
            text = "Pika pika!"
        llm_busy = False
        llm_signal.response_ready.emit(text)
    threading.Thread(target=run, daemon=True).start()

def show_bubble(text):
    global bubble_ticks, _type_full, _type_index, _type_delay
    _type_full  = text
    _type_index = 0
    _type_delay = 0
    bubble.setText("")
    bubble.adjustSize()
    _reposition_bubble()
    bubble.show()
    bubble_ticks = BUBBLE_SHOW_MS // TICK_MS

def _reposition_bubble():
    pw = base_pixmap.width()
    bx = int(x) + pw // 2 - bubble.width() // 2
    by = int(y) - bubble.height() - 8
    bubble.move(max(0, min(bx, screen_w - bubble.width())), max(0, by))

llm_signal.response_ready.connect(show_bubble)

# ── Movement helpers ───────────────────────────────
pw = base_pixmap.width()
ph = base_pixmap.height()

def clamp_to_screen(nx, ny):
    """Hard clamp — Pikachu can never leave screen bounds."""
    nx = max(0.0, min(nx, float(screen_w - pw)))
    ny = max(0.0, min(ny, float(screen_h - ph)))
    return nx, ny

def is_covered(rect):
    """True if Pikachu's rect overlaps the window rect."""
    if rect is None:
        return False
    wl, wt, wr, wb = rect
    return x < wr and x + pw > wl and y < wb and y + ph > wt

def escape_vector(rect):
    """
    Returns (evx, evy) — the direction that gets Pikachu
    out of the window overlap in the fewest pixels.
    Vertical boundaries → push left/right.
    Horizontal boundaries → push up/down.
    """
    wl, wt, wr, wb = rect
    d_left  = (x + pw) - wl   # cost to exit via left wall
    d_right = wr - x           # cost to exit via right wall
    d_up    = (y + ph) - wt   # cost to exit via top wall
    d_down  = wb - y           # cost to exit via bottom wall

    # Respect screen edges: don't escape toward a wall we're already against
    if x <= 0:            d_left  = float("inf")
    if x + pw >= screen_w: d_right = float("inf")
    if y <= 0:            d_up    = float("inf")
    if y + ph >= screen_h: d_down  = float("inf")

    min_d = min(d_left, d_right, d_up, d_down)

    if min_d == d_left:   return (-ESCAPE_SPEED, 0.0)
    if min_d == d_right:  return ( ESCAPE_SPEED, 0.0)
    if min_d == d_up:     return (0.0, -ESCAPE_SPEED)
    return                       (0.0,  ESCAPE_SPEED)

def pick_direction():
    """Pick a random non-zero 2D direction and reset direction timer."""
    global vx, vy, dir_ticks
    choices = [-SPEED, 0.0, SPEED]
    while True:
        nvx = rng.choice(choices)
        nvy = rng.choice(choices)
        if nvx != 0 or nvy != 0:
            break
    vx = nvx
    vy = nvy
    dir_ticks = rng.randint(DIR_MIN_TICKS, DIR_MAX_TICKS)
    if vx > 0:  label.setPixmap(base_pixmap)
    elif vx < 0: label.setPixmap(flipped_pixmap)

# ── Movement state ─────────────────────────────────
x         = 100.0
y         = float(screen_h // 2)
vx        = SPEED
vy        = 0.0
bob       = 0
bob_dir   = 1
state     = ROAMING
idle_ticks       = 0
idle_talk_count  = 0
dir_ticks        = rng.randint(DIR_MIN_TICKS, DIR_MAX_TICKS)
prev_win         = None   # last known window rect (for tab-switch detection)

# ── Main tick ─────────────────────────────────────
def tick():
    global x, y, vx, vy, bob, bob_dir, state
    global idle_ticks, idle_talk_count, dir_ticks, prev_win
    global bubble_ticks, _type_full, _type_index, _type_delay

    # Bob
    bob += bob_dir
    if abs(bob) >= BOB_RANGE:
        bob_dir *= -1

    # ── Fullscreen / z-order ──────────────────────
    rect, fullscreen = get_foreground_info()
    if fullscreen and not _is_topmost:
        go_to_foreground()
    elif not fullscreen and _is_topmost:
        go_to_background()

    # ── Tab-switch detection ──────────────────────
    # If topmost window changed and Pikachu is now covered → escape immediately
    if rect != prev_win:
        prev_win = rect
        if not fullscreen and is_covered(rect):
            state = ESCAPING

    # ── Bubble: typewriter + follow ───────────────
    if bubble_ticks > 0:
        bubble_ticks -= 1
        # Typewriter: reveal one character at a time
        if _type_index < len(_type_full):
            _type_delay -= 1
            if _type_delay <= 0:
                _type_index += 1
                bubble.setText(_type_full[:_type_index] + ("_" if _type_index < len(_type_full) else ""))
                bubble.adjustSize()
                _type_delay = TYPE_SPEED
        else:
            bubble.setText(_type_full)   # done typing, remove cursor
        _reposition_bubble()
        if bubble_ticks == 0:
            bubble.hide()

    # ── Skip movement logic when fullscreen ───────
    # (Pikachu roams freely on top, no window obstacles)
    if fullscreen:
        _move_freely()
        label.move(int(x), int(y + bob))
        return

    # ── ROAMING ───────────────────────────────────
    if state == ROAMING:
        idle_talk_count = 0

        # Random pause
        if rng.random() < IDLE_CHANCE:
            state = IDLE
            idle_ticks = rng.randint(IDLE_MIN_MS, IDLE_MAX_MS) // TICK_MS
            label.move(int(x), int(y + bob))
            return

        _move_freely()

        # If movement landed inside window → escape
        if is_covered(rect):
            state = ESCAPING

    # ── IDLE ──────────────────────────────────────
    elif state == IDLE:
        idle_talk_count += 1
        if idle_talk_count == IDLE_TALK_TICKS:
            ask_llm("I have been standing still for a while, just chilling.")
        idle_ticks -= 1
        if idle_ticks <= 0:
            state = ROAMING
            idle_talk_count = 0
            pick_direction()
        # Still escape if covered while idle
        if is_covered(rect):
            state = ESCAPING

    # ── ESCAPING ──────────────────────────────────
    elif state == ESCAPING:
        if not is_covered(rect):
            # Free — resume roaming
            state = ROAMING
            pick_direction()
            ask_llm("I just escaped from behind a window!")
        else:
            evx, evy = escape_vector(rect)
            nx, ny = clamp_to_screen(x + evx, y + evy)
            x, y = nx, ny

    label.move(int(x), int(y + bob))

def _move_freely():
    """Apply vx/vy with direction timer, screen edge bounce, and wall reaction."""
    global x, y, vx, vy, dir_ticks

    # Direction change countdown
    dir_ticks -= 1
    if dir_ticks <= 0:
        pick_direction()

    nx = x + vx
    ny = y + vy

    # Screen edges:
    # Left/right → bounce (reverse horizontal)
    # Top/bottom → hard clamp (cannot exit, bounce back)
    if nx <= 0:
        nx = 0.0
        vx = abs(vx)
        label.setPixmap(base_pixmap)
    elif nx + pw >= screen_w:
        nx = float(screen_w - pw)
        vx = -abs(vx)
        label.setPixmap(flipped_pixmap)

    if ny <= 0:
        ny = 0.0
        vy = abs(vy)   # bounce downward
    elif ny + ph >= screen_h:
        ny = float(screen_h - ph)
        vy = -abs(vy)  # bounce upward

    x, y = nx, ny

# ── Timer ──────────────────────────────────────────
timer = QTimer()
timer.timeout.connect(tick)
timer.start(TICK_MS)

# ── Click to talk ──────────────────────────────────
def mousePressEvent(e):
    if e.button() == Qt.LeftButton:
        ask_llm("Someone just clicked on me! I am surprised and happy.")

def contextMenuEvent(e):
    from PyQt5.QtWidgets import QMenu
    menu = QMenu()
    menu.addAction("Close  ✕", app.quit)
    menu.exec_(e.globalPos())

label.mousePressEvent  = mousePressEvent
label.contextMenuEvent = contextMenuEvent

sys.exit(app.exec_())