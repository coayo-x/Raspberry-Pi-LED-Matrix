import random

import pytest

import snake_game
from snake_game import (
    FRAME_SECONDS,
    MIN_TICK_SECONDS,
    SPEEDUP_FOOD_INTERVAL,
    SPEEDUP_STEP_SECONDS,
    TICK_SECONDS,
    SnakeGame,
    _snake_frame_sleep_seconds,
)


class SequenceRng:
    def __init__(self, values: list[int]) -> None:
        self.values = iter(values)

    def randrange(self, stop: int) -> int:
        value = next(self.values)
        assert 0 <= value < stop
        return value


class ConstantRng:
    def __init__(self, value: int) -> None:
        self.value = value

    def randrange(self, stop: int) -> int:
        assert 0 <= self.value < stop
        return self.value


def _first_visible_food_cell(game: SnakeGame) -> tuple[int, int]:
    occupied = set(game.snake)
    for y in range(game.grid_height):
        for x in range(game.grid_width):
            candidate = (x, y)
            if candidate not in occupied and not game._is_score_overlay_cell(candidate):
                return candidate
    raise AssertionError("No visible food cell available")


def test_snake_waits_until_first_control_input() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    original_head = game.snake[0]

    game.step()
    assert game.phase == "waiting"
    assert game.snake[0] == original_head

    game.apply_input("up")
    assert game.phase == "playing"
    assert game.direction == "up"


def test_snake_pause_toggles_only_during_gameplay() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    waiting_head = game.snake[0]

    game.apply_input("pause")
    assert game.phase == "waiting"
    assert game.snake[0] == waiting_head

    game.apply_input("right")
    game.apply_input("pause")
    paused_head = game.snake[0]
    game.step()

    assert game.phase == "paused"
    assert game.snake[0] == paused_head

    game.apply_input("pause")
    assert game.phase == "playing"


def test_snake_rejects_invalid_reverse_direction() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    game.apply_input("right")
    game.apply_input("left")

    assert game.phase == "playing"
    assert game.pending_direction == "right"


def test_snake_grows_after_eating_food() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    game.apply_input("right")
    head_x, head_y = game.snake[0]
    game.food = (head_x + 1, head_y)
    original_length = len(game.snake)

    game.step()

    assert game.phase == "playing"
    assert game.score == 1
    assert len(game.snake) == original_length + 1


def test_snake_food_spawn_skips_score_overlay_random_candidates() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    game.snake = [(50, 10)]
    overlay_width, overlay_height = game._score_overlay_cell_bounds()
    visible_food = _first_visible_food_cell(game)
    game.rng = SequenceRng(
        [
            0,
            0,
            overlay_width - 1,
            overlay_height - 1,
            visible_food[0],
            visible_food[1],
        ]
    )

    assert game._spawn_food() == visible_food


def test_snake_food_spawn_fallback_skips_score_overlay_cells() -> None:
    game = SnakeGame(width=192, height=32, rng=ConstantRng(0))
    game.snake = [(50, 10)]

    assert game._spawn_food() == _first_visible_food_cell(game)


def test_snake_food_spawn_after_eating_respects_score_overlay() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    game.apply_input("right")
    head_x, head_y = game.snake[0]
    game.food = (head_x + 1, head_y)
    visible_food = _first_visible_food_cell(game)
    game.rng = SequenceRng([0, 0, visible_food[0], visible_food[1]])

    game.step()

    assert game.score == 1
    assert game.food == visible_food
    assert not game._is_score_overlay_cell(game.food)


def test_snake_speed_increases_every_three_food_items() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))

    assert game.tick_seconds() == TICK_SECONDS
    game.score = SPEEDUP_FOOD_INTERVAL - 1
    assert game.tick_seconds() == TICK_SECONDS
    game.score = SPEEDUP_FOOD_INTERVAL
    assert game.tick_seconds() == pytest.approx(TICK_SECONDS - SPEEDUP_STEP_SECONDS)
    game.score = SPEEDUP_FOOD_INTERVAL * 2
    assert game.tick_seconds() == pytest.approx(
        TICK_SECONDS - (SPEEDUP_STEP_SECONDS * 2)
    )
    game.score = 999
    assert game.tick_seconds() == MIN_TICK_SECONDS


