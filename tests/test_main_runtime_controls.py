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


class AlienResumeDisplay:
    def __init__(self, alien_state: dict) -> None:
        self.alien_state = alien_state
        self.alien_runs = 0
        self.categories: list[str] = []

    def run_alien_animation(self, should_interrupt=None) -> None:
        self.alien_runs += 1
        assert should_interrupt is not None
        assert should_interrupt() is False
        self.alien_state["active"] = False

    def display_payload(
        self,
        payload: dict,
        duration_seconds=None,
        should_interrupt=None,
    ) -> None:
        self.categories.append(payload["category"])
        raise StopRuntimeLoop


def test_run_forever_resumes_rotation_after_alien_mode_stops(monkeypatch) -> None:
    alien_state = {"active": True}

    monkeypatch.setattr(main, "datetime", FakeDateTime)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "print_payload", lambda payload: None)
    monkeypatch.setattr(main, "save_current_display_state", lambda payload: payload)
    monkeypatch.setattr(main, "alien_mode_active", lambda: alien_state["active"])
    monkeypatch.setattr(main, "get_current_slot_key", lambda now=None: "2026-03-15:144")
    monkeypatch.setattr(main, "seconds_until_next_slot", lambda now=None: 60)
    monkeypatch.setattr(main, "get_skip_category_state", lambda: (0, 0))
    monkeypatch.setattr(main, "consume_skip_category_request", lambda: None)
    monkeypatch.setattr(main, "get_switch_category_state", lambda: (0, 0, None))
    monkeypatch.setattr(main, "consume_switch_category_request", lambda: None)
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

    display = AlienResumeDisplay(alien_state)

    with pytest.raises(StopRuntimeLoop):
        main.run_forever(display, boot_delay=0)

    assert display.alien_runs == 1
    assert display.categories == ["pokemon"]
