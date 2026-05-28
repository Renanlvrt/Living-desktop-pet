import sys, os, ctypes, win32gui, win32con, random, threading, textwrap
import requests
from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtGui import QPixmap, QTransform, QFont
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject

# ── Config ─────────────────────────────────────────
SCALE        = 0.3
GROUND_Y     = 800
WALK_SPEED   = 2
CLIMB_SPEED  = 2
FALL_SPEED   = 5
BOB_RANGE    = 5
TICK_MS      = 20
RANDOM_SEED  = 42

IDLE_CHANCE      = 0.003
IDLE_MIN_MS      = 2000
IDLE_MAX_MS      = 6000
SIT_CHANCE       = 0.5
SIT_MIN_MS       = 3000
SIT_MAX_MS       = 8000

OLLAMA_MODEL     = "tinyllama"
OLLAMA_URL       = "http://localhost:11434/api/generate"
BUBBLE_SHOW_MS   = 6000
IDLE_TALK_TICKS  = 150
# ───────────────────────────────────────────────────

rng = random.Random(RANDOM_SEED)
WALKING  = "walking"
IDLE     = "idle"
CLIMBING = "climbing"
SITTING  = "sitting"
FALLING  = "falling"

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
label.move(100, GROUND_Y)
label.show()

# ── Speech bubble ──────────────────────────────────
bubble = QLabel()
bubble.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
bubble.setWordWrap(True)
bubble.setFont(QFont("Arial", 9, QFont.Bold))
bubble.setStyleSheet("""
    QLabel {
        background-color: white;
        border: 2px solid black;
        border-radius: 8px;
        padding: 6px 8px;
        color: black;
    }
""")
bubble.setMaximumWidth(200)
bubble.hide()

bubble_ticks    = 0
llm_busy        = False
idle_talk_count = 0

# ── Z-order management ─────────────────────────────
# Normally: parent Pikachu to WorkerW so he lives in the desktop background
# Fullscreen exception: un-parent + HWND_TOPMOST so he appears above fullscreen

_hwnd        = int(label.winId())
_workerw     = None
_is_topmost  = False
_zorder_tick = 0
ZORDER_EVERY = 25

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

DESKTOP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Button",
                   "DV2ControlHost", "MsgrIMEWindowClass", ""}

def get_foreground_info():
    """Returns (rect_or_None, is_fullscreen) for the current foreground window."""
    fg = win32gui.GetForegroundWindow()
    if not fg or win32gui.GetClassName(fg) in DESKTOP_CLASSES:
        return None, False
    try:
        l, t, r, b = win32gui.GetWindowRect(fg)
    except:
        return None, False
    if (r - l) < 150 or (b - t) < 80:
        return None, False
    if b < 0 or r < 0 or l > screen_w:
        return None, False
    fullscreen = (l <= 0 and t <= 0 and r >= screen_w and b >= screen_h)
    return (l, t, r, b), fullscreen

def get_obstacles():
    rect, fullscreen = get_foreground_info()
    if fullscreen or rect is None:
        return []
    return [rect]

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
                    "Reply in ONE short sentence (max 12 words). Stay in character. "
                    "Be energetic, cute and expressive. "
                    f"Situation: {context}"
                ),
                "stream": False
            }, timeout=15)
            text = resp.json().get("response", "Pika pika!").strip()
            text = text.split(".")[0].split("!")[0].split("?")[0] + "!"
        except Exception:
            text = "Pika pika!"
        llm_busy = False
        llm_signal.response_ready.emit(text)
    threading.Thread(target=run, daemon=True).start()

def show_bubble(text):
    global bubble_ticks
    wrapped = textwrap.fill(text, width=28)
    bubble.setText(wrapped)
    bubble.adjustSize()
    bx = int(x) + base_pixmap.width() // 2 - bubble.width() // 2
    by = int(y) - bubble.height() - 8
    bx = max(0, min(bx, screen_w - bubble.width()))
    by = max(0, by)
    bubble.move(bx, by)
    bubble.show()
    bubble_ticks = BUBBLE_SHOW_MS // TICK_MS

llm_signal.response_ready.connect(show_bubble)

# ── Movement state ─────────────────────────────────
x                = 100.0
y                = float(GROUND_Y)
direction        = 1
bob              = 0
bob_dir          = 1
state            = WALKING
idle_ticks       = 0
sit_ticks        = 0
climb_target     = 0.0
current_win      = None
off_screen_ticks = 0
MAX_OFF_SCREEN   = 3000 // TICK_MS

def resolve_push(obstacles):
    global x, y, direction, state
    pw = base_pixmap.width()
    ph = base_pixmap.height()
    
    for wl, wt, wr, wb in obstacles:
        # GOAL 1 & 4: Detect bounding boxes of topmost tab
        if not (x < wr and x + pw > wl and y < wb and y + ph > wt):
            continue
            
        push_right = wr - x
        push_left  = (x + pw) - wl
        push_down  = wb - y
        push_up    = (y + ph) - wt
        
        # Calculate the absolute shortest path to safety
        min_push   = min(push_right, push_left, push_up, push_down)

        # GOAL 5 & 6: Uncovered at all times / Shortest path recovery
        # If covered by more than 30 pixels, he immediately dashes out 
        # using left/right walking or up/down climbing logic.
        if min_push > 30:
            ESCAPE_SPEED = 15 
            if min_push == push_left:
                x -= ESCAPE_SPEED; direction = -1; label.setPixmap(flipped_pixmap)
            elif min_push == push_right:
                x += ESCAPE_SPEED; direction = 1;  label.setPixmap(base_pixmap)
            elif min_push == push_up:
                y -= ESCAPE_SPEED  # Recovers by climbing up
            elif min_push == push_down:
                y += ESCAPE_SPEED  # Recovers by climbing down
            return # Exit so we can see him dash out naturally
            
        # GOAL 2: Affected by boundaries (Pushed left/right and up/down)
        if min_push == push_left:
            x = float(wl - pw); direction = -1; label.setPixmap(flipped_pixmap)
        elif min_push == push_right:
            x = float(wr);      direction = 1;  label.setPixmap(base_pixmap)
        elif min_push == push_up:
            y = float(wt - ph)
        elif min_push == push_down:
            y = float(wb)

