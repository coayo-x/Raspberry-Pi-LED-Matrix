from collections import deque
import random

import pytest

import snake_game
from snake_game import (
    FRAME_SECONDS,
    FOOD_PER_LEVEL,
    MAX_LEVEL,
    LEVEL_SPEED_STEP_SECONDS,
    MIN_TICK_SECONDS,
    SPEEDUP_FOOD_INTERVAL,
    SPEEDUP_STEP_SECONDS,
    TICK_SECONDS,
    SnakeGame,
    _snake_frame_sleep_seconds,
    score_overlay_text,
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
    occupied = set(game.snake) | set(game.obstacles)
    left, top, right, bottom = game.playfield_bounds
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            candidate = (x, y)
            if (
                game._is_playfield_cell(candidate)
                and candidate not in occupied
                and not game._is_score_overlay_cell(candidate)
            ):
                return candidate
    raise AssertionError("No visible food cell available")


def _start_game(game: SnakeGame, direction: str = "right") -> None:
    game.apply_input(direction)
    assert game.phase == "level_intro"
    game.begin_level_after_intro()
    assert game.phase == "playing"


def _place_safe_food_ahead(game: SnakeGame) -> None:
    left, top, _, _ = game.playfield_bounds
    row = top + 2
    head_x = left + 20
    game.snake = [
        (head_x, row),
        (head_x - 1, row),
        (head_x - 2, row),
        (head_x - 3, row),
        (head_x - 4, row),
        (head_x - 5, row),
    ]
    game.direction = "right"
    game.pending_direction = "right"
    game.food = (head_x + 1, row)


def _reachable_playfield_cells(game: SnakeGame) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    left, top, right, bottom = game.playfield_bounds
    open_cells = {
        (x, y)
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
        if (x, y) not in game.obstacles
    }
    reachable = {game.snake[0]}
    frontier = deque([game.snake[0]])
    while frontier:
        cell_x, cell_y = frontier.popleft()
        for dx, dy in snake_game.DIRECTION_DELTAS.values():
            next_cell = (cell_x + dx, cell_y + dy)
            if next_cell not in open_cells or next_cell in reachable:
                continue
            reachable.add(next_cell)
            frontier.append(next_cell)
    return reachable, open_cells


def test_snake_waits_until_first_control_input() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    original_head = game.snake[0]

    game.step()
    assert game.phase == "waiting"
    assert game.snake[0] == original_head

    game.apply_input("up")
    assert game.phase == "level_intro"
    assert game.pending_direction == "up"

    game.begin_level_after_intro()
    assert game.phase == "playing"
    assert game.direction == "up"


def test_snake_pause_toggles_only_during_gameplay() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))

    game.apply_input("pause")
    assert game.phase == "level_intro"
    assert game.pending_direction == "right"
    game.begin_level_after_intro()

    game.apply_input("pause")
    paused_head = game.snake[0]
    game.step()

    assert game.phase == "paused"
    assert game.snake[0] == paused_head

    game.apply_input("pause")
    assert game.phase == "playing"


def test_snake_rejects_invalid_reverse_direction() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    _start_game(game)
    game.apply_input("left")

    assert game.phase == "playing"
    assert game.pending_direction == "right"


def test_snake_grows_after_eating_food() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    _start_game(game)
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
    _start_game(game)
    head_x, head_y = game.snake[0]
    game.food = (head_x + 1, head_y)
    visible_food = _first_visible_food_cell(game)
    game.rng = SequenceRng([0, 0, visible_food[0], visible_food[1]])

    game.step()

    assert game.score == 1
    assert game.food == visible_food
    assert not game._is_score_overlay_cell(game.food)
    assert game._is_playfield_cell(game.food)


def test_snake_playfield_reserves_hud_and_border_cells() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    left, top, right, bottom = game.playfield_bounds

    assert top > 0
    assert not game._is_playfield_cell((left, top - 1))
    assert not game._is_playfield_cell((left - 1, top))
    assert not game._is_playfield_cell((right + 1, top))
    assert not game._is_playfield_cell((left, bottom + 1))
    assert game._is_playfield_cell((left, top))
    assert game._is_playfield_cell((right, bottom))
    assert score_overlay_text(12, level=3) == "12"


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
    game.score = 0
    game.level = 3
    assert game.tick_seconds() == pytest.approx(
        TICK_SECONDS - (LEVEL_SPEED_STEP_SECONDS * 2)
    )
    game.score = 999
    assert game.tick_seconds() == MIN_TICK_SECONDS


