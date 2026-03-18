import http.cookiejar
import json
import threading
import urllib.error
import urllib.request

import admin_auth
from current_display_state import save_current_display_state
from dashboard_server import create_dashboard_server
from runtime_control import (
    consume_skip_category_request,
    consume_switch_category_request,
    get_alien_mode_state,
from dashboard_server import create_dashboard_server
from current_display_state import save_current_display_state
from runtime_control import (
    consume_skip_category_request,
    consume_switch_category_request,
    get_skip_category_state,
    get_switch_category_state,
    set_control_lock,
)


def _build_opener() -> urllib.request.OpenerDirector:
    cookie_jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def _fetch_json(url: str, opener: urllib.request.OpenerDirector | None = None) -> dict:
    active_opener = opener or urllib.request.build_opener()
    with active_opener.open(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url: str, opener: urllib.request.OpenerDirector | None = None) -> str:
    active_opener = opener or urllib.request.build_opener()
    with active_opener.open(url, timeout=5) as response:
        return response.read().decode("utf-8")


def _post_json(
    url: str,
    payload: dict | None = None,
    opener: urllib.request.OpenerDirector | None = None,
) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    active_opener = opener or urllib.request.build_opener()
    with active_opener.open(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _post_json_expect_error(
    url: str,
    payload: dict | None = None,
    opener: urllib.request.OpenerDirector | None = None,
) -> tuple[int, dict]:
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
    active_opener = opener or urllib.request.build_opener()
    try:
        with active_opener.open(request, timeout=5):
            raise AssertionError("Expected HTTPError")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def _install_admin(monkeypatch, password: str = "s3cret!") -> None:
    monkeypatch.setattr(admin_auth, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(
        admin_auth, "ADMIN_PASSWORD_HASH", admin_auth.build_password_hash(password)
    )


def test_dashboard_api_returns_stable_response_shape(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
def _post_json(url: str) -> dict:
    request = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def test_dashboard_api_returns_stable_response_shape(isolated_db_path) -> None:
    save_current_display_state(
        {
            "time": "2026-03-15 11:00:00",
            "slot_key": "2026-03-15:132",
            "category": "pokemon",
            "data": {
                "name": "Bulbasaur",
                "types": ["Grass", "Poison"],
                "hp": 45,
                "attack": 49,
                "defense": 49,
                "image_url": "https://example.test/bulbasaur.png",
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
        control_state = _fetch_json(f"{base_url}/api/control-state")
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
    assert state["category"] == "pokemon"
    assert state["data"]["image_url"] == "https://example.test/bulbasaur.png"
    assert control_state["auth"]["configured"] is True
    assert "services" not in control_state
    assert "data-control-state-api=" in page
    assert 'id="admin-control-button"' in page
    assert 'id="admin-login-modal"' in page
    assert 'id="admin-controls-modal"' in page
    assert 'id="pokemon-image"' in page
    assert 'id="alien-start-button"' in page
    assert 'id="alien-stop-button"' in page
    assert "/api/admin/login" in page
    assert "/api/alien/start" in page
    assert "/api/admin/login" in page
    assert 'id="toggle-skip-lock-button"' in page
    assert 'id="toggle-switch-lock-button"' in page
    assert page.count('class="admin-subcard"') == 1
    assert page.count('class="lock-row"') == 2
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
    assert second_state["category"] == "joke"
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
        status, result = _post_json(url)
        result = _post_json(url)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert result["accepted"] is True
    assert result["requested"] is True
    assert result["request_count"] == 1
    assert get_skip_category_state(str(isolated_db_path)) == (1, 0)
    assert consume_skip_category_request(str(isolated_db_path)) == 1


def test_dashboard_skip_category_endpoint_rate_limits_rapid_requests(
    isolated_db_path,
) -> None:
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/skip-category"

    try:
        _post_json(url)
        status, body = _post_json_expect_error(url)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 429
    assert body["rate_limited"] is True


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
        status, result = _post_json(url, {"category": "weather"})
        result = _post_json(url, {"category": "weather"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert result["accepted"] is True
    assert result["category"] == "weather"
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
    url = f"http://127.0.0.1:{server.server_address[1]}/api/switch-category"

    try:
        status, body = _post_json_expect_error(url, {"category": "invalid"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 400
    assert "Invalid category" in body["error"]


def test_dashboard_alien_mode_start_and_stop_endpoints(isolated_db_path) -> None:
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        start_status, start_body = _post_json(f"{base_url}/api/alien/start")
        control_state = _fetch_json(f"{base_url}/api/control-state")
        stop_status, stop_body = _post_json(f"{base_url}/api/alien/stop")
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

    assert start_status == 200
    assert start_body["active"] is True
    assert control_state["controls"]["alien_mode"]["active"] is True
    assert get_alien_mode_state(str(isolated_db_path))["active"] is False
    assert stop_status == 200
    assert stop_body["active"] is False


def test_dashboard_protected_admin_endpoint_rejects_unauthorized_request(
    assert status == 400
    assert "Invalid category" in body["error"]


def test_dashboard_protected_admin_endpoint_rejects_unauthorized_request(
def test_dashboard_skip_category_endpoint_returns_not_found_for_unknown_post(
    isolated_db_path,
) -> None:
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/admin/control-lock"

    try:
        status, body = _post_json_expect_error(
            url,
            {"action": "skip_category", "locked": True},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 401
    assert "Admin authentication is required" in body["error"]


def test_dashboard_admin_login_and_lock_controls(monkeypatch, isolated_db_path) -> None:
    _install_admin(monkeypatch)
    opener = _build_opener()
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, login = _post_json(
            f"{base_url}/api/admin/login",
            {"username": "admin", "password": "s3cret!"},
            opener=opener,
        )
        lock_status, lock_result = _post_json(
            f"{base_url}/api/admin/control-lock",
            {"action": "skip_category", "locked": True},
            opener=opener,
        )
        control_state = _fetch_json(f"{base_url}/api/control-state", opener=opener)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert login["authenticated"] is True
    assert lock_status == 200
    assert lock_result["control"]["locked"] is True
    assert control_state["auth"]["authenticated"] is True
    assert control_state["controls"]["skip_category"]["admin_override"] is True


def test_dashboard_admin_login_lockout_after_failed_attempts(
    monkeypatch,
    isolated_db_path,
) -> None:
    _install_admin(monkeypatch)
    monkeypatch.setattr(admin_auth, "ADMIN_LOGIN_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(admin_auth, "ADMIN_LOGIN_LOCKOUT_SECONDS", 300)

    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/admin/login"

    try:
        first_status, first_body = _post_json_expect_error(
            url, {"username": "admin", "password": "wrong"}
        )
        second_status, second_body = _post_json_expect_error(
            url, {"username": "admin", "password": "wrong"}
        )
        third_status, third_body = _post_json_expect_error(
            url, {"username": "admin", "password": "s3cret!"}
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert first_status == 401
    assert second_status == 429
    assert second_body["status"] == "locked"
    assert third_status == 429
    assert third_body["status"] == "locked"


def test_dashboard_control_state_reflects_public_lock(isolated_db_path) -> None:
    set_control_lock("switch_category", True, str(isolated_db_path))

    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/control-state"

    try:
        state = _fetch_json(url)
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

    assert state["auth"]["authenticated"] is False
    assert state["controls"]["switch_category"]["locked"] is True
    assert state["controls"]["switch_category"]["available"] is False
    assert status == 404
