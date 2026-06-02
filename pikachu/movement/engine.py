"""pikachu/movement/engine.py — 2D physics and state machine for Pikachu."""

import random
from pikachu import config as cfg
from pikachu.utils.logger import get_logger

log = get_logger(__name__)

# ── States ────────────────────────────────────────────────────────────────────
ROAMING  = "roaming"
IDLE     = "idle"
ESCAPING = "escaping"


class MovementEngine:
    """
    Maintains Pikachu's position, velocity, and behavioural state.

    Call ``update(collision)`` every tick; it returns the new
    ``(x, y, flip, state)`` tuple without touching any Qt objects directly.
    """

    def __init__(self, screen_w: int, screen_h: int,
                 sprite_w: int, sprite_h: int):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.sw       = sprite_w
        self.sh       = sprite_h

        self._rng = random.Random(cfg.RANDOM_SEED)

        # Position and velocity
        self.x   = 100.0
        self.y   = float(screen_h // 2)
        self.vx  = cfg.SPEED
        self.vy  = 0.0

        # Bob (vertical oscillation)
        self._bob     = 0
        self._bob_dir = 1

        # State machine
        self.state          = ROAMING
        self._idle_ticks    = 0
        self._idle_talk_cnt = 0
        self._dir_ticks     = self._rng.randint(cfg.DIR_MIN_TICKS, cfg.DIR_MAX_TICKS)
        self._prev_rect     = None

        # External event flags
        self._force_escape  = False

        log.debug("MovementEngine initialised at (%.0f, %.0f)", self.x, self.y)

    # ── Public API ────────────────────────────────────────────────────────────

    def trigger_escape(self):
        """Force immediate transition to ESCAPING state."""
        self._force_escape = True

    def update(self, collision) -> tuple:
        """
        Advance one tick.

        Args:
            collision: CollisionDetector instance (provides rect + helpers)

        Returns:
            (x, y, flip: bool, state: str, idle_talk_fired: bool)
            flip=True means the sprite should be drawn mirrored (facing left).
            idle_talk_fired=True means Pikachu just hit the idle-talk threshold.
        """
        rect, fullscreen = collision.get_foreground_info()

        # ── Bob ───────────────────────────────────────────────────────────────
        self._bob += self._bob_dir
        if abs(self._bob) >= cfg.BOB_RANGE:
            self._bob_dir *= -1

        flip             = False
        idle_talk_fired  = False

        # ── Force-escape after rect change ────────────────────────────────────
        if self._force_escape or (
            rect != self._prev_rect
            and not fullscreen
            and collision.is_covered(self.x, self.y, rect)
        ):
            self.state         = ESCAPING
            self._force_escape = False
        self._prev_rect = rect

        # ── State machine ─────────────────────────────────────────────────────
        if fullscreen:
            # Pikachu roams freely on top of fullscreen apps
            flip = self._move_freely(collision)

        elif self.state == ROAMING:
            self._idle_talk_cnt = 0
            if self._rng.random() < cfg.IDLE_CHANCE:
                self.state       = IDLE
                self._idle_ticks = self._rng.randint(
                    cfg.IDLE_MIN_MS, cfg.IDLE_MAX_MS
                ) // cfg.TICK_MS
            else:
                flip = self._move_freely(collision)
                if collision.is_covered(self.x, self.y, rect):
                    self.state = ESCAPING

        elif self.state == IDLE:
            self._idle_talk_cnt += 1
            if self._idle_talk_cnt == cfg.IDLE_TALK_TICKS:
                idle_talk_fired = True
            self._idle_ticks -= 1
            if self._idle_ticks <= 0:
                self.state          = ROAMING
                self._idle_talk_cnt = 0
                flip = self._pick_direction()
            if collision.is_covered(self.x, self.y, rect):
                self.state = ESCAPING

        elif self.state == ESCAPING:
            if not collision.is_covered(self.x, self.y, rect):
                self.state = ROAMING
                flip = self._pick_direction()
                # Signal caller to say something ("I escaped!")
                idle_talk_fired = False   # caller checks state == ESCAPING→ROAMING
            else:
                evx, evy    = collision.escape_vector(self.x, self.y, rect)
                self.x, self.y = collision.clamp(self.x + evx, self.y + evy)

        # Compute render position (apply bob)
        render_x = int(self.x)
        render_y = int(self.y + self._bob)

        return render_x, render_y, flip, self.state, idle_talk_fired

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _pick_direction(self) -> bool:
        """Choose a new random non-zero (vx, vy) and reset direction timer."""
        choices = [-cfg.SPEED, 0.0, cfg.SPEED]
        while True:
            nvx = self._rng.choice(choices)
            nvy = self._rng.choice(choices)
            if nvx != 0 or nvy != 0:
                break
        self.vx          = nvx
        self.vy          = nvy
        self._dir_ticks  = self._rng.randint(cfg.DIR_MIN_TICKS, cfg.DIR_MAX_TICKS)
        return self.vx < 0   # True → flip sprite

    def _move_freely(self, collision) -> bool:
        """Apply velocity with screen-edge bouncing. Returns flip flag."""
        self._dir_ticks -= 1
        if self._dir_ticks <= 0:
            return self._pick_direction()

        nx = self.x + self.vx
        ny = self.y + self.vy

        flip = self.vx < 0

        # Left / right bounce
        if nx <= 0:
            nx   = 0.0
            self.vx = abs(self.vx)
            flip = False
        elif nx + self.sw >= self.screen_w:
            nx   = float(self.screen_w - self.sw)
            self.vx = -abs(self.vx)
            flip = True

        # Top / bottom clamp + bounce
        if ny <= 0:
            ny   = 0.0
            self.vy = abs(self.vy)
        elif ny + self.sh >= self.screen_h:
            ny   = float(self.screen_h - self.sh)
            self.vy = -abs(self.vy)

        self.x, self.y = nx, ny
        return flip