def test_snake_detects_wall_and_self_collision() -> None:
    wall_game = SnakeGame(width=192, height=32, rng=random.Random(1))
    _start_game(wall_game)
    _, top, right, _ = wall_game.playfield_bounds
    wall_game.snake = [(right, top), (right - 1, top)]
    wall_game.direction = "right"
    wall_game.pending_direction = "right"

    wall_game.step()
    assert wall_game.phase == "game_over"

    top_border_game = SnakeGame(width=192, height=32, rng=random.Random(1))
    _start_game(top_border_game, "up")
    left, top, _, _ = top_border_game.playfield_bounds
    top_border_game.snake = [(left + 5, top), (left + 5, top + 1)]
    top_border_game.direction = "up"
    top_border_game.pending_direction = "up"

    top_border_game.step()
    assert top_border_game.phase == "game_over"

    self_game = SnakeGame(width=192, height=32, rng=random.Random(1))
    _start_game(self_game, "left")
    left, top, _, _ = self_game.playfield_bounds
    self_game.snake = [
        (left + 2, top + 3),
        (left + 2, top + 4),
        (left + 1, top + 4),
        (left + 1, top + 3),
        (left + 1, top + 2),
        (left + 2, top + 2),
    ]
    self_game.direction = "left"
    self_game.pending_direction = "left"

    self_game.step()
    assert self_game.phase == "game_over"


def test_snake_game_over_replay_restarts_same_level() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    game.level = 4
    game.score = 35
    game.level_food_count = 5
    game.pending_direction = "up"
    game.phase = "game_over"

    game.apply_input("pause")

    assert game.phase == "level_intro"
    assert game.level == 4
    assert game.pending_direction == "up"
    assert game.level_intro_source_phase == "game_over"

    game.begin_level_after_intro()

    assert game.phase == "playing"
    assert game.level == 4
    assert game.score == 30
    assert game.level_food_count == 0
    assert not set(game.snake) & game.obstacles


def test_snake_advances_level_every_ten_food_items() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    _start_game(game)

    for expected_score in range(1, FOOD_PER_LEVEL + 1):
        _place_safe_food_ahead(game)
        game.step()
        assert game.score == expected_score

    assert game.phase == "level_intro"
    assert game.level == 2
    assert game.level_food_count == 0
    assert game.level_intro_source_phase == "playing"

    game.begin_level_after_intro()

    assert game.phase == "playing"
    assert game.level == 2
    assert game.score == FOOD_PER_LEVEL
    assert game.obstacles


def test_snake_level_layouts_are_playable_and_avoid_reserved_cells() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))

    for level in range(1, MAX_LEVEL + 1):
        game.level = level
        game._reset_body(reset_score=True)
        overlay_width, overlay_height = game._score_overlay_cell_bounds_for_score(
            999,
            level=MAX_LEVEL,
        )
        reachable_cells, open_cells = _reachable_playfield_cells(game)
        head_x, head_y = game.snake[0]
        forward_cell = (head_x + 1, head_y)
        turn_cells = [(head_x, head_y - 1), (head_x, head_y + 1)]

        assert game.phase == "waiting"
        assert game.score == (level - 1) * FOOD_PER_LEVEL
        assert (level == 1) == (not game.obstacles)
        assert not set(game.snake) & game.obstacles
        assert game.food not in game.obstacles
        assert game.food not in game.snake
        assert not game._is_score_overlay_cell(game.food)
        assert game._is_playfield_cell(game.food)
        assert all(game._is_playfield_cell(cell) for cell in game.snake)
        assert all(game._is_playfield_cell(cell) for cell in game.obstacles)
        assert all(
            not (0 <= cell_x < overlay_width and 0 <= cell_y < overlay_height)
            for cell_x, cell_y in game.obstacles
        )
        assert len(game.obstacles) <= game._playfield_cell_count() // 10
        assert len(open_cells) >= int(game._playfield_cell_count() * 0.9)
        assert reachable_cells == open_cells
        assert game._is_playfield_cell(forward_cell)
        assert forward_cell not in game.obstacles
        assert any(
            game._is_playfield_cell(cell) and cell not in game.obstacles
            for cell in turn_cells
        )


def test_snake_obstacle_collision_ends_game() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    game.level = 2
    game._reset_body(reset_score=True)
    obstacle = next(iter(game.obstacles))
    game.snake = [(obstacle[0] - 1, obstacle[1]), (obstacle[0] - 2, obstacle[1])]
    game.direction = "right"
    game.pending_direction = "right"
    game.phase = "playing"

    game.step()

    assert game.phase == "game_over"
    assert game.game_over_animation_pending is True


