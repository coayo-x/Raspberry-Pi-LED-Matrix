from datetime import datetime as real_datetime

import pytest

import main


class StopRuntimeLoop(Exception):
    pass


class FakeDateTime:
    @classmethod
    def now(cls):
        return real_datetime(2026, 3, 15, 12, 0, 0)


class FakeDisplay:
    def __init__(self, switch_state: dict) -> None:
        self.switch_state = switch_state
        self.categories: list[str] = []

    def display_payload(
        self,
        payload: dict,
        duration_seconds=None,
        should_interrupt=None,
    ) -> None:
        self.categories.append(payload["category"])

        if len(self.categories) == 1:
            self.switch_state["request_count"] = 1
            self.switch_state["category"] = "weather"
            assert should_interrupt is not None
            assert should_interrupt() is True
            return

        raise StopRuntimeLoop


def test_run_forever_switches_category_immediately_within_active_slot(
    monkeypatch,
) -> None:
    switch_state = {
        "request_count": 0,
        "handled_count": 0,
        "category": None,
    }

    def fake_get_switch_category_state(_db_path=None):
        return (
            switch_state["request_count"],
            switch_state["handled_count"],
            switch_state["category"],
        )

    def fake_consume_switch_category_request(_db_path=None):
        if switch_state["handled_count"] >= switch_state["request_count"]:
            return None

        switch_state["handled_count"] = switch_state["request_count"]
        return switch_state["handled_count"], switch_state["category"]

    monkeypatch.setattr(main, "datetime", FakeDateTime)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "print_payload", lambda payload: None)
    monkeypatch.setattr(main, "get_current_slot_key", lambda now=None: "2026-03-15:144")
    monkeypatch.setattr(main, "seconds_until_next_slot", lambda now=None: 60)
    monkeypatch.setattr(main, "get_skip_category_state", lambda: (0, 0))
    monkeypatch.setattr(main, "consume_skip_category_request", lambda: None)
    monkeypatch.setattr(
        main, "get_switch_category_state", fake_get_switch_category_state
    )
    monkeypatch.setattr(
        main,
        "consume_switch_category_request",
        fake_consume_switch_category_request,
    )
    monkeypatch.setattr(
        main,
        "build_runtime_payload",
        lambda now, category_override=None: {
            "slot_key": "2026-03-15:144",
            "time": "2026-03-15 12:00:00",
            "category": category_override or "pokemon",
            "data": {},
        },
    )

    display = FakeDisplay(switch_state)

    with pytest.raises(StopRuntimeLoop):
        main.run_forever(display, boot_delay=0)

    assert display.categories == ["pokemon", "weather"]


def test_run_once_uses_short_duration_for_single_render(monkeypatch) -> None:
    captured: dict = {}
    payload = {
        "slot_key": "2026-03-15:144",
        "time": "2026-03-15 12:00:00",
        "category": "pokemon",
        "data": {},
    }

    class FakeOneShotDisplay:
        def display_payload(
            self,
            active_payload: dict,
            duration_seconds=None,
            should_interrupt=None,
        ) -> None:
            captured["payload"] = active_payload
            captured["duration_seconds"] = duration_seconds
            captured["should_interrupt"] = should_interrupt

    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "build_runtime_payload", lambda now=None: payload)
    monkeypatch.setattr(main, "print_payload", lambda active_payload: None)

    result = main.run_once(
        FakeOneShotDisplay(), now=real_datetime(2026, 3, 15, 12, 0, 0)
    )

    assert result == payload
    assert captured["payload"] == payload
    assert captured["duration_seconds"] == 1
    assert captured["should_interrupt"] is None


def test_run_once_renders_snake_waiting_screen_when_mode_is_active(
    monkeypatch,
) -> None:
    payload = {
        "slot_key": "2026-03-26:144",
        "time": "2026-03-26 12:00:00",
        "category": "snake_game",
        "data": {
            "state": "waiting",
            "score": 0,
            "summary": "Press any button to start",
        },
    }
    captured: dict = {}

    class FakeOneShotDisplay:
        pass

    def fake_render_snake_waiting_once(display):
        captured["display"] = display
        return payload

    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "is_snake_mode_enabled", lambda: True)
    monkeypatch.setattr(
        main,
        "render_snake_waiting_once",
        fake_render_snake_waiting_once,
    )
    monkeypatch.setattr(main, "print_payload", lambda active_payload: None)
    monkeypatch.setattr(
        main,
        "build_runtime_payload",
        lambda now=None: pytest.fail("normal payload should not render"),
    )

    display = FakeOneShotDisplay()
    result = main.run_once(display, now=real_datetime(2026, 3, 26, 12, 0, 0))

    assert result == payload
    assert captured["display"] is display


