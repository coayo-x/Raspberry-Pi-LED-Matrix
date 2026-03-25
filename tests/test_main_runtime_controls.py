from datetime import datetime as real_datetime
from types import SimpleNamespace

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


def test_build_content_for_now_returns_qr_payload_shape(monkeypatch) -> None:
    now = real_datetime(2026, 3, 23, 12, 20, 0)

    monkeypatch.setattr(main, "get_active_custom_text_override", lambda now=None: None)
    monkeypatch.setattr(main, "get_current_slot_key", lambda now=None: "2026-03-23:148")

    payload = main.build_content_for_now(now=now, category_override="qr")

    assert payload == {
        "slot_key": "2026-03-23:148",
        "time": "2026-03-23 12:20:00",
        "category": "qr",
        "data": {
            "image_path": "qr_cache.png",
        },
    }


def test_main_generates_qr_cache_once_before_single_run(monkeypatch) -> None:
    calls: list = []
    fake_display = object()

    monkeypatch.setattr(
        main, "sys", SimpleNamespace(argv=["main.py", "--simulate", "--once"])
    )
    monkeypatch.setattr(
        main,
        "DisplayManager",
        lambda **kwargs: calls.append(("display", kwargs)) or fake_display,
    )
    monkeypatch.setattr(main, "_build_qr_url", lambda: "http://localhost:8080")
    monkeypatch.setattr(
        main,
        "generate_qr_if_missing",
        lambda url: calls.append(("qr", url)) or "qr_cache.png",
    )
    monkeypatch.setattr(
        main,
        "run_once",
        lambda display: calls.append(("run_once", display)),
    )
    monkeypatch.setattr(
        main,
        "run_forever",
        lambda display: pytest.fail("run_forever should not be called in --once mode"),
    )

    main.main()

    assert calls[0] == ("display", {"use_matrix": False, "save_previews": False})
    assert calls[1] == ("qr", "http://localhost:8080")
    assert calls[2] == ("run_once", fake_display)


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
