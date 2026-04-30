import base64
import io
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

import custom_text
from custom_text import (
    _validate_rendered_frame,
    find_banned_words,
    get_active_custom_text_override,
    get_custom_text_control_state,
    get_custom_text_interrupt_token,
    get_custom_text_override,
    normalize_custom_text_style,
    request_custom_text_override,
    set_custom_text_lock,
    stop_custom_text_override,
)
from snake_control import SNAKE_ACTIVE_BLOCKED_MESSAGE, set_snake_mode_enabled


def _make_png_b64(width: int = 192, height: int = 32, color: tuple = (255, 0, 0)) -> str:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _make_png_data_url(width: int = 192, height: int = 32) -> str:
    return "data:image/png;base64," + _make_png_b64(width, height)


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
            "text_brightness": 55,
            "background_brightness": 35,
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
    assert loaded["style"]["text_brightness"] == 55
    assert loaded["style"]["background_brightness"] == 35
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


def test_custom_text_request_is_blocked_while_snake_mode_is_active(
    monkeypatch,
    isolated_db_path,
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    set_snake_mode_enabled(True, str(isolated_db_path), is_admin=True)

    result = request_custom_text_override(
        "Admin maintenance notice",
        db_path=str(isolated_db_path),
        is_admin=True,
        now=datetime(2026, 3, 26, 12, 0, 0),
    )
    state = get_custom_text_control_state(
        str(isolated_db_path),
        is_admin=True,
        now=datetime(2026, 3, 26, 12, 0, 0),
    )

    assert result["accepted"] is False
    assert result["blocked_by_snake"] is True
    assert result["error"] == SNAKE_ACTIVE_BLOCKED_MESSAGE
    assert state["available"] is False
    assert state["status"] == "snake_game_active"
    assert state["blocked_reason"] == SNAKE_ACTIVE_BLOCKED_MESSAGE


def test_custom_text_rate_limits_rapid_repeats(monkeypatch, isolated_db_path) -> None:
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


def test_stop_custom_text_override_clears_active_override(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    started_at = datetime(2026, 3, 23, 12, 18, 0)
    request_custom_text_override(
        "Stop me now",
        db_path=str(isolated_db_path),
        now=started_at,
    )

    stopped = stop_custom_text_override(
        db_path=str(isolated_db_path),
        is_admin=True,
        now=started_at + timedelta(seconds=2),
    )

    assert stopped["stopped"] is True
    assert stopped["message"] == "Custom text stopped."
    assert stopped["active_override"] is False
    assert (
        get_active_custom_text_override(
            db_path=str(isolated_db_path),
            now=started_at + timedelta(seconds=2),
        )
        is None
    )
    assert (
        get_custom_text_interrupt_token(
            db_path=str(isolated_db_path),
            now=started_at + timedelta(seconds=2),
        )
        is None
    )


def test_stop_custom_text_override_is_safe_when_inactive(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)

    stopped = stop_custom_text_override(
        db_path=str(isolated_db_path),
        is_admin=True,
        now=datetime(2026, 3, 23, 12, 19, 0),
    )

    assert stopped["stopped"] is False
    assert stopped["message"] == "No active custom text."
    assert stopped["active_override"] is False


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


def test_custom_text_rejects_invalid_brightness(monkeypatch, isolated_db_path) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)

    with pytest.raises(
        ValueError,
        match="'text_brightness' must be between 10 and 100.",
    ):
        request_custom_text_override(
            "Brightness out of range",
            style={"text_brightness": 5},
            db_path=str(isolated_db_path),
            now=datetime(2026, 3, 23, 12, 30, 0),
        )


def test_custom_text_legacy_brightness_maps_to_text_and_background() -> None:
    style = normalize_custom_text_style({"brightness": 55})

    assert style["text_brightness"] == 55
    assert style["background_brightness"] == 55


def test_validate_rendered_frame_returns_none_for_empty() -> None:
    assert _validate_rendered_frame(None) is None
    assert _validate_rendered_frame("") is None


def test_validate_rendered_frame_accepts_valid_png_b64() -> None:
    b64 = _make_png_b64(192, 32)
    result = _validate_rendered_frame(b64)
    assert result is not None
    raw = base64.b64decode(result)
    img = Image.open(io.BytesIO(raw))
    assert img.size == (192, 32)
    assert img.format == "PNG"


def test_validate_rendered_frame_accepts_data_url() -> None:
    data_url = _make_png_data_url(192, 32)
    result = _validate_rendered_frame(data_url)
    assert result is not None
    raw = base64.b64decode(result)
    img = Image.open(io.BytesIO(raw))
    assert img.size == (192, 32)


def test_validate_rendered_frame_resizes_to_matrix_dimensions() -> None:
    b64 = _make_png_b64(96, 16)
    result = _validate_rendered_frame(b64)
    assert result is not None
    raw = base64.b64decode(result)
    img = Image.open(io.BytesIO(raw))
    assert img.size == (192, 32)


def test_validate_rendered_frame_rejects_invalid_base64() -> None:
    with pytest.raises(ValueError, match="valid base64"):
        _validate_rendered_frame("not-valid-base64!!!")


def test_validate_rendered_frame_rejects_non_png_data_url() -> None:
    with pytest.raises(ValueError, match="PNG"):
        _validate_rendered_frame("data:image/jpeg;base64,/9j/abc")


def test_validate_rendered_frame_rejects_oversized_payload() -> None:
    import custom_text as ct

    original = ct.RENDERED_FRAME_MAX_BYTES
    ct.RENDERED_FRAME_MAX_BYTES = 10
    try:
        with pytest.raises(ValueError, match="too large"):
            _validate_rendered_frame(_make_png_b64(192, 32))
    finally:
        ct.RENDERED_FRAME_MAX_BYTES = original


def test_request_custom_text_override_with_rendered_frame_stores_it(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    b64 = _make_png_b64(192, 32)
    now = datetime(2026, 3, 23, 12, 0, 0)

    result = request_custom_text_override(
        "Hello LED",
        duration_minutes=1.0,
        rendered_frame_png=b64,
        db_path=str(isolated_db_path),
        now=now,
    )

    assert result["accepted"] is True
    override = result["override"]
    assert "rendered_frame" in override
    raw = base64.b64decode(override["rendered_frame"])
    img = Image.open(io.BytesIO(raw))
    assert img.size == (192, 32)


def test_request_custom_text_override_with_rendered_frame_data_url(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    data_url = _make_png_data_url(192, 32)
    now = datetime(2026, 3, 23, 12, 0, 0)

    result = request_custom_text_override(
        "Hello LED data url",
        duration_minutes=1.0,
        rendered_frame_png=data_url,
        db_path=str(isolated_db_path),
        now=now,
    )

    assert result["accepted"] is True
    assert "rendered_frame" in result["override"]


def test_request_custom_text_override_without_rendered_frame_unchanged(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    now = datetime(2026, 3, 23, 12, 0, 0)

    result = request_custom_text_override(
        "No image",
        duration_minutes=1.0,
        db_path=str(isolated_db_path),
        now=now,
    )

    assert result["accepted"] is True
    assert "rendered_frame" not in (result.get("override") or {})


def test_request_custom_text_override_invalid_frame_raises(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)

    with pytest.raises(ValueError, match="valid base64"):
        request_custom_text_override(
            "Bad frame",
            rendered_frame_png="not-valid-base64!!!",
            db_path=str(isolated_db_path),
        )


def test_get_active_custom_text_override_includes_rendered_frame(
    monkeypatch, isolated_db_path
) -> None:
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    b64 = _make_png_b64(192, 32)
    now = datetime(2026, 3, 23, 12, 0, 0)

    request_custom_text_override(
        "Persisted frame",
        duration_minutes=5.0,
        rendered_frame_png=b64,
        db_path=str(isolated_db_path),
        now=now,
    )

    loaded = get_active_custom_text_override(
        db_path=str(isolated_db_path),
        now=now + timedelta(seconds=30),
    )
    assert loaded is not None
    assert "rendered_frame" in loaded
    raw = base64.b64decode(loaded["rendered_frame"])
    img = Image.open(io.BytesIO(raw))
    assert img.size == (192, 32)
