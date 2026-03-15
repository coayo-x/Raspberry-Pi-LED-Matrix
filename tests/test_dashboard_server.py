import json
import threading
import urllib.error
import urllib.request

from dashboard_server import create_dashboard_server
from current_display_state import save_current_display_state
from runtime_control import (
    consume_skip_category_request,
    consume_switch_category_request,
    get_skip_category_state,
    get_switch_category_state,
)
from runtime_control import consume_skip_category_request, get_skip_category_state


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8")


def _post_json(url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
def _post_json(url: str) -> dict:
    request = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


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
    assert "/api/skip-category" in page
    assert "/api/switch-category" in page


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


def test_dashboard_skip_category_endpoint_records_runtime_request(
    isolated_db_path,
) -> None:
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/skip-category"

    try:
        result = _post_json(url)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result["requested"] is True
    assert result["request_count"] == 1
    assert get_skip_category_state(str(isolated_db_path)) == (1, 0)
    assert consume_skip_category_request(str(isolated_db_path)) == 1


def test_dashboard_switch_category_endpoint_records_runtime_request(
    isolated_db_path,
) -> None:
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/switch-category"

    try:
        result = _post_json(url, {"category": "weather"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result["requested"] is True
    assert result["category"] == "weather"
    assert result["request_count"] == 1
    assert get_switch_category_state(str(isolated_db_path)) == (1, 0, "weather")
    assert consume_switch_category_request(str(isolated_db_path)) == (1, "weather")


def test_dashboard_switch_category_endpoint_rejects_invalid_category(
    isolated_db_path,
) -> None:
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}/api/switch-category",
        data=json.dumps({"category": "invalid"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=5):
            pass
    except urllib.error.HTTPError as error:
        status = error.code
        body = json.loads(error.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 400
    assert "Invalid category" in body["error"]


def test_dashboard_skip_category_endpoint_returns_not_found_for_unknown_post(
    isolated_db_path,
) -> None:
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}/api/unknown",
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=5):
            pass
    except urllib.error.HTTPError as error:
        status = error.code
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 404
