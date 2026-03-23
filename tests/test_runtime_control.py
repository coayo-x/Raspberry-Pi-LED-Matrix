from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

import custom_text
from custom_text import request_custom_text_override
from runtime_control import (
    CATEGORY_CHANGE_BLOCKED_MESSAGE,
    consume_skip_category_request,
    consume_switch_category_request,
    get_runtime_control_state,
    get_skip_category_state,
    get_switch_category_state,
    request_skip_category,
    request_switch_category,
    set_control_lock,
)


def _install_bad_words(
    monkeypatch,
    base_dir: Path,
    contents: str = "obscene\nblocked phrase\n",
) -> Path:
    path = base_dir / f"badwords-{uuid4().hex}.txt"
    path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(custom_text, "BAD_WORDS_PATH", path)
    return path


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


def test_independent_control_locks_do_not_overlap(
    isolated_db_path,
) -> None:
    set_control_lock("switch_category", True, str(isolated_db_path))

    skip_result = request_skip_category(
        str(isolated_db_path),
        requested_at="2026-03-15T13:24:00",
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

    assert skip_result["accepted"] is True
    assert public_switch["accepted"] is False
    assert public_switch["locked"] is True
    assert admin_switch["accepted"] is True
    assert admin_switch["admin_override"] is True
    assert get_skip_category_state(str(isolated_db_path)) == (1, 0)


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


def test_runtime_control_state_reports_independent_locks(
    isolated_db_path,
) -> None:
    set_control_lock("skip_category", True, str(isolated_db_path))

    public_state = get_runtime_control_state(str(isolated_db_path))
    admin_state = get_runtime_control_state(str(isolated_db_path), is_admin=True)

    assert public_state["skip_category"]["locked"] is True
    assert public_state["skip_category"]["available"] is False
    assert public_state["switch_category"]["locked"] is False
    assert public_state["switch_category"]["available"] is True
    assert admin_state["skip_category"]["admin_override"] is True
    assert admin_state["switch_category"]["admin_override"] is False


def test_skip_and_switch_requests_are_rejected_while_custom_text_is_active(
    monkeypatch,
    isolated_db_path,
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    active_at = datetime(2026, 3, 23, 12, 0, 0)
    request_custom_text_override(
        "Matrix maintenance in progress",
        db_path=str(isolated_db_path),
        now=active_at,
    )

    skip_result = request_skip_category(
        str(isolated_db_path),
        now=datetime(2026, 3, 23, 12, 0, 1),
    )
    switch_result = request_switch_category(
        "weather",
        str(isolated_db_path),
        now=datetime(2026, 3, 23, 12, 0, 1),
    )
    public_state = get_runtime_control_state(
        str(isolated_db_path),
        now=datetime(2026, 3, 23, 12, 0, 1),
    )
    admin_state = get_runtime_control_state(
        str(isolated_db_path),
        is_admin=True,
        now=datetime(2026, 3, 23, 12, 0, 1),
    )

    assert skip_result["accepted"] is False
    assert skip_result["error"] == CATEGORY_CHANGE_BLOCKED_MESSAGE
    assert skip_result["blocked_by_custom_text"] is True
    assert switch_result["accepted"] is False
    assert switch_result["error"] == CATEGORY_CHANGE_BLOCKED_MESSAGE
    assert switch_result["blocked_by_custom_text"] is True
    assert get_skip_category_state(str(isolated_db_path)) == (0, 0)
    assert get_switch_category_state(str(isolated_db_path)) == (0, 0, None)

    assert public_state["skip_category"]["available"] is False
    assert public_state["skip_category"]["status"] == "custom_text_active"
    assert (
        public_state["skip_category"]["blocked_reason"]
        == CATEGORY_CHANGE_BLOCKED_MESSAGE
    )
    assert public_state["switch_category"]["available"] is False
    assert public_state["switch_category"]["blocked_by_custom_text"] is True
    assert admin_state["skip_category"]["available"] is False
    assert admin_state["switch_category"]["available"] is False


def test_pending_category_requests_are_discarded_while_custom_text_is_active(
    monkeypatch,
    isolated_db_path,
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    current = datetime.now().replace(microsecond=0)

    request_skip_category(
        str(isolated_db_path),
        requested_at=current.isoformat(timespec="seconds"),
    )
    request_switch_category(
        "science",
        str(isolated_db_path),
        requested_at=current.isoformat(timespec="seconds"),
    )
    request_custom_text_override(
        "Override active",
        db_path=str(isolated_db_path),
        now=current,
    )

    assert consume_skip_category_request(str(isolated_db_path)) is None
    assert consume_switch_category_request(str(isolated_db_path)) is None
    assert get_skip_category_state(str(isolated_db_path)) == (1, 1)
    assert get_switch_category_state(str(isolated_db_path)) == (1, 1, "science")
