import sys, os, ctypes, win32gui, random
from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtGui import QPixmap, QTransform
from PyQt5.QtCore import Qt, QTimer

# ── Config ─────────────────────────────────────────
SCALE        = 0.3
GROUND_Y     = 800    # Y position pikachu walks along
WALK_SPEED   = 2
CLIMB_SPEED  = 2
FALL_SPEED   = 5
BOB_RANGE    = 5
TICK_MS      = 20
RANDOM_SEED  = 42     # change this number to get different behaviour

# Idle: chance per tick to randomly stop
IDLE_CHANCE  = 0.003  # 0.003 = ~0.3% per tick. raise for more stops
IDLE_MIN_MS  = 2000   # min time stopped (ms)
IDLE_MAX_MS  = 6000   # max time stopped (ms)

# Sitting on top of a window
SIT_CHANCE   = 0.5    # 50% chance to sit after climbing (vs walk off)
SIT_MIN_MS   = 3000
SIT_MAX_MS   = 8000
# ───────────────────────────────────────────────────

rng = random.Random(RANDOM_SEED)

# States
WALKING  = "walking"
IDLE     = "idle"
CLIMBING = "climbing"
SITTING  = "sitting"
FALLING  = "falling"

script_dir = os.path.dirname(os.path.abspath(__file__))
img_path   = os.path.join(script_dir, "pikachu.png")

app = QApplication(sys.argv)
screen_w = app.primaryScreen().geometry().width()

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

# ── Pin to desktop background ──────────────────────
def pin_to_desktop(hwnd):
    progman = win32gui.FindWindow("Progman", None)
    ctypes.windll.user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, None)
    workerw = ctypes.c_ulonglong(0)
    def enum_cb(h, _):
        if win32gui.FindWindowEx(h, 0, "SHELLDLL_DefView", None):
            workerw.value = win32gui.FindWindowEx(0, h, "WorkerW", None)
    win32gui.EnumWindows(enum_cb, None)
    if workerw.value:
        ctypes.windll.user32.SetParent(hwnd, workerw.value)

pin_to_desktop(int(label.winId()))

# ── Window obstacle detection (cached every 1s) ────
_obstacle_cache   = []
_obstacle_refresh = 0
OBSTACLE_REFRESH  = 50  # ticks between refreshes

EXCLUDED_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Button",
                    "DV2ControlHost", "MsgrIMEWindowClass", ""}

def refresh_obstacles():
    result = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if win32gui.GetClassName(hwnd) in EXCLUDED_CLASSES:
            return
        try:
            l, t, r, b = win32gui.GetWindowRect(hwnd)
        except:
            return
        if (r - l) < 150 or (b - t) < 80:
            return
        if b < 0 or r < 0 or l > screen_w:
            return
        result.append((l, t, r, b))
    win32gui.EnumWindows(cb, None)
    return result

def get_obstacles():
    global _obstacle_cache, _obstacle_refresh
    _obstacle_refresh -= 1
    if _obstacle_refresh <= 0:
        _obstacle_cache   = refresh_obstacles()
        _obstacle_refresh = OBSTACLE_REFRESH
    return _obstacle_cache

# ── Movement state ─────────────────────────────────
x             = 100.0
y             = float(GROUND_Y)
direction     = 1
bob           = 0
bob_dir       = 1
state         = WALKING
idle_ticks    = 0
sit_ticks     = 0
climb_target  = 0.0
current_win   = None  # window being climbed

def tick():
    global x, y, direction, bob, bob_dir, state
    global idle_ticks, sit_ticks, climb_target, current_win

    pw = base_pixmap.width()
    ph = base_pixmap.height()

    # Bob
    bob += bob_dir
    if abs(bob) >= BOB_RANGE:
        bob_dir *= -1

    # ── WALKING ───────────────────────────────────
    if state == WALKING:

        # Random idle chance
        if rng.random() < IDLE_CHANCE:
            state = IDLE
            idle_ticks = rng.randint(IDLE_MIN_MS, IDLE_MAX_MS) // TICK_MS
            label.move(int(x), int(y + bob))
            return

        x += WALK_SPEED * direction

        # Screen edges
        if x + pw >= screen_w:
            x = float(screen_w - pw)
            direction = -1
            label.setPixmap(flipped_pixmap)
        elif x <= 0:
            x = 0.0
            direction = 1
            label.setPixmap(base_pixmap)

        # Window collision check
        for win in get_obstacles():
            wl, wt, wr, wb = win

            # Only care about windows whose bottom is near ground level
            if wb < y - 20 or wt > y + ph:
                continue

            hit = False
            if direction == 1  and (x + pw) >= wl and (x + pw) <= wl + WALK_SPEED + 4:
                hit = True
            elif direction == -1 and x <= wr and x >= wr - WALK_SPEED - 4:
                hit = True

            if hit:
                roll = rng.random()
                if roll < 0.40:
                    # Climb up the wall
                    state        = CLIMBING
                    current_win  = win
                    climb_target = float(wt - ph)
                    x = float(wl - pw) if direction == 1 else float(wr)
                elif roll < 0.80:
                    # Turn around
                    direction *= -1
                    label.setPixmap(base_pixmap if direction == 1 else flipped_pixmap)
                # else 20%: ignore and walk through
                break

    # ── IDLE ──────────────────────────────────────
    elif state == IDLE:
        idle_ticks -= 1
        if idle_ticks <= 0:
            state = WALKING

    # ── CLIMBING ──────────────────────────────────
    elif state == CLIMBING:
        y -= CLIMB_SPEED
        if y <= climb_target:
            y = climb_target
            if rng.random() < SIT_CHANCE:
                # Sit on top for a while
                state     = SITTING
                sit_ticks = rng.randint(SIT_MIN_MS, SIT_MAX_MS) // TICK_MS
            else:
                # Skip sitting, fall straight back down
                state = FALLING

    # ── SITTING ───────────────────────────────────
    elif state == SITTING:
        sit_ticks -= 1
        if sit_ticks <= 0:
            state = FALLING

    # ── FALLING ───────────────────────────────────
    elif state == FALLING:
        y += FALL_SPEED
        if y >= GROUND_Y:
            y     = float(GROUND_Y)
            state = WALKING

    label.move(int(x), int(y + bob))

timer = QTimer()
timer.timeout.connect(tick)
timer.start(TICK_MS)

# Right-click to close
def contextMenuEvent(e):
    from PyQt5.QtWidgets import QMenu
    menu = QMenu()
    menu.addAction("Close  ✕", app.quit)
    menu.exec_(e.globalPos())

label.contextMenuEvent = contextMenuEvent

sys.exit(app.exec_())