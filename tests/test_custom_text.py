from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

import custom_text
from custom_text import (
    find_banned_words,
    get_active_custom_text_override,
    get_custom_text_control_state,
    get_custom_text_interrupt_token,
    get_custom_text_override,
    request_custom_text_override,
    set_custom_text_lock,
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


def test_request_custom_text_override_persists_active_state(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    requested_at = datetime(2026, 3, 23, 12, 0, 0)

    override = request_custom_text_override(
        "Matrix maintenance at 3 PM",
        duration_minutes=1.5,
        style={
            "bold": True,
            "italic": False,
            "underline": True,
            "font_family": "serif",
            "font_size": 18,
            "brightness": 55,
            "text_color": "orange",
            "background_color": "blue",
            "alignment": "right",
        },
        db_path=str(isolated_db_path),
        now=requested_at,
    )

    loaded = get_custom_text_override(
        db_path=str(isolated_db_path),
        now=requested_at + timedelta(seconds=10),
    )

    assert override["accepted"] is True
    assert override["override"]["active"] is True
    assert loaded is not None
    assert loaded["text"] == "Matrix maintenance at 3 PM"
    assert loaded["style"]["bold"] is True
    assert loaded["style"]["underline"] is True
    assert loaded["style"]["font_family"] == "serif"
    assert loaded["style"]["alignment"] == "right"
    assert loaded["style"]["brightness"] == 55
    assert loaded["duration_seconds"] == 90
    assert loaded["duration_minutes"] == 1.5
    assert loaded["remaining_seconds"] == 80
    assert loaded["text_color_hex"] == "#ff9f0a"
    assert loaded["background_color_hex"] == "#0a84ff"
    assert (
        get_custom_text_interrupt_token(
            db_path=str(isolated_db_path),
            now=requested_at + timedelta(seconds=10),
        )
        == loaded["request_id"]
    )


def test_custom_text_override_expires_without_being_active(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    requested_at = datetime(2026, 3, 23, 12, 5, 0)

    request_custom_text_override(
        "Short override",
        duration_minutes=0.1,
        db_path=str(isolated_db_path),
        now=requested_at,
    )

    active_override = get_active_custom_text_override(
        db_path=str(isolated_db_path),
        now=requested_at + timedelta(seconds=7),
    )

    assert active_override is None
    assert (
        get_custom_text_interrupt_token(
            db_path=str(isolated_db_path),
            now=requested_at + timedelta(seconds=7),
        )
        is None
    )


def test_custom_text_lock_blocks_public_requests_but_allows_admin_override(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    set_custom_text_lock(True, str(isolated_db_path))

    public_attempt = request_custom_text_override(
        "Public request",
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 23, 12, 10, 0),
    )
    admin_attempt = request_custom_text_override(
        "Admin request",
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 23, 12, 10, 4),
        is_admin=True,
    )
    admin_state = get_custom_text_control_state(
        str(isolated_db_path),
        is_admin=True,
        now=datetime(2026, 3, 23, 12, 10, 4),
    )

    assert public_attempt["accepted"] is False
    assert public_attempt["locked"] is True
    assert public_attempt["error"] == "Custom text is currently locked by admin."
    assert admin_attempt["accepted"] is True
    assert admin_attempt["admin_override"] is True
    assert admin_state["locked"] is True
    assert admin_state["admin_override"] is True


def test_custom_text_rate_limits_rapid_repeats(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)

    accepted = request_custom_text_override(
        "First message",
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 23, 12, 15, 0),
    )
    rejected = request_custom_text_override(
        "Second message",
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 23, 12, 15, 1),
    )
    accepted_again = request_custom_text_override(
        "Third message",
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 23, 12, 15, 3),
    )

    assert accepted["accepted"] is True
    assert rejected["accepted"] is False
    assert rejected["rate_limited"] is True
    assert rejected["retry_after_seconds"] == 2
    assert accepted_again["accepted"] is True


def test_custom_text_rejects_missing_badwords_file(
    monkeypatch, isolated_db_path
) -> None:
    missing_path = isolated_db_path.parent / f"missing-badwords-{uuid4().hex}.txt"
    monkeypatch.setattr(custom_text, "BAD_WORDS_PATH", missing_path)

    with pytest.raises(
        ValueError,
        match="Custom text moderation is unavailable because badwordslist.txt is missing.",
    ):
        request_custom_text_override(
            "This should fail safely.",
            db_path=str(isolated_db_path),
            now=datetime(2026, 3, 23, 12, 20, 0),
        )


def test_custom_text_rejects_blocked_words_case_insensitively(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)

    with pytest.raises(
        ValueError,
        match="Custom text contains blocked words and was rejected.",
    ):
        request_custom_text_override(
            "This OBSCENE notice is blocked.",
            db_path=str(isolated_db_path),
            now=datetime(2026, 3, 23, 12, 25, 0),
        )

    assert find_banned_words("A blocked PHRASE appears here.", {"blocked phrase"}) == [
        "blocked phrase"
    ]


def test_custom_text_rejects_invalid_brightness(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)

    with pytest.raises(
        ValueError,
        match="'brightness' must be between 10 and 100.",
    ):
        request_custom_text_override(
            "Brightness out of range",
            style={"brightness": 5},
            db_path=str(isolated_db_path),
            now=datetime(2026, 3, 23, 12, 30, 0),
        )
