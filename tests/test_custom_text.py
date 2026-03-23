from datetime import datetime, timedelta
from pathlib import Path

import pytest

from custom_text import (
    BAD_WORDS_PATH,
    find_banned_words,
    get_active_custom_text_override,
    get_custom_text_interrupt_token,
    get_custom_text_override,
    request_custom_text_override,
)


def test_request_custom_text_override_persists_active_state(isolated_db_path) -> None:
    requested_at = datetime(2026, 3, 23, 12, 0, 0)
    override = request_custom_text_override(
        "Matrix maintenance at 3 PM",
        duration_seconds=90,
        style={
            "bold": True,
            "italic": False,
            "underline": True,
            "font_family": "serif",
            "font_size": 18,
            "text_color": "#abcdef",
            "background_color": "#123456",
            "alignment": "right",
        },
        db_path=str(isolated_db_path),
        now=requested_at,
    )

    loaded = get_custom_text_override(
        db_path=str(isolated_db_path),
        now=requested_at + timedelta(seconds=10),
    )

    assert override["active"] is True
    assert loaded is not None
    assert loaded["text"] == "Matrix maintenance at 3 PM"
    assert loaded["style"]["bold"] is True
    assert loaded["style"]["underline"] is True
    assert loaded["style"]["font_family"] == "serif"
    assert loaded["style"]["alignment"] == "right"
    assert loaded["remaining_seconds"] == 80
    assert (
        get_custom_text_interrupt_token(
            db_path=str(isolated_db_path),
            now=requested_at + timedelta(seconds=10),
        )
        == loaded["request_id"]
    )


def test_custom_text_override_expires_without_being_active(isolated_db_path) -> None:
    requested_at = datetime(2026, 3, 23, 12, 5, 0)
    request_custom_text_override(
        "Short override",
        duration_seconds=5,
        db_path=str(isolated_db_path),
        now=requested_at,
    )

    active_override = get_active_custom_text_override(
        db_path=str(isolated_db_path),
        now=requested_at + timedelta(seconds=6),
    )

    assert active_override is None
    assert (
        get_custom_text_interrupt_token(
            db_path=str(isolated_db_path),
            now=requested_at + timedelta(seconds=6),
        )
        is None
    )


def test_custom_text_rejects_banned_words(monkeypatch, isolated_db_path) -> None:
    monkeypatch.setattr(
        "custom_text.BAD_WORDS_PATH",
        Path(__file__).resolve().parents[1] / "badwordslist.txt",
    )

    with pytest.raises(
        ValueError, match="Custom text contains banned words and was rejected."
    ):
        request_custom_text_override(
            "This message is obscene.",
            db_path=str(isolated_db_path),
            now=datetime(2026, 3, 23, 12, 10, 0),
        )


def test_find_banned_words_uses_case_insensitive_token_matching(monkeypatch) -> None:
    monkeypatch.setattr("custom_text.BAD_WORDS_PATH", BAD_WORDS_PATH)

    found = find_banned_words("  ObScEnE signage ahead!  ")

    assert found == ["obscene"]
