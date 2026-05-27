import sys, os, ctypes, win32gui, random
from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtGui import QPixmap, QTransform
from PyQt5.QtCore import Qt, QTimer

# ── Config ─────────────────────────────────────────
SCALE        = 0.3
GROUND_Y     = 800
WALK_SPEED   = 2
CLIMB_SPEED  = 2
FALL_SPEED   = 5
BOB_RANGE    = 5
TICK_MS      = 20
RANDOM_SEED  = 42

IDLE_CHANCE  = 0.003
IDLE_MIN_MS  = 2000
IDLE_MAX_MS  = 6000

SIT_CHANCE   = 0.5
SIT_MIN_MS   = 3000
SIT_MAX_MS   = 8000
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

# ── Window detection (every tick, no cache) ────────

# These window classes mean "the desktop is in focus, no real app open"
DESKTOP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Button",
                   "DV2ControlHost", "MsgrIMEWindowClass", ""}

def get_obstacles():
    # Only the uppermost focused window counts as an obstacle
    fg = win32gui.GetForegroundWindow()
    if not fg:
        return []

    fg_class = win32gui.GetClassName(fg)

    # Foreground is the desktop or taskbar — no real window is active
    if fg_class in DESKTOP_CLASSES:
        return []

    # Foreground is a real app — use only its rect
    try:
        l, t, r, b = win32gui.GetWindowRect(fg)
    except:
        return []

    # Ignore if minimised or off-screen
    if (r - l) < 150 or (b - t) < 80:
        return []
    if b < 0 or r < 0 or l > screen_w:
        return []

    return [(l, t, r, b)]

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
MAX_OFF_SCREEN   = 3000 // TICK_MS  # 3 seconds

def resolve_push(obstacles):
    """
    Runs every tick regardless of state.
    If any window is overlapping Pikachu right now, push him out
    to the nearest free side immediately.
    """
    global x, y, direction

    pw = base_pixmap.width()
    ph = base_pixmap.height()

    for wl, wt, wr, wb in obstacles:
        # Check if Pikachu's rect overlaps this window
        overlapping = (x < wr and x + pw > wl and y < wb and y + ph > wt)
        if not overlapping:
            continue

        # How deep is the overlap on each side
        push_right = wr - x          # push pikachu to the right of window
        push_left  = (x + pw) - wl   # push pikachu to the left of window
        push_down  = wb - y           # push pikachu downward
        push_up    = (y + ph) - wt   # push pikachu upward

        # Pick the shallowest push direction
        min_push = min(push_right, push_left, push_up, push_down)

        if min_push == push_left:
            x = float(wl - pw)
            direction = -1
            label.setPixmap(flipped_pixmap)
        elif min_push == push_right:
            x = float(wr)
            direction = 1
            label.setPixmap(base_pixmap)
        elif min_push == push_up:
            y = float(wt - ph)
        elif min_push == push_down:
            y = float(wb)

def tick():
    global x, y, direction, bob, bob_dir, state
    global idle_ticks, sit_ticks, climb_target, current_win, off_screen_ticks

    pw = base_pixmap.width()
    ph = base_pixmap.height()

    # Bob always runs
    bob += bob_dir
    if abs(bob) >= BOB_RANGE:
        bob_dir *= -1

    # Fetch fresh window list every tick for real-time push
    obstacles = get_obstacles()

    # ── Off-screen guard ──────────────────────────
    # If pushed outside screen bounds, count ticks and snap back after 3s
    is_off_screen = (x + pw < 0 or x > screen_w or
                     y + ph < 0 or y > screen_h)

    if is_off_screen:
        off_screen_ticks += 1
        if off_screen_ticks >= MAX_OFF_SCREEN:
            # Snap back to nearest screen edge and resume walking
            x = max(0.0, min(x, float(screen_w - pw)))
            y = float(GROUND_Y)
            state            = WALKING
            off_screen_ticks = 0
    else:
        off_screen_ticks = 0

    # ── Push resolution (always, every tick) ──────
    resolve_push(obstacles)

    # ── WALKING ───────────────────────────────────
    if state == WALKING:
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

        # Window wall — decide reaction
        for wl, wt, wr, wb in obstacles:
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
                    state        = CLIMBING
                    current_win  = (wl, wt, wr, wb)
                    climb_target = float(wt - ph)
                    x = float(wl - pw) if direction == 1 else float(wr)
                elif roll < 0.80:
                    direction *= -1
                    label.setPixmap(base_pixmap if direction == 1 else flipped_pixmap)
                break

    elif state == IDLE:
        idle_ticks -= 1
        if idle_ticks <= 0:
            state = WALKING

    elif state == CLIMBING:
        y -= CLIMB_SPEED
        if y <= climb_target:
            y = climb_target
            state = SITTING if rng.random() < SIT_CHANCE else FALLING
            if state == SITTING:
                sit_ticks = rng.randint(SIT_MIN_MS, SIT_MAX_MS) // TICK_MS

    elif state == SITTING:
        sit_ticks -= 1
        if sit_ticks <= 0:
            state = FALLING

    elif state == FALLING:
        y += FALL_SPEED
        if y >= GROUND_Y:
            y     = float(GROUND_Y)
            state = WALKING

    label.move(int(x), int(y + bob))

timer = QTimer()
timer.timeout.connect(tick)
timer.start(TICK_MS)

def contextMenuEvent(e):
    from PyQt5.QtWidgets import QMenu
    menu = QMenu()
    menu.addAction("Close  ✕", app.quit)
    menu.exec_(e.globalPos())

label.contextMenuEvent = contextMenuEvent

sys.exit(app.exec_())