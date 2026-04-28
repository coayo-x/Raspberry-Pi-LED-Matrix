from datetime import datetime

from snake_control import (
    consume_snake_input,
    get_snake_control_state,
    is_snake_mode_enabled,
    request_snake_input,
    set_snake_mode_enabled,
    set_snake_runtime_status,
)


def test_snake_mode_requires_admin_for_mode_changes_and_input(isolated_db_path) -> None:
    public_enable = set_snake_mode_enabled(True, str(isolated_db_path))
    admin_enable = set_snake_mode_enabled(
        True,
        str(isolated_db_path),
        is_admin=True,
        now=datetime(2026, 3, 26, 12, 0, 0),
    )
    public_input = request_snake_input("up", str(isolated_db_path))

    assert public_enable["accepted"] is False
    assert public_enable["enabled"] is False
    assert admin_enable["accepted"] is True
    assert admin_enable["enabled"] is True
    assert admin_enable["status"] == "waiting"
    assert public_input["accepted"] is False
    assert consume_snake_input(str(isolated_db_path)) is None


def test_snake_input_is_counted_consumed_and_cleared_on_stop(isolated_db_path) -> None:
    set_snake_mode_enabled(True, str(isolated_db_path), is_admin=True)
    first = request_snake_input(
        "ArrowUp",
        str(isolated_db_path),
        is_admin=True,
        requested_at="2026-03-26T12:01:00",
    )

    assert first["accepted"] is True
    assert first["direction"] == "up"
    assert first["request_count"] == 1
    assert consume_snake_input(str(isolated_db_path)) == (1, "up")
    assert consume_snake_input(str(isolated_db_path)) is None

    request_snake_input("left", str(isolated_db_path), is_admin=True)
    stopped = set_snake_mode_enabled(False, str(isolated_db_path), is_admin=True)

    assert stopped["enabled"] is False
    assert is_snake_mode_enabled(str(isolated_db_path)) is False
    assert consume_snake_input(str(isolated_db_path)) is None
    state = get_snake_control_state(str(isolated_db_path), is_admin=True)
    assert state["pending_request_count"] == 0


def test_snake_input_normalizes_space_to_pause(isolated_db_path) -> None:
    set_snake_mode_enabled(True, str(isolated_db_path), is_admin=True)

    result = request_snake_input(" ", str(isolated_db_path), is_admin=True)

    assert result["accepted"] is True
    assert result["direction"] == "pause"
    assert consume_snake_input(str(isolated_db_path)) == (1, "pause")


def test_snake_runtime_status_tracks_score_only_while_enabled(isolated_db_path) -> None:
    set_snake_mode_enabled(True, str(isolated_db_path), is_admin=True)

    playing = set_snake_runtime_status(
        "playing",
        score=3,
        level=2,
        db_path=str(isolated_db_path),
    )
    set_snake_mode_enabled(False, str(isolated_db_path), is_admin=True)
    idle = set_snake_runtime_status(
        "playing",
        score=9,
        db_path=str(isolated_db_path),
    )

    assert playing["status"] == "playing"
    assert playing["score"] == 3
    assert playing["level"] == 2
    assert idle["status"] == "idle"
    assert idle["score"] == 0
    assert idle["level"] == 1
