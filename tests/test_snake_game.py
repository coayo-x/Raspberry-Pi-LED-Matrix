import random

import pytest

from snake_game import FRAME_SECONDS, SnakeGame, _snake_frame_sleep_seconds


def test_snake_waits_until_first_control_input() -> None:
    game = SnakeGame(width=192, height=32, rng=random.Random(1))
    original_head = game.snake[0]

    game.step()
    assert game.phase == "waiting"
    assert game.snake[0] == original_head

    game.apply_input("up")
    assert game.phase == "playing"
    assert game.direction == "up"


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
    assert _snake_frame_sleep_seconds("playing", 10.0, now=9.99) == pytest.approx(
        0.01
    )
    assert _snake_frame_sleep_seconds("playing", 10.0, now=10.01) == 0.0