def test_build_content_for_now_prioritizes_active_custom_text_override(
    monkeypatch,
) -> None:
    now = real_datetime(2026, 3, 23, 12, 0, 0)
    override = {
        "request_id": "override-1",
        "text": "Temporary maintenance notice",
        "style": {
            "bold": True,
            "italic": False,
            "underline": False,
            "font_family": "sans",
            "font_size": 16,
            "text_color": "white",
            "background_color": "black",
            "alignment": "center",
        },
        "duration_seconds": 300,
        "duration_minutes": 5,
        "started_at": "2026-03-23T12:00:00",
        "expires_at": "2026-03-23T12:05:00",
        "remaining_seconds": 300,
        "text_color_hex": "#f5f7fa",
        "background_color_hex": "#000000",
    }

    monkeypatch.setattr(
        main, "get_active_custom_text_override", lambda now=None: override
    )
    monkeypatch.setattr(main, "get_current_slot_key", lambda now=None: "2026-03-23:144")
    monkeypatch.setattr(
        main,
        "get_current_category",
        lambda now=None: pytest.fail("rotation category should not be requested"),
    )

    payload = main.build_content_for_now(now=now)

    assert payload["category"] == "custom_text"
    assert payload["data"]["text"] == "Temporary maintenance notice"
    assert payload["data"]["duration_minutes"] == 5


def test_run_forever_custom_text_discards_category_requests_without_interrupting(
    monkeypatch,
) -> None:
    skip_state = {
        "request_count": 1,
        "handled_count": 0,
    }
    switch_state = {
        "request_count": 1,
        "handled_count": 0,
        "category": "weather",
    }
    override = {
        "request_id": "override-1",
        "text": "Temporary maintenance notice",
        "style": {
            "bold": False,
            "italic": False,
            "underline": False,
            "font_family": "sans",
            "font_size": 16,
            "text_color": "white",
            "background_color": "black",
            "alignment": "center",
        },
        "duration_seconds": 300,
        "duration_minutes": 5,
        "started_at": "2026-03-23T12:00:00",
        "expires_at": "2026-03-23T12:05:00",
        "remaining_seconds": 300,
        "text_color_hex": "#f5f7fa",
        "background_color_hex": "#000000",
    }

    def fake_get_skip_category_state():
        return skip_state["request_count"], skip_state["handled_count"]

    def fake_get_switch_category_state():
        return (
            switch_state["request_count"],
            switch_state["handled_count"],
            switch_state["category"],
        )

    def fake_consume_skip_category_request():
        if skip_state["handled_count"] >= skip_state["request_count"]:
            return None
        skip_state["handled_count"] = skip_state["request_count"]
        return None

    def fake_consume_switch_category_request():
        if switch_state["handled_count"] >= switch_state["request_count"]:
            return None
        switch_state["handled_count"] = switch_state["request_count"]
        return None

    class FakeCustomTextDisplay:
        def display_payload(
            self,
            payload: dict,
            duration_seconds=None,
            should_interrupt=None,
        ) -> None:
            assert payload["category"] == "custom_text"
            assert duration_seconds == 30
            assert should_interrupt is not None
            assert should_interrupt() is False
            raise StopRuntimeLoop

    monkeypatch.setattr(main, "datetime", FakeDateTime)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "print_payload", lambda payload: None)
    monkeypatch.setattr(main, "get_current_slot_key", lambda now=None: "2026-03-23:144")
    monkeypatch.setattr(
        main, "get_active_custom_text_override", lambda now=None: override
    )
    monkeypatch.setattr(
        main, "get_custom_text_interrupt_token", lambda now=None: "override-1"
    )
    monkeypatch.setattr(
        main, "get_custom_text_remaining_seconds", lambda override, now=None: 30
    )
    monkeypatch.setattr(main, "get_skip_category_state", fake_get_skip_category_state)
    monkeypatch.setattr(
        main, "get_switch_category_state", fake_get_switch_category_state
    )
    monkeypatch.setattr(
        main, "consume_skip_category_request", fake_consume_skip_category_request
    )
    monkeypatch.setattr(
        main,
        "consume_switch_category_request",
        fake_consume_switch_category_request,
    )
    monkeypatch.setattr(
        main,
        "build_runtime_payload",
        lambda now, category_override=None, custom_override=None: {
            "slot_key": "2026-03-23:144",
            "time": "2026-03-23 12:00:00",
            "category": "custom_text",
            "data": {"text": "Temporary maintenance notice"},
        },
    )

    with pytest.raises(StopRuntimeLoop):
        main.run_forever(FakeCustomTextDisplay(), boot_delay=0)

    assert skip_state["handled_count"] == skip_state["request_count"]
    assert switch_state["handled_count"] == switch_state["request_count"]


