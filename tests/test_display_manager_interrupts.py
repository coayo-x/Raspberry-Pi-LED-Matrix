from PIL import ImageChops

import main
from display_manager import DisplayManager


def _blank_frame(display: DisplayManager):
    return display._prepare_image(display._new_canvas())


def test_build_interrupt_checker_triggers_when_slot_changes(monkeypatch) -> None:
    state = {"slot_key": "2026-03-19:30"}

    monkeypatch.setattr(
        main, "get_current_slot_key", lambda now=None: state["slot_key"]
    )
    monkeypatch.setattr(main, "get_skip_category_state", lambda: (0, 0))
    monkeypatch.setattr(main, "get_switch_category_state", lambda: (0, 0, None))

    checker = main._build_interrupt_checker(0, 0, "2026-03-19:30")

    assert checker() is False

    state["slot_key"] = "2026-03-19:31"

    assert checker() is True


def test_display_payload_clears_frame_after_interrupt() -> None:
    display = DisplayManager(use_matrix=False)
    payload = {
        "slot_key": "2026-03-19:30",
        "time": "2026-03-19 02:30:00",
        "category": "weather",
        "data": {
            "location": "Erie, PA",
            "condition": "Clear",
            "temperature_f": 41,
            "wind_mph": 8,
        },
    }
    calls = {"count": 0}

    def should_interrupt() -> bool:
        calls["count"] += 1
        return calls["count"] > 3

    display.display_payload(
        payload,
        duration_seconds=10,
        should_interrupt=should_interrupt,
    )

    assert display.last_frame is not None
    assert (
        ImageChops.difference(display.last_frame, _blank_frame(display)).getbbox()
        is None
    )
