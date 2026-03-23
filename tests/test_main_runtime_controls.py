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


def test_run_forever_returns_to_rotation_after_custom_text_expires(
    monkeypatch,
) -> None:
    override_state = {
        "value": {
            "request_id": "override-1",
            "text": "Temporary notice",
            "style": {},
            "duration_seconds": 30,
            "started_at": "2026-03-15T12:00:00",
            "expires_at": "2026-03-15T12:00:30",
            "remaining_seconds": 30,
        }
    }

    class FakeDisplay:
        def __init__(self) -> None:
            self.categories: list[str] = []

        def display_payload(
            self,
            payload: dict,
            duration_seconds=None,
            should_interrupt=None,
        ) -> None:
            self.categories.append(payload["category"])
            if len(self.categories) == 1:
                override_state["value"] = None
                return
            raise StopRuntimeLoop

    monkeypatch.setattr(main, "datetime", FakeDateTime)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "print_payload", lambda payload: None)
    monkeypatch.setattr(main, "get_current_slot_key", lambda now=None: "2026-03-15:144")
    monkeypatch.setattr(main, "seconds_until_next_slot", lambda now=None: 60)
    monkeypatch.setattr(main, "get_skip_category_state", lambda: (0, 0))
    monkeypatch.setattr(main, "get_switch_category_state", lambda: (0, 0, None))
    monkeypatch.setattr(main, "consume_skip_category_request", lambda: None)
    monkeypatch.setattr(main, "consume_switch_category_request", lambda: None)
    monkeypatch.setattr(
        main,
        "get_active_custom_text_override",
        lambda now=None: override_state["value"],
    )
    monkeypatch.setattr(
        main,
        "get_custom_text_interrupt_token",
        lambda now=None: (
            override_state["value"]["request_id"] if override_state["value"] else None
        ),
    )
    monkeypatch.setattr(
        main,
        "get_custom_text_remaining_seconds",
        lambda override, now=None: 30,
    )
    monkeypatch.setattr(
        main,
        "build_runtime_payload",
        lambda now, category_override=None, custom_override=None: {
            "slot_key": "2026-03-15:144",
            "time": "2026-03-15 12:00:00",
            "category": (
                "custom_text" if custom_override else (category_override or "pokemon")
            ),
            "data": {},
        },
    )

    display = FakeDisplay()

    with pytest.raises(StopRuntimeLoop):
        main.run_forever(display, boot_delay=0)

    assert display.categories == ["custom_text", "pokemon"]


def test_run_forever_uses_rotation_category_for_skip_after_custom_text(
    monkeypatch,
) -> None:
    override_state = {
        "value": {
            "request_id": "override-2",
            "text": "Temporary notice",
            "style": {},
            "duration_seconds": 30,
            "started_at": "2026-03-15T12:00:00",
            "expires_at": "2026-03-15T12:00:30",
            "remaining_seconds": 30,
        }
    }
    skip_state = {"request_count": 0, "handled_count": 0}

    def fake_get_skip_category_state():
        return skip_state["request_count"], skip_state["handled_count"]

    def fake_consume_skip_category_request():
        if skip_state["handled_count"] >= skip_state["request_count"]:
            return None
        skip_state["handled_count"] += 1
        return skip_state["handled_count"]

    class FakeDisplay:
        def __init__(self) -> None:
            self.categories: list[str] = []

        def display_payload(
            self,
            payload: dict,
            duration_seconds=None,
            should_interrupt=None,
        ) -> None:
            self.categories.append(payload["category"])
            if len(self.categories) == 1:
                override_state["value"] = None
                skip_state["request_count"] = 1
                return
            raise StopRuntimeLoop

    monkeypatch.setattr(main, "datetime", FakeDateTime)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "print_payload", lambda payload: None)
    monkeypatch.setattr(main, "get_current_slot_key", lambda now=None: "2026-03-15:144")
    monkeypatch.setattr(main, "get_current_category", lambda now=None: "pokemon")
    monkeypatch.setattr(main, "seconds_until_next_slot", lambda now=None: 60)
    monkeypatch.setattr(main, "get_skip_category_state", fake_get_skip_category_state)
    monkeypatch.setattr(main, "get_switch_category_state", lambda: (0, 0, None))
    monkeypatch.setattr(
        main, "consume_skip_category_request", fake_consume_skip_category_request
    )
    monkeypatch.setattr(main, "consume_switch_category_request", lambda: None)
    monkeypatch.setattr(
        main,
        "get_active_custom_text_override",
        lambda now=None: override_state["value"],
    )
    monkeypatch.setattr(
        main,
        "get_custom_text_interrupt_token",
        lambda now=None: (
            override_state["value"]["request_id"] if override_state["value"] else None
        ),
    )
    monkeypatch.setattr(
        main,
        "get_custom_text_remaining_seconds",
        lambda override, now=None: 30,
    )
    monkeypatch.setattr(
        main,
        "build_runtime_payload",
        lambda now, category_override=None, custom_override=None: {
            "slot_key": "2026-03-15:144",
            "time": "2026-03-15 12:00:00",
            "category": (
                "custom_text" if custom_override else (category_override or "pokemon")
            ),
            "data": {},
        },
    )

    display = FakeDisplay()

    with pytest.raises(StopRuntimeLoop):
        main.run_forever(display, boot_delay=0)

    assert display.categories == ["custom_text", "weather"]