def test_snake_detects_wall_and_self_collision() -> None:
    wall_game = SnakeGame(width=192, height=32, rng=random.Random(1))
    wall_game.apply_input("right")
    wall_game.snake = [(wall_game.grid_width - 1, 1), (wall_game.grid_width - 2, 1)]
    wall_game.direction = "right"
    wall_game.pending_direction = "right"

    wall_game.step()
    assert wall_game.phase == "game_over"

    self_game = SnakeGame(width=192, height=32, rng=random.Random(1))
    self_game.apply_input("left")
    self_game.snake = [(5, 5), (5, 6), (4, 6), (4, 5), (4, 4), (5, 4)]
    self_game.direction = "left"
    self_game.pending_direction = "left"

    self_game.step()
    assert self_game.phase == "game_over"


def test_snake_frame_sleep_wakes_for_next_movement_tick() -> None:
    assert _snake_frame_sleep_seconds("waiting", 10.0, now=9.99) == FRAME_SECONDS
    assert _snake_frame_sleep_seconds("game_over", 10.0, now=9.99) == FRAME_SECONDS
    assert _snake_frame_sleep_seconds("playing", 10.0, now=9.0) == FRAME_SECONDS
    assert _snake_frame_sleep_seconds("playing", 10.0, now=9.99) == pytest.approx(0.01)
    assert _snake_frame_sleep_seconds("playing", 10.0, now=10.01) == 0.0


def test_run_snake_mode_pause_stops_motion_and_resume_waits_for_next_tick(
    monkeypatch,
) -> None:
    class FakeClock:
        def __init__(self) -> None:
            self.now = 0.0

        def perf_counter(self) -> float:
            return self.now

        def sleep(self, duration: float) -> None:
            self.now += max(0.0, duration)

    class FakeDisplay:
        width = 192
        height = 32

        def __init__(self) -> None:
            self.snapshots = []
            self.show_count = 0

        def render_snake_message(self, lines):
            return ("message", lines)

        def render_snake_game(self, snapshot):
            self.snapshots.append(snapshot)
            return ("game", snapshot.phase)

        def show_image(self, frame, preview_name=None) -> None:
            self.show_count += 1

    clock = FakeClock()
    display = FakeDisplay()
    inputs = iter([(1, "right"), (2, "pause"), None, None, (3, "pause"), None])

    monkeypatch.setattr(snake_game.time, "perf_counter", clock.perf_counter)
    monkeypatch.setattr(snake_game.time, "sleep", clock.sleep)
    monkeypatch.setattr(
        snake_game,
        "is_snake_mode_enabled",
        lambda db_path=None: display.show_count < 6,
    )
    monkeypatch.setattr(
        snake_game,
        "consume_snake_input",
        lambda db_path=None: next(inputs, None),
    )
    monkeypatch.setattr(
        snake_game,
        "save_current_display_state",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        snake_game,
        "set_snake_runtime_status",
        lambda *args, **kwargs: None,
    )

    snake_game.run_snake_mode(display)

    paused_heads = [
        snapshot.snake[0]
        for snapshot in display.snapshots
        if snapshot.phase == "paused"
    ]
    resumed_head = next(
        snapshot.snake[0]
        for index, snapshot in enumerate(display.snapshots)
        if index > 0 and snapshot.phase == "playing"
    )

    assert paused_heads
    assert all(head == paused_heads[0] for head in paused_heads)
    assert resumed_head == paused_heads[0]
    assert _snake_frame_sleep_seconds("playing", 10.0, now=9.99) == pytest.approx(0.01)
    assert _snake_frame_sleep_seconds("playing", 10.0, now=10.01) == 0.0
