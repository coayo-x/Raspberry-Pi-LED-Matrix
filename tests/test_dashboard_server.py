import json
import threading
import urllib.request

from dashboard_server import create_dashboard_server
from current_display_state import save_current_display_state


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8")


def test_dashboard_api_returns_stable_response_shape(isolated_db_path) -> None:
    save_current_display_state(
        {
            "time": "2026-03-15 11:00:00",
            "slot_key": "2026-03-15:132",
            "category": "weather",
            "data": {
                "location": "Erie, PA",
                "condition": "Clear",
                "temperature_f": 41,
                "wind_mph": 8,
            },
        },
        db_path=str(isolated_db_path),
        updated_at="2026-03-15T11:00:01",
    )

    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        state = _fetch_json(f"{base_url}/api/current-display-state")
        page = _fetch_text(f"{base_url}/")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert set(state) == {
        "snapshot_version",
        "has_data",
        "updated_at",
        "time",
        "slot",
        "category",
        "setup",
        "punchline",
        "data",
    }
    assert state["setup"] == "Erie, PA"
    assert state["punchline"] == "Clear | 41F | Wind 8 mph"
    assert "data-poll-interval-ms=" in page
    assert "/api/current-display-state" in page


def test_dashboard_api_reads_updated_snapshot_without_restart(isolated_db_path) -> None:
    save_current_display_state(
        {
            "time": "2026-03-15 12:00:00",
            "slot_key": "2026-03-15:144",
            "category": "pokemon",
            "data": {
                "name": "Charmander",
                "types": ["Fire"],
                "hp": 39,
                "attack": 52,
                "defense": 43,
            },
        },
        db_path=str(isolated_db_path),
        updated_at="2026-03-15T12:00:01",
    )

    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/current-display-state"

    try:
        first_state = _fetch_json(url)
        save_current_display_state(
            {
                "time": "2026-03-15 12:05:00",
                "slot_key": "2026-03-15:145",
                "category": "joke",
                "data": {
                    "type": "single",
                    "text": "I told my Pi a joke. It needed more bytes.",
                },
            },
            db_path=str(isolated_db_path),
            updated_at="2026-03-15T12:05:01",
        )
        second_state = _fetch_json(url)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert first_state["category"] == "pokemon"
    assert first_state["slot"] == "2026-03-15:144"
    assert second_state["category"] == "joke"
    assert second_state["slot"] == "2026-03-15:145"
    assert second_state["setup"] == "I told my Pi a joke. It needed more bytes."