def test_snake_game_over_pulse_animates_existing_snapshot(monkeypatch) -> None:
    class FakeDisplay:
        def __init__(self) -> None:
            self.pulse_factors: list[float] = []
            self.show_count = 0

        def render_snake_game(self, snapshot):
            self.pulse_factors.append(snapshot.pulse_factor)
            return snapshot

        def show_image(self, frame, preview_name=None) -> None:
            self.show_count += 1

    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    game.phase = "game_over"
    display = FakeDisplay()
    monkeypatch.setattr(
        snake_game,
        "_sleep_with_snake_interrupt",
        lambda duration, should_interrupt, interval=0.02: False,
    )

    interrupted = snake_game._show_snake_game_over_pulse(
        display,
        game,
        should_interrupt=lambda: False,
    )

    assert interrupted is False
    assert display.pulse_factors == [1.0, 0.55, 1.15, 0.55, 1.0]
    assert display.show_count == 5


def test_snake_level_progression_intro_reads_as_advancement(monkeypatch) -> None:
    class FakeDisplay:
        def __init__(self) -> None:
            self.pulse_factors: list[float] = []
            self.events: list[tuple[str, object]] = []

        def render_snake_game(self, snapshot):
            self.pulse_factors.append(snapshot.border_pulse_factor)
            return ("game", snapshot.border_pulse_factor)

        def render_snake_message(self, lines):
            return ("message", tuple(lines))

        def show_image(self, frame, preview_name=None) -> None:
            self.events.append(("show", frame))

        def _transition_to(
            self,
            frame,
            *,
            preview_name=None,
            steps=5,
            delay=0.025,
            should_interrupt=None,
        ):
            self.events.append(("transition", frame))
            return False

    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    game.level = 2
    game.phase = "level_intro"
    game.level_intro_source_phase = "playing"
    display = FakeDisplay()
    monkeypatch.setattr(
        snake_game,
        "_sleep_with_snake_interrupt",
        lambda duration, should_interrupt, interval=0.02: False,
    )

    interrupted = snake_game._show_snake_level_intro_sequence(
        display,
        game,
        should_interrupt=lambda: False,
    )

    assert interrupted is False
    assert display.pulse_factors == list(snake_game.LEVEL_UP_PULSE_FACTORS)
    assert display.events == [
        *[
            ("show", ("game", factor))
            for factor in snake_game.LEVEL_UP_PULSE_FACTORS
        ],
        ("transition", ("message", ("LEVEL UP",))),
        ("transition", ("message", ("LEVEL 2",))),
    ]


def test_snake_frame_sleep_wakes_for_next_movement_tick() -> None:
    assert _snake_frame_sleep_seconds("waiting", 10.0, now=9.99) == FRAME_SECONDS
    assert _snake_frame_sleep_seconds("game_over", 10.0, now=9.99) == FRAME_SECONDS
    assert _snake_frame_sleep_seconds("playing", 10.0, now=9.0) == FRAME_SECONDS
    assert _snake_frame_sleep_seconds("playing", 10.0, now=9.99) == pytest.approx(0.01)
    assert _snake_frame_sleep_seconds("playing", 10.0, now=10.01) == 0.0


def test_run_snake_mode_shows_level_intro_before_gameplay(monkeypatch) -> None:
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
            self.events: list[tuple[str, object]] = []
            self.playing_seen = False

        def render_snake_message(self, lines):
            return ("message", tuple(lines))

        def render_snake_game(self, snapshot):
            return ("game", snapshot.phase, snapshot.level)

        def _fade_sequence(
            self,
            frame,
            *,
            steps=6,
            fade_in=True,
            delay=0.05,
            should_interrupt=None,
            end_time=None,
        ):
            self.events.append(("fade_in" if fade_in else "fade_out", frame))
            return False

        def show_image(self, frame, preview_name=None) -> None:
            self.events.append(("show", frame))
            if frame == ("game", "playing", 1):
                self.playing_seen = True

    clock = FakeClock()
    display = FakeDisplay()
    inputs = iter([(1, "right"), None])

    monkeypatch.setattr(snake_game.time, "perf_counter", clock.perf_counter)
    monkeypatch.setattr(snake_game.time, "sleep", clock.sleep)
    monkeypatch.setattr(
        snake_game,
        "is_snake_mode_enabled",
        lambda db_path=None: not display.playing_seen,
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

    assert display.events[:4] == [
        ("fade_out", ("message", ("Press any button to start",))),
        ("fade_in", ("message", ("LEVEL 1",))),
        ("fade_out", ("message", ("LEVEL 1",))),
        ("show", ("game", "playing", 1)),
    ]


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
