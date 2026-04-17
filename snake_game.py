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
PAUSE_INPUT = "pause"

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
    grid_width: int
    grid_height: int
    cell_size: int


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
        self.phase = "waiting"
        self.direction = "right"
        self.pending_direction = "right"
        self.snake: list[tuple[int, int]] = []
        self.food = (0, 0)
        self.score = 0
        self.reset_waiting()

    def reset_waiting(self) -> None:
        self.phase = "waiting"
        self._reset_body()

    def _reset_body(self, initial_direction: str = "right") -> None:
        self.direction = initial_direction
        self.pending_direction = initial_direction
        center_x = self.grid_width // 2
        center_y = self.grid_height // 2
        dx, dy = DIRECTION_DELTAS[initial_direction]
        self.snake = [
            (center_x - (dx * offset), center_y - (dy * offset)) for offset in range(6)
        ]
        self.score = 0
        self.food = self._spawn_food()

    def _spawn_food(self) -> tuple[int, int]:
        occupied = set(self.snake)
        total_cells = self.grid_width * self.grid_height
        if len(occupied) >= total_cells:
            return self.snake[0]

        for _ in range(total_cells * 2):
            candidate = (
                self.rng.randrange(self.grid_width),
                self.rng.randrange(self.grid_height),
            )
            if candidate not in occupied:
                return candidate

        for y in range(self.grid_height):
            for x in range(self.grid_width):
                if (x, y) not in occupied:
                    return (x, y)

        return self.snake[0]

    def apply_input(self, direction: str) -> None:
        if direction == PAUSE_INPUT:
            if self.phase == "playing":
                self.phase = "paused"
            elif self.phase == "paused":
                self.phase = "playing"
            return

        if direction not in DIRECTION_DELTAS:
            return

        if self.phase in {"waiting", "game_over"}:
            self._reset_body(direction)
            self.phase = "playing"
            return

        if self.phase != "playing":
            return

        if len(self.snake) > 1 and OPPOSITE_DIRECTIONS.get(self.direction) == direction:
            return

        self.pending_direction = direction

    def step(self) -> None:
        if self.phase != "playing":
            return

        self.direction = self.pending_direction
        dx, dy = DIRECTION_DELTAS[self.direction]
        head_x, head_y = self.snake[0]
        next_head = (head_x + dx, head_y + dy)

        if not (0 <= next_head[0] < self.grid_width) or not (
            0 <= next_head[1] < self.grid_height
        ):
            self.phase = "game_over"
            return

        will_grow = next_head == self.food
        collision_body = self.snake if will_grow else self.snake[:-1]
        if next_head in collision_body:
            self.phase = "game_over"
            return

        self.snake.insert(0, next_head)
        if will_grow:
            self.score += 1
            self.food = self._spawn_food()
        else:
            self.snake.pop()

    def tick_seconds(self) -> float:
        speed_tier = self.score // SPEEDUP_FOOD_INTERVAL
        return max(
            MIN_TICK_SECONDS,
            TICK_SECONDS - (speed_tier * SPEEDUP_STEP_SECONDS),
        )

    def snapshot(self) -> SnakeSnapshot:
        return SnakeSnapshot(
            phase=self.phase,
            snake=self.snake[:],
            food=self.food,
            direction=self.direction,
            score=self.score,
            grid_width=self.grid_width,
            grid_height=self.grid_height,
            cell_size=self.cell_size,
        )


def build_snake_payload(game: SnakeGame) -> dict:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    phase_labels = {
        "waiting": "Press any button to start",
        "playing": f"Score {game.score}",
        "paused": f"Paused | Score {game.score}",
        "game_over": f"Game over | Score {game.score}",
    }
    return {
        "slot_key": get_current_slot_key(),
        "time": now,
        "category": "snake_game",
        "data": {
            "state": game.phase,
            "score": game.score,
            "summary": phase_labels.get(game.phase, "Snake Game Mode"),
        },
    }


def _save_snake_state(game: SnakeGame, db_path: str) -> None:
    save_current_display_state(build_snake_payload(game), db_path=db_path)
    set_snake_runtime_status(game.phase, score=game.score, db_path=db_path)


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


def run_snake_mode(display, db_path: str = DB_PATH) -> None:
    game = SnakeGame(width=display.width, height=display.height)
    _save_snake_state(game, db_path)
    last_snapshot = (game.phase, game.score)
    next_step_at = time.perf_counter() + game.tick_seconds()

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

        current_snapshot = (game.phase, game.score)
        if current_snapshot != last_snapshot:
            _save_snake_state(game, db_path)
            last_snapshot = current_snapshot

        snapshot = game.snapshot()
        if snapshot.phase == "waiting":
            frame = display.render_snake_message(["Press any button to start"])
        elif snapshot.phase == "paused":
            frame = display.render_snake_game(snapshot)
        elif snapshot.phase == "game_over":
            frame = display.render_snake_message(
                ["Game Over", f"Score {snapshot.score}", "Press any button"]
            )
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
