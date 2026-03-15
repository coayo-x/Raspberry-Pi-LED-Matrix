import pytest

from runtime_control import (
    consume_skip_category_request,
    consume_switch_category_request,
    get_skip_category_state,
    get_switch_category_state,
    request_skip_category,
    request_switch_category,
from runtime_control import (
    consume_skip_category_request,
    get_skip_category_state,
    request_skip_category,
)


def test_skip_category_requests_are_counted_and_consumed(isolated_db_path) -> None:
    assert get_skip_category_state(str(isolated_db_path)) == (0, 0)

    first = request_skip_category(
        str(isolated_db_path), requested_at="2026-03-15T13:00:00"
    )
    second = request_skip_category(
        str(isolated_db_path), requested_at="2026-03-15T13:00:01"
    )

    assert first["request_count"] == 1
    assert second["request_count"] == 2
    assert get_skip_category_state(str(isolated_db_path)) == (2, 0)

    assert consume_skip_category_request(str(isolated_db_path)) == 1
    assert get_skip_category_state(str(isolated_db_path)) == (2, 1)
    assert consume_skip_category_request(str(isolated_db_path)) == 2
    assert get_skip_category_state(str(isolated_db_path)) == (2, 2)
    assert consume_skip_category_request(str(isolated_db_path)) is None


def test_switch_category_requests_validate_and_consume_latest_selection(
    isolated_db_path,
) -> None:
    assert get_switch_category_state(str(isolated_db_path)) == (0, 0, None)

    first = request_switch_category(
        "weather", str(isolated_db_path), requested_at="2026-03-15T13:10:00"
    )
    second = request_switch_category(
        "science", str(isolated_db_path), requested_at="2026-03-15T13:10:01"
    )

    assert first["category"] == "weather"
    assert second["category"] == "science"
    assert get_switch_category_state(str(isolated_db_path)) == (2, 0, "science")

    assert consume_switch_category_request(str(isolated_db_path)) == (2, "science")
    assert get_switch_category_state(str(isolated_db_path)) == (2, 2, "science")
    assert consume_switch_category_request(str(isolated_db_path)) is None


def test_switch_category_request_rejects_invalid_category(isolated_db_path) -> None:
    with pytest.raises(ValueError):
        request_switch_category("invalid-category", str(isolated_db_path))
