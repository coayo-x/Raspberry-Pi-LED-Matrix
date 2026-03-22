from datetime import datetime

import pytest

from runtime_control import (
    consume_skip_category_request,
    consume_switch_category_request,
    get_controls_lock_state,
    get_runtime_control_state,
    get_skip_category_state,
    get_switch_category_state,
    set_controls_lock,
    request_skip_category,
    request_switch_category,
    set_control_lock,
)


def test_skip_category_requests_are_counted_and_consumed(isolated_db_path) -> None:
    assert get_skip_category_state(str(isolated_db_path)) == (0, 0)

    first = request_skip_category(
        str(isolated_db_path), requested_at="2026-03-15T13:00:00"
    )
    second = request_skip_category(
        str(isolated_db_path), requested_at="2026-03-15T13:00:11"
    )

    assert first["accepted"] is True
    assert first["request_count"] == 1
    assert second["accepted"] is True
    assert second["request_count"] == 2
    assert get_skip_category_state(str(isolated_db_path)) == (2, 0)

    assert consume_skip_category_request(str(isolated_db_path)) == 1
    assert get_skip_category_state(str(isolated_db_path)) == (2, 1)
    assert consume_skip_category_request(str(isolated_db_path)) == 2
    assert get_skip_category_state(str(isolated_db_path)) == (2, 2)
    assert consume_skip_category_request(str(isolated_db_path)) is None


def test_skip_category_rate_limits_rapid_repeats(isolated_db_path) -> None:
    accepted = request_skip_category(
        str(isolated_db_path), requested_at="2026-03-15T13:05:00"
    )
    rejected = request_skip_category(
        str(isolated_db_path), requested_at="2026-03-15T13:05:04"
    )

    assert accepted["accepted"] is True
    assert rejected["accepted"] is False
    assert rejected["rate_limited"] is True
    assert rejected["retry_after_seconds"] >= 1
    assert get_skip_category_state(str(isolated_db_path)) == (1, 0)


def test_switch_category_requests_validate_and_consume_latest_selection(
    isolated_db_path,
) -> None:
    assert get_switch_category_state(str(isolated_db_path)) == (0, 0, None)

    first = request_switch_category(
        "weather", str(isolated_db_path), requested_at="2026-03-15T13:10:00"
    )
    second = request_switch_category(
        "science", str(isolated_db_path), requested_at="2026-03-15T13:10:11"
    )

    assert first["category"] == "weather"
    assert second["category"] == "science"
    assert second["accepted"] is True
    assert get_switch_category_state(str(isolated_db_path)) == (2, 0, "science")

    assert consume_switch_category_request(str(isolated_db_path)) == (2, "science")
    assert get_switch_category_state(str(isolated_db_path)) == (2, 2, "science")
    assert consume_switch_category_request(str(isolated_db_path)) is None


def test_switch_category_request_rejects_invalid_category(isolated_db_path) -> None:
    with pytest.raises(ValueError):
        request_switch_category("invalid-category", str(isolated_db_path))


def test_control_lock_blocks_public_requests_but_allows_admin_override(
    isolated_db_path,
) -> None:
    control = set_control_lock("skip_category", True, str(isolated_db_path))
    public_attempt = request_skip_category(
        str(isolated_db_path), requested_at="2026-03-15T13:20:00"
    )
    admin_attempt = request_skip_category(
        str(isolated_db_path),
        requested_at="2026-03-15T13:20:11",
        is_admin=True,
    )

    assert control["locked"] is True
    assert public_attempt["accepted"] is False
    assert public_attempt["locked"] is True
    assert admin_attempt["accepted"] is True
    assert admin_attempt["admin_override"] is True
    assert get_skip_category_state(str(isolated_db_path)) == (1, 0)


def test_global_controls_lock_blocks_public_requests_but_allows_admin_override(
    isolated_db_path,
) -> None:
    assert get_controls_lock_state(str(isolated_db_path)) is False

    locked = set_controls_lock(True, str(isolated_db_path))
    public_skip = request_skip_category(
        str(isolated_db_path), requested_at="2026-03-15T13:24:00"
    )
    public_switch = request_switch_category(
        "weather",
        str(isolated_db_path),
        requested_at="2026-03-15T13:24:03",
    )
    admin_switch = request_switch_category(
        "science",
        str(isolated_db_path),
        requested_at="2026-03-15T13:24:10",
        is_admin=True,
    )

    assert locked is True
    assert get_controls_lock_state(str(isolated_db_path)) is True
    assert public_skip["accepted"] is False
    assert public_skip["locked"] is True
    assert public_skip["controls_locked"] is True
    assert public_switch["accepted"] is False
    assert public_switch["locked"] is True
    assert public_switch["controls_locked"] is True
    assert admin_switch["accepted"] is True
    assert admin_switch["admin_override"] is True


def test_runtime_control_state_reports_lock_and_cooldown(isolated_db_path) -> None:
    set_control_lock("switch_category", True, str(isolated_db_path))
    request_skip_category(str(isolated_db_path), requested_at="2026-03-15T13:30:00")

    public_state = get_runtime_control_state(
        str(isolated_db_path),
        now=datetime(2026, 3, 15, 13, 30, 3),
    )
    admin_state = get_runtime_control_state(
        str(isolated_db_path),
        is_admin=True,
        now=datetime(2026, 3, 15, 13, 30, 3),
    )

    assert public_state["skip_category"]["status"] == "cooldown"
    assert public_state["skip_category"]["cooldown_remaining_seconds"] >= 1
    assert public_state["switch_category"]["status"] == "locked"
    assert public_state["switch_category"]["available"] is False

    assert admin_state["switch_category"]["locked"] is True
    assert admin_state["switch_category"]["admin_override"] is True
    assert admin_state["switch_category"]["available"] is True


def test_runtime_control_state_reports_global_lock_for_all_controls(
    isolated_db_path,
) -> None:
    set_controls_lock(True, str(isolated_db_path))

    public_state = get_runtime_control_state(str(isolated_db_path))
    admin_state = get_runtime_control_state(str(isolated_db_path), is_admin=True)

    assert public_state["skip_category"]["controls_locked"] is True
    assert public_state["switch_category"]["controls_locked"] is True
    assert public_state["skip_category"]["available"] is False
    assert public_state["switch_category"]["available"] is False
    assert admin_state["skip_category"]["admin_override"] is True
    assert admin_state["switch_category"]["admin_override"] is True