def test_run_forever_enters_snake_mode_before_normal_rotation(
    monkeypatch,
) -> None:
    calls: dict[str, int] = {"snake": 0}

    def fake_run_snake_mode(display):
        calls["snake"] += 1
        raise StopRuntimeLoop

    monkeypatch.setattr(main, "datetime", FakeDateTime)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "is_snake_mode_enabled", lambda: True)
    monkeypatch.setattr(main, "run_snake_mode", fake_run_snake_mode)
    monkeypatch.setattr(
        main,
        "build_runtime_payload",
        lambda *args, **kwargs: pytest.fail("normal rotation should stay paused"),
    )

    with pytest.raises(StopRuntimeLoop):
        main.run_forever(object(), boot_delay=0)

    assert calls["snake"] == 1


def test_run_forever_resumes_rotation_after_snake_mode_stops(
    monkeypatch,
) -> None:
    snake_state = {"enabled": True}
    rendered_categories: list[str] = []

    class FakeRotationDisplay:
        def display_payload(
            self,
            payload: dict,
            duration_seconds=None,
            should_interrupt=None,
        ) -> None:
            rendered_categories.append(payload["category"])
            raise StopRuntimeLoop

    def fake_run_snake_mode(_display):
        rendered_categories.append("snake_game")
        snake_state["enabled"] = False

    monkeypatch.setattr(main, "datetime", FakeDateTime)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "print_payload", lambda payload: None)
    monkeypatch.setattr(main, "is_snake_mode_enabled", lambda: snake_state["enabled"])
    monkeypatch.setattr(main, "run_snake_mode", fake_run_snake_mode)
    monkeypatch.setattr(main, "get_current_slot_key", lambda now=None: "2026-03-15:144")
    monkeypatch.setattr(main, "seconds_until_next_slot", lambda now=None: 60)
    monkeypatch.setattr(main, "is_custom_text_force_enabled", lambda: False)
    monkeypatch.setattr(main, "get_custom_text_override", lambda now=None: None)
    monkeypatch.setattr(main, "get_active_custom_text_override", lambda now=None: None)
    monkeypatch.setattr(main, "get_skip_category_state", lambda: (0, 0))
    monkeypatch.setattr(main, "get_switch_category_state", lambda: (0, 0, None))
    monkeypatch.setattr(main, "consume_skip_category_request", lambda: None)
    monkeypatch.setattr(main, "consume_switch_category_request", lambda: None)
    monkeypatch.setattr(main, "get_current_category", lambda now=None: "pokemon")
    monkeypatch.setattr(
        main,
        "build_runtime_payload",
        lambda now, category_override=None, custom_override=None: {
            "slot_key": "2026-03-15:144",
            "time": "2026-03-15 12:00:00",
            "category": category_override or "pokemon",
            "data": {},
        },
    )

    with pytest.raises(StopRuntimeLoop):
        main.run_forever(FakeRotationDisplay(), boot_delay=0)

    assert rendered_categories == ["snake_game", "pokemon"]


def test_interrupt_checker_fires_when_snake_mode_changes(
    monkeypatch,
) -> None:
    snake_state = {"enabled": False}

    monkeypatch.setattr(main, "get_skip_category_state", lambda: (0, 0))
    monkeypatch.setattr(main, "get_switch_category_state", lambda: (0, 0, None))
    monkeypatch.setattr(main, "is_custom_text_force_enabled", lambda: False)
    monkeypatch.setattr(
        main,
        "_get_custom_text_interrupt_token_value",
        lambda include_inactive=False: None,
    )
    monkeypatch.setattr(
        main,
        "is_snake_mode_enabled",
        lambda: snake_state["enabled"],
    )

    checker = main._build_interrupt_checker(
        skip_baseline=0,
        switch_baseline=0,
        force_baseline=False,
        custom_text_baseline=None,
        snake_baseline=False,
    )

    assert checker() is False
    snake_state["enabled"] = True
    assert checker() is True