def tick():
    global x, y, direction, bob, bob_dir, state
    global idle_ticks, sit_ticks, climb_target, current_win
    global off_screen_ticks, bubble_ticks, idle_talk_count, _zorder_tick

    pw = base_pixmap.width()
    ph = base_pixmap.height()

    # Bob
    bob += bob_dir
    if abs(bob) >= BOB_RANGE:
        bob_dir *= -1

    # ── Z-order: check fullscreen every tick ───────
    _, fullscreen = get_foreground_info()
    if fullscreen and not _is_topmost:
        go_to_foreground()   # fullscreen → pop on top
    elif not fullscreen and _is_topmost:
        go_to_background()   # fullscreen gone → back to desktop layer

    obstacles = get_obstacles()

    # ── Off-screen guard (always get back within 3s) ──
    is_off = x + pw < 0 or x > screen_w or y + ph < 0 or y > screen_h
    if is_off:
        off_screen_ticks += 1
        if off_screen_ticks >= MAX_OFF_SCREEN:
            x = max(0.0, min(x, float(screen_w - pw)))
            y = float(GROUND_Y)
            state = WALKING
            off_screen_ticks = 0
    else:
        off_screen_ticks = 0

    resolve_push(obstacles)

    # ── STRICT VERTICAL BOUNDARIES ──
    # Prevent Pikachu from being pushed off the top or bottom of the screen.
    # Left and right (X-axis) remain unrestricted here.
    if y < 0:
        y = 0.0
    elif y > GROUND_Y:
        y = float(GROUND_Y)
    # ────────────────────────────────

    # GOAL 4: Keeps updating location/size of topmost active tab
    obstacles = get_obstacles()
    resolve_push(obstacles)

    # GOAL 3: Cannot leave screen through top/bottom boundaries
    if y < 0:
        y = 0.0
    elif y > GROUND_Y:
        y = float(GROUND_Y)

    # Bubble: countdown and follow Pikachu
    if bubble_ticks > 0:
        bubble_ticks -= 1
        bx = int(x) + pw // 2 - bubble.width() // 2
        by = int(y) - bubble.height() - 8
        bubble.move(max(0, min(bx, screen_w - bubble.width())), max(0, by))
        if bubble_ticks == 0:
            bubble.hide()

    # ── WALKING ───────────────────────────────────
    if state == WALKING:
        idle_talk_count = 0
        if rng.random() < IDLE_CHANCE:
            state = IDLE
            idle_ticks = rng.randint(IDLE_MIN_MS, IDLE_MAX_MS) // TICK_MS
            label.move(int(x), int(y + bob))
            return

        x += WALK_SPEED * direction
        if x + pw >= screen_w:
            x = float(screen_w - pw); direction = -1; label.setPixmap(flipped_pixmap)
        elif x <= 0:
            x = 0.0; direction = 1; label.setPixmap(base_pixmap)

        for wl, wt, wr, wb in obstacles:
            if wb < y - 20 or wt > y + ph:
                continue
            hit = (direction == 1  and (x + pw) >= wl and (x + pw) <= wl + WALK_SPEED + 4) or \
                  (direction == -1 and x <= wr and x >= wr - WALK_SPEED - 4)
            if hit:
                roll = rng.random()
                if roll < 0.40:
                    state = CLIMBING; current_win = (wl, wt, wr, wb)
                    climb_target = float(wt - ph)
                    x = float(wl - pw) if direction == 1 else float(wr)
                    ask_llm("I just started climbing up the side of a window!")
                elif roll < 0.80:
                    direction *= -1
                    label.setPixmap(base_pixmap if direction == 1 else flipped_pixmap)
                break

    elif state == IDLE:
        idle_talk_count += 1
        if idle_talk_count == IDLE_TALK_TICKS:
            ask_llm("I have been standing still on the desktop for a while, just chilling.")
        idle_ticks -= 1
        if idle_ticks <= 0:
            state = WALKING; idle_talk_count = 0

    elif state == CLIMBING:
        y -= CLIMB_SPEED
        if y <= climb_target:
            y = climb_target
            if rng.random() < SIT_CHANCE:
                state = SITTING
                sit_ticks = rng.randint(SIT_MIN_MS, SIT_MAX_MS) // TICK_MS
                ask_llm("I just climbed to the top of a window and I am sitting up here!")
            else:
                state = FALLING

    elif state == SITTING:
        sit_ticks -= 1
        if sit_ticks <= 0:
            state = FALLING

    elif state == FALLING:
        y += FALL_SPEED
        if y >= GROUND_Y:
            y = float(GROUND_Y); state = WALKING

    label.move(int(x), int(y + bob))

timer = QTimer()
timer.timeout.connect(tick)
timer.start(TICK_MS)

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