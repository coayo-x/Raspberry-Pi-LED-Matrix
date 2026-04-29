import random
import time
from dataclasses import dataclass

from config import DB_PATH
from current_display_state import save_current_display_state
from rotation_engine import get_current_slot_key
from snake_control import (
    consume_snake_input,
    is_snake_mode_enabled,
    set_snake_runtime_status,
)

CELL_SIZE = 2
TICK_SECONDS = 0.12
FRAME_SECONDS = 0.035
SPEEDUP_FOOD_INTERVAL = 3
SPEEDUP_STEP_SECONDS = 0.01
MIN_TICK_SECONDS = 0.07
MAX_LEVEL = 10
FOOD_PER_LEVEL = 10
LEVEL_SPEED_STEP_SECONDS = 0.002
LEVEL_INTRO_HOLD_SECONDS = 0.28
LEVEL_INTRO_FADE_DELAY_SECONDS = 0.035
GAME_OVER_PULSE_FRAME_SECONDS = 0.08
PAUSE_INPUT = "pause"
SCORE_OVERLAY_HEIGHT_PX = 8
SCORE_OVERLAY_TEXT_X_PX = 1
SCORE_OVERLAY_RIGHT_PADDING_PX = 3
SCORE_OVERLAY_CHAR_WIDTH_PX = 6
SCORE_OVERLAY_RESERVED_SCORE = 999
HUD_RESERVED_HEIGHT_PX = 12

DIRECTION_DELTAS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}
OPPOSITE_DIRECTIONS = {
    "up": "down",
    "down": "up",
    "left": "right",
    "right": "left",
}


@dataclass
class SnakeSnapshot:
    phase: str
    snake: list[tuple[int, int]]
    food: tuple[int, int]
    direction: str
    score: int
    level: int
    level_food_count: int
    grid_width: int
    grid_height: int
    cell_size: int
    score_overlay_cells: tuple[int, int]
    playfield_bounds: tuple[int, int, int, int]
    hud_notch_cells: tuple[int, int]
    obstacles: list[tuple[int, int]]
    pulse_factor: float = 1.0


def _ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def score_overlay_text(score: int, level: int | None = None) -> str:
    safe_score = max(0, int(score))
    return str(safe_score)


def score_overlay_size_px(score: int, level: int | None = None) -> tuple[int, int]:
    score_text_length = len(score_overlay_text(score, level))
    return (
        SCORE_OVERLAY_TEXT_X_PX
        + (score_text_length * SCORE_OVERLAY_CHAR_WIDTH_PX)
        + SCORE_OVERLAY_RIGHT_PADDING_PX,
        SCORE_OVERLAY_HEIGHT_PX,
    )


class SnakeGame:
    def __init__(
        self,
        *,
        width: int,
        height: int,
        cell_size: int = CELL_SIZE,
        rng: random.Random | None = None,
    ) -> None:
        self.cell_size = max(1, cell_size)
        self.grid_width = max(4, width // self.cell_size)
        self.grid_height = max(4, height // self.cell_size)
        self.rng = rng or random.Random()
        self.playfield_bounds = self._build_playfield_bounds()
        self.hud_notch_cells = self._build_hud_notch_cells()
        self.phase = "waiting"
        self.direction = "right"
        self.pending_direction = "right"
        self.snake: list[tuple[int, int]] = []
        self.obstacles: set[tuple[int, int]] = set()
        self.food = (0, 0)
        self.score = 0
        self.level = 1
        self.level_food_count = 0
        self.level_intro_reset_score = False
        self.level_intro_source_phase = "waiting"
        self.game_over_animation_pending = False
        self.reset_waiting()

    def _build_playfield_bounds(self) -> tuple[int, int, int, int]:
        left = 1
        top = 1
        right = max(left, self.grid_width - 2)
        bottom = max(1, self.grid_height - 2)
        return left, top, right, bottom

    def _build_hud_notch_cells(self) -> tuple[int, int]:
        notch_right, _ = self._score_overlay_cell_bounds_for_score(
            SCORE_OVERLAY_RESERVED_SCORE,
            level=MAX_LEVEL,
        )
        _, top, _, bottom = self.playfield_bounds
        notch_bottom = _ceil_div(HUD_RESERVED_HEIGHT_PX, self.cell_size)
        return (
            min(self.grid_width, max(2, notch_right)),
            min(bottom, max(top + 1, notch_bottom)),
        )

    def _is_hud_notch_cell(self, cell: tuple[int, int]) -> bool:
        cell_x, cell_y = cell
        left, top, _, _ = self.playfield_bounds
        notch_right, notch_bottom = self.hud_notch_cells
        return left <= cell_x < notch_right and top <= cell_y < notch_bottom

    def _is_playfield_cell(self, cell: tuple[int, int]) -> bool:
        cell_x, cell_y = cell
        left, top, right, bottom = self.playfield_bounds
        return (
            left <= cell_x <= right
            and top <= cell_y <= bottom
            and not self._is_hud_notch_cell(cell)
        )

    def _playfield_cell_count(self) -> int:
        left, top, right, bottom = self.playfield_bounds
        notch_right, notch_bottom = self.hud_notch_cells
        outer_cells = max(0, right - left + 1) * max(0, bottom - top + 1)
        notch_cells = max(0, min(right + 1, notch_right) - left) * max(
            0, min(bottom + 1, notch_bottom) - top
        )
        return max(0, outer_cells - notch_cells)

    def reset_waiting(self) -> None:
        self.phase = "waiting"
        self.level = 1
        self.score = 0
        self.level_food_count = 0
        self.level_intro_reset_score = False
        self.level_intro_source_phase = "waiting"
        self.game_over_animation_pending = False
        self._reset_body(reset_score=False)

    def _level_base_score(self) -> int:
        return (self.level - 1) * FOOD_PER_LEVEL

    def _reset_body(
        self,
        initial_direction: str = "right",
        *,
        reset_score: bool = False,
    ) -> None:
        self.direction = initial_direction
        self.pending_direction = initial_direction
        dx, dy = DIRECTION_DELTAS[initial_direction]
        self.obstacles = self._build_level_obstacles(self.level)
        if reset_score:
            self.score = self._level_base_score()
            self.level_food_count = 0
        self.snake = self._initial_snake_cells(initial_direction, dx, dy)
        self.food = self._spawn_food()

    def _initial_snake_cells(
        self,
        initial_direction: str,
        dx: int,
        dy: int,
    ) -> list[tuple[int, int]]:
        left, top, right, bottom = self.playfield_bounds
        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        _, overlay_height = self._score_overlay_cell_bounds_for_score(
            SCORE_OVERLAY_RESERVED_SCORE,
            level=MAX_LEVEL,
        )
        candidate_heads = [
            (center_x, center_y),
            (center_x, max(top + 2, bottom - 2)),
            (max(left + 5, left + ((right - left + 1) // 4)), center_y),
            (min(right - 2, left + (((right - left + 1) * 3) // 4)), center_y),
        ]
        for head_x, head_y in candidate_heads:
            snake = [
                (head_x - (dx * offset), head_y - (dy * offset)) for offset in range(6)
            ]
            if all(
                self._is_playfield_cell((cell_x, cell_y))
                and (cell_x, cell_y) not in self.obstacles
                and not self._is_score_overlay_cell((cell_x, cell_y))
                for cell_x, cell_y in snake
            ):
                return snake

        fallback_y = min(bottom, max(top, center_y, overlay_height + 1))
        fallback_x = min(right, max(left + 5, center_x))
        return [
            (max(left, fallback_x - offset), fallback_y)
            for offset in range(min(6, right - left + 1))
        ]

    def _is_reserved_obstacle_cell(self, cell: tuple[int, int]) -> bool:
        cell_x, cell_y = cell
        if not self._is_playfield_cell(cell):
            return True

        overlay_width, overlay_height = self._score_overlay_cell_bounds_for_score(
            SCORE_OVERLAY_RESERVED_SCORE,
            level=MAX_LEVEL,
        )
        if 0 <= cell_x < overlay_width and 0 <= cell_y < overlay_height:
            return True

        left, top, right, bottom = self.playfield_bounds
        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        return abs(cell_x - center_x) <= 8 and abs(cell_y - center_y) <= 1

    def _build_level_obstacles(self, level: int) -> set[tuple[int, int]]:
        safe_level = max(1, min(MAX_LEVEL, int(level)))
        obstacles: set[tuple[int, int]] = set()

        def add(cell_x: int, cell_y: int) -> None:
            cell = (cell_x, cell_y)
            if self._is_playfield_cell(cell) and not self._is_reserved_obstacle_cell(
                cell
            ):
                obstacles.add(cell)

        def hline(
            y: int, x0: int, x1: int, *, gap: tuple[int, int] | None = None
        ) -> None:
            play_left, _, play_right, _ = self.playfield_bounds
            start = max(play_left, min(x0, x1))
            end = min(play_right, max(x0, x1))
            for x in range(start, end + 1):
                if gap is not None and gap[0] <= x <= gap[1]:
                    continue
                add(x, y)

        def vline(
            x: int, y0: int, y1: int, *, gap: tuple[int, int] | None = None
        ) -> None:
            _, play_top, _, play_bottom = self.playfield_bounds
            start = max(play_top, min(y0, y1))
            end = min(play_bottom, max(y0, y1))
            for y in range(start, end + 1):
                if gap is not None and gap[0] <= y <= gap[1]:
                    continue
                add(x, y)

        def block(x0: int, y0: int, width: int, height: int) -> None:
            for y in range(y0, y0 + height):
                for x in range(x0, x0 + width):
                    add(x, y)

        play_left, play_top, play_right, play_bottom = self.playfield_bounds
        play_width = play_right - play_left + 1
        cx = (play_left + play_right) // 2
        cy = (play_top + play_bottom) // 2
        left = max(play_left + 4, play_left + (play_width // 4))
        right = min(play_right - 4, play_left + ((play_width * 3) // 4))
        upper_lane_y = play_top + 3
        lower_lane_y = play_bottom - 3

        if safe_level >= 2:
            vline(left, play_top + 2, cy - 1)
            vline(right, cy + 1, play_bottom - 2)

        if safe_level >= 3:
            hline(upper_lane_y, left + 4, cx - 8, gap=(cx - 14, cx - 10))
            hline(lower_lane_y, cx + 8, right - 4, gap=(cx + 10, cx + 14))

        if safe_level >= 4:
            vline(cx - 16, play_top + 1, play_bottom - 1, gap=(cy - 2, cy + 2))
            vline(cx + 16, play_top + 1, play_bottom - 1, gap=(cy - 2, cy + 2))

        if safe_level >= 5:
            block(play_left + 13, play_top + 1, 5, 2)
            block(play_right - 17, play_top + 1, 5, 2)
            block(play_left + 9, play_bottom - 2, 5, 2)
            block(play_right - 13, play_bottom - 2, 5, 2)

        if safe_level >= 6:
            hline(cy - 2, cx - 12, cx + 12, gap=(cx - 2, cx + 2))
            hline(cy + 2, cx - 12, cx + 12, gap=(cx - 2, cx + 2))

        if safe_level >= 7:
            for offset in range(5):
                add(cx - 24 + (offset * 2), cy - 4 + offset)
                add(cx + 24 - (offset * 2), cy + 4 - offset)

        if safe_level >= 8:
            hline(cy - 4, cx - 10, cx + 10, gap=(cx - 2, cx + 2))
            hline(cy + 4, cx - 10, cx + 10, gap=(cx - 2, cx + 2))
            vline(cx - 10, cy - 4, cy + 4, gap=(cy - 1, cy + 1))
            vline(cx + 10, cy - 4, cy + 4, gap=(cy - 1, cy + 1))

        if safe_level >= 9:
            for x in (cx - 26, cx, cx + 26):
                vline(x, play_top + 1, play_top + 4)
                vline(x, play_bottom - 4, play_bottom - 1)

        if safe_level >= 10:
            hline(play_top + 1, cx - 22, cx + 22, gap=(cx - 6, cx + 6))
            hline(play_bottom - 1, cx - 22, cx + 22, gap=(cx - 6, cx + 6))
            vline(cx - 28, play_top + 2, play_bottom - 2, gap=(cy - 2, cy + 2))
            vline(cx + 28, play_top + 2, play_bottom - 2, gap=(cy - 2, cy + 2))

        return obstacles

    def _spawn_food(self) -> tuple[int, int]:
        occupied = set(self.snake) | set(self.obstacles)
        total_cells = self._playfield_cell_count()
        if len(occupied) >= total_cells:
            return self.snake[0]

        for _ in range(total_cells * 2):
            candidate = (
                self.rng.randrange(self.grid_width),
                self.rng.randrange(self.grid_height),
            )
            if (
                self._is_playfield_cell(candidate)
                and candidate not in occupied
                and not self._is_score_overlay_cell(candidate)
            ):
                return candidate

        left, top, right, bottom = self.playfield_bounds
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                candidate = (x, y)
                if (
                    self._is_playfield_cell(candidate)
                    and candidate not in occupied
                    and not self._is_score_overlay_cell(candidate)
                ):
                    return (x, y)

        return self.snake[0]

    def _score_overlay_cell_bounds_for_score(
        self,
        score: int,
        *,
        level: int | None = None,
    ) -> tuple[int, int]:
        width_px, height_px = score_overlay_size_px(
            score,
            self.level if level is None else level,
        )
        return (
            min(self.grid_width, max(1, _ceil_div(width_px, self.cell_size))),
            min(self.grid_height, max(1, _ceil_div(height_px, self.cell_size))),
        )

    def _score_overlay_cell_bounds(self) -> tuple[int, int]:
        return self._score_overlay_cell_bounds_for_score(self.score)

    def _is_score_overlay_cell(self, cell: tuple[int, int]) -> bool:
        cell_x, cell_y = cell
        overlay_width, overlay_height = self._score_overlay_cell_bounds()
        return 0 <= cell_x < overlay_width and 0 <= cell_y < overlay_height

    def _apply_cheat_level(self, cheat_input: str) -> None:
        if self.phase == "level_intro":
            return
        try:
            target_level = int(cheat_input.removeprefix("cheat_level_"))
        except ValueError:
            return
        if target_level < 1 or target_level > MAX_LEVEL:
            return
        self.level = target_level
        self._queue_level_intro(self.pending_direction, reset_score=True)

    def apply_input(self, direction: str) -> None:
        if direction.startswith("cheat_level_"):
            self._apply_cheat_level(direction)
            return

        if direction == PAUSE_INPUT:
            if self.phase == "waiting":
                self._queue_level_intro(self.pending_direction, reset_score=True)
                return
            if self.phase == "game_over":
                self._queue_level_intro(self.pending_direction, reset_score=True)
                return
            if self.phase == "playing":
                self.phase = "paused"
            elif self.phase == "paused":
                self.phase = "playing"
            return

        if direction not in DIRECTION_DELTAS:
            return

        if self.phase == "waiting":
            self._queue_level_intro(direction, reset_score=True)
            return

        if self.phase == "game_over":
            self._queue_level_intro(direction, reset_score=True)
            return

        if self.phase != "playing":
            return

        if len(self.snake) > 1 and OPPOSITE_DIRECTIONS.get(self.direction) == direction:
            return

        self.pending_direction = direction

    def _queue_level_intro(self, direction: str, *, reset_score: bool) -> None:
        self.pending_direction = direction if direction in DIRECTION_DELTAS else "right"
        self.level_intro_reset_score = reset_score
        self.level_intro_source_phase = self.phase
        self.phase = "level_intro"
        self.game_over_animation_pending = False

    def begin_level_after_intro(self) -> None:
        self._reset_body(
            self.pending_direction,
            reset_score=self.level_intro_reset_score,
        )
        self.phase = "playing"
        self.level_intro_reset_score = False
        self.level_intro_source_phase = "playing"

    def step(self) -> None:
        if self.phase != "playing":
            return

        self.direction = self.pending_direction
        dx, dy = DIRECTION_DELTAS[self.direction]
        head_x, head_y = self.snake[0]
        next_head = (head_x + dx, head_y + dy)

        if not self._is_playfield_cell(next_head):
            self.phase = "game_over"
            self.game_over_animation_pending = True
            return

        will_grow = next_head == self.food
        collision_body = self.snake if will_grow else self.snake[:-1]
        if next_head in collision_body or next_head in self.obstacles:
            self.phase = "game_over"
            self.game_over_animation_pending = True
            return

        self.snake.insert(0, next_head)
        if will_grow:
            self.score += 1
            self.level_food_count += 1
            if self.level_food_count >= FOOD_PER_LEVEL and self.level < MAX_LEVEL:
                self.level += 1
                self.level_food_count = 0
                self._queue_level_intro(self.direction, reset_score=False)
                return
            self.food = self._spawn_food()
        else:
            self.snake.pop()

    def tick_seconds(self) -> float:
        speed_tier = self.score // SPEEDUP_FOOD_INTERVAL
        level_pressure = (self.level - 1) * LEVEL_SPEED_STEP_SECONDS
        return max(
            MIN_TICK_SECONDS,
            TICK_SECONDS - (speed_tier * SPEEDUP_STEP_SECONDS) - level_pressure,
        )

    def snapshot(self, *, pulse_factor: float = 1.0) -> SnakeSnapshot:
        return SnakeSnapshot(
            phase=self.phase,
            snake=self.snake[:],
            food=self.food,
            direction=self.direction,
            score=self.score,
            level=self.level,
            level_food_count=self.level_food_count,
            grid_width=self.grid_width,
            grid_height=self.grid_height,
            cell_size=self.cell_size,
            score_overlay_cells=self._score_overlay_cell_bounds(),
            playfield_bounds=self.playfield_bounds,
            hud_notch_cells=self.hud_notch_cells,
            obstacles=sorted(self.obstacles),
            pulse_factor=max(0.0, float(pulse_factor)),
        )


def build_snake_payload(game: SnakeGame) -> dict:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    phase_labels = {
        "waiting": "Press any button to start",
        "level_intro": f"Level {game.level} starting",
        "playing": f"Level {game.level} | Score {game.score}",
        "paused": f"Paused | Level {game.level} | Score {game.score}",
        "game_over": (
            f"LOSER! | Score {game.score} | "
            f"Press any button to play level {game.level} again"
        ),
    }
    return {
        "slot_key": get_current_slot_key(),
        "time": now,
        "category": "snake_game",
        "data": {
            "state": game.phase,
            "score": game.score,
            "level": game.level,
            "level_food_count": game.level_food_count,
            "foods_until_next_level": (
                max(0, FOOD_PER_LEVEL - game.level_food_count)
                if game.level < MAX_LEVEL
                else 0
            ),
            "summary": phase_labels.get(game.phase, "Snake Game Mode"),
        },
    }


def _save_snake_state(game: SnakeGame, db_path: str) -> None:
    save_current_display_state(build_snake_payload(game), db_path=db_path)
    set_snake_runtime_status(
        game.phase,
        score=game.score,
        level=game.level,
        db_path=db_path,
    )


def _snake_frame_sleep_seconds(
    phase: str,
    next_step_at: float,
    *,
    now: float | None = None,
) -> float:
    if phase != "playing":
        return FRAME_SECONDS

    current = time.perf_counter() if now is None else now
    return min(FRAME_SECONDS, max(0.0, next_step_at - current))


def _runtime_snapshot_key(game: SnakeGame) -> tuple[str, int, int, int]:
    return (game.phase, game.score, game.level, game.level_food_count)


def _snake_game_over_message_lines(game: SnakeGame) -> list[str]:
    return [
        "LOSER!",
        f"Score: {game.score}",
        f"Press any button to play level {game.level} again",
    ]


def _sleep_with_snake_interrupt(
    duration: float,
    should_interrupt,
    *,
    interval: float = 0.02,
) -> bool:
    if duration <= 0:
        return bool(should_interrupt and should_interrupt())

    end_time = time.perf_counter() + duration
    while time.perf_counter() < end_time:
        if should_interrupt and should_interrupt():
            return True
        time.sleep(min(interval, max(0.0, end_time - time.perf_counter())))
    return bool(should_interrupt and should_interrupt())


def _fade_snake_frame(
    display,
    frame,
    *,
    fade_in: bool,
    should_interrupt,
    steps: int = 6,
    delay: float = LEVEL_INTRO_FADE_DELAY_SECONDS,
) -> bool:
    fade_sequence = getattr(display, "_fade_sequence", None)
    if callable(fade_sequence):
        return bool(
            fade_sequence(
                frame,
                steps=steps,
                fade_in=fade_in,
                delay=delay,
                should_interrupt=should_interrupt,
            )
        )

    if fade_in:
        display.show_image(frame, preview_name="snake_game.png")
    return _sleep_with_snake_interrupt(delay * steps, should_interrupt)


def _transition_snake_frame(
    display,
    frame,
    *,
    should_interrupt,
    steps: int = 5,
    delay: float = 0.025,
) -> bool:
    transition_to = getattr(display, "_transition_to", None)
    if callable(transition_to):
        return bool(
            transition_to(
                frame,
                preview_name="snake_game.png",
                steps=steps,
                delay=delay,
                should_interrupt=should_interrupt,
            )
        )

    display.show_image(frame, preview_name="snake_game.png")
    return _sleep_with_snake_interrupt(delay * steps, should_interrupt)


def _show_snake_level_intro_sequence(
    display,
    game: SnakeGame,
    *,
    should_interrupt,
) -> bool:
    source_phase = game.level_intro_source_phase
    if source_phase == "waiting":
        outgoing = display.render_snake_message(["Press any button to start"])
        if _fade_snake_frame(
            display,
            outgoing,
            fade_in=False,
            should_interrupt=should_interrupt,
            steps=5,
            delay=0.03,
        ):
            return True
    elif source_phase == "game_over":
        outgoing = display.render_snake_message(_snake_game_over_message_lines(game))
        if _fade_snake_frame(
            display,
            outgoing,
            fade_in=False,
            should_interrupt=should_interrupt,
            steps=5,
            delay=0.03,
        ):
            return True
    level_lines = [f"LEVEL {game.level}"]
    if source_phase == "playing":
        level_lines = ["LEVEL UP", f"LEVEL {game.level}"]

    level_frame = display.render_snake_message(level_lines)
    if source_phase == "playing":
        if _transition_snake_frame(
            display,
            level_frame,
            should_interrupt=should_interrupt,
        ):
            return True
        return _sleep_with_snake_interrupt(
            LEVEL_INTRO_HOLD_SECONDS,
            should_interrupt,
        )

    if _fade_snake_frame(
        display,
        level_frame,
        fade_in=True,
        should_interrupt=should_interrupt,
        steps=6,
    ):
        return True
    if _sleep_with_snake_interrupt(
        LEVEL_INTRO_HOLD_SECONDS,
        should_interrupt,
    ):
        return True
    return _fade_snake_frame(
        display,
        level_frame,
        fade_in=False,
        should_interrupt=should_interrupt,
        steps=5,
        delay=0.025,
    )


def _show_snake_game_over_pulse(
    display,
    game: SnakeGame,
    *,
    should_interrupt,
) -> bool:
    for factor in (1.0, 0.55, 1.15, 0.55, 1.0):
        if should_interrupt and should_interrupt():
            return True
        frame = display.render_snake_game(game.snapshot(pulse_factor=factor))
        display.show_image(frame, preview_name="snake_game.png")
        if _sleep_with_snake_interrupt(
            GAME_OVER_PULSE_FRAME_SECONDS,
            should_interrupt,
        ):
            return True
    return False


def run_snake_mode(display, db_path: str = DB_PATH) -> None:
    game = SnakeGame(width=display.width, height=display.height)
    _save_snake_state(game, db_path)
    last_snapshot = _runtime_snapshot_key(game)
    next_step_at = time.perf_counter() + game.tick_seconds()

    def should_stop_snake() -> bool:
        return not is_snake_mode_enabled(db_path)

    while is_snake_mode_enabled(db_path):
        consumed_input = consume_snake_input(db_path)
        if consumed_input is not None:
            _, direction = consumed_input
            previous_phase = game.phase
            game.apply_input(direction)
            if previous_phase != "playing" and game.phase == "playing":
                resumed_at = time.perf_counter()
                if previous_phase == "paused":
                    next_step_at = resumed_at + game.tick_seconds()
                else:
                    next_step_at = resumed_at

        now = time.perf_counter()
        if game.phase == "playing" and now >= next_step_at:
            game.step()
            next_step_at = time.perf_counter() + game.tick_seconds()
        elif game.phase != "playing":
            next_step_at = now + game.tick_seconds()

        current_snapshot = _runtime_snapshot_key(game)
        if current_snapshot != last_snapshot:
            _save_snake_state(game, db_path)
            last_snapshot = current_snapshot

        if game.phase == "level_intro":
            if _show_snake_level_intro_sequence(
                display,
                game,
                should_interrupt=should_stop_snake,
            ):
                break
            game.begin_level_after_intro()
            next_step_at = time.perf_counter() + game.tick_seconds()
            current_snapshot = _runtime_snapshot_key(game)
            if current_snapshot != last_snapshot:
                _save_snake_state(game, db_path)
                last_snapshot = current_snapshot

        if game.phase == "game_over" and game.game_over_animation_pending:
            if _show_snake_game_over_pulse(
                display,
                game,
                should_interrupt=should_stop_snake,
            ):
                break
            game.game_over_animation_pending = False

        snapshot = game.snapshot()
        if snapshot.phase == "waiting":
            frame = display.render_snake_message(["Press any button to start"])
        elif snapshot.phase == "paused":
            frame = display.render_snake_game(snapshot)
        elif snapshot.phase == "game_over":
            frame = display.render_snake_message(_snake_game_over_message_lines(game))
        elif snapshot.phase == "level_intro":
            frame = display.render_snake_message([f"LEVEL {snapshot.level}"])
        else:
            frame = display.render_snake_game(snapshot)

        display.show_image(frame, preview_name="snake_game.png")
        sleep_seconds = _snake_frame_sleep_seconds(
            game.phase,
            next_step_at,
        )
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    set_snake_runtime_status("idle", score=0, db_path=db_path)


def render_snake_waiting_once(display, db_path: str = DB_PATH) -> dict:
    game = SnakeGame(width=display.width, height=display.height)
    payload = build_snake_payload(game)
    save_current_display_state(payload, db_path=db_path)
    set_snake_runtime_status("waiting", score=0, db_path=db_path)
    display.show_image(
        display.render_snake_message(["Press any button to start"]),
        preview_name="snake_game.png",
    )
    return payload
