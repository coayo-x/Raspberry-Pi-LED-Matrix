import http.cookiejar
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

import admin_auth
import custom_text
from current_display_state import save_current_display_state
from dashboard_server import create_dashboard_server
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


def _fetch_json_expect_error(
    url: str, opener: urllib.request.OpenerDirector | None = None
) -> tuple[int, dict]:
    active_opener = opener or urllib.request.build_opener()
    try:
        with active_opener.open(url, timeout=5):
            raise AssertionError("Expected HTTPError")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


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


def _login(
    base_url: str,
    opener: urllib.request.OpenerDirector,
    *,
    username: str = "admin",
    password: str = "s3cret!",
) -> tuple[int, dict]:
    return _post_json(
        f"{base_url}/api/admin/login",
        {"username": username, "password": password},
        opener=opener,
    )


def _install_bad_words(
    monkeypatch,
    base_dir: Path,
    contents: str = "obscene\nblocked phrase\n",
) -> Path:
    path = base_dir / f"badwords-{uuid4().hex}.txt"
    path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(custom_text, "BAD_WORDS_PATH", path)
    return path


def test_dashboard_root_is_public_without_authentication(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        page = _fetch_text(f"{base_url}/")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert "Current matrix payload" in page
    assert 'id="admin-control-button"' in page
    assert 'id="custom-text-form"' in page
    assert 'id="custom-text-stop-button"' in page
    assert 'id="custom-text-lock-banner"' in page
    assert "/api/current-display-state" in page
    assert "/api/custom-text" in page
    assert "Restricted Access" not in page


def test_dashboard_safe_default_keeps_public_routes_available_when_credentials_missing(
    isolated_db_path,
) -> None:
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        page = _fetch_text(f"{base_url}/")
        state_body = _fetch_json(f"{base_url}/api/current-display-state")
        control_body = _fetch_json(f"{base_url}/api/control-state")
        skip_status, skip_body = _post_json(f"{base_url}/api/skip-category")
        switch_status, switch_body = _post_json(
            f"{base_url}/api/switch-category",
            {"category": "weather"},
        )
        login_page = _fetch_text(f"{base_url}/login")
        login_status, login_body = _post_json_expect_error(
            f"{base_url}/api/admin/login",
            {"username": "admin", "password": "s3cret!"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert "Current matrix payload" in page
    assert state_body["has_data"] is False
    assert "not configured on this host" in login_page
    assert control_body["auth"]["configured"] is False
    assert control_body["auth"]["authenticated"] is False
    assert control_body["controls"]["skip_category"]["locked"] is False
    assert control_body["controls"]["switch_category"]["locked"] is False
    assert control_body["controls"]["custom_text"]["locked"] is False
    assert skip_status == 200
    assert skip_body["accepted"] is True
    assert switch_status == 200
    assert switch_body["accepted"] is True
    assert login_status == 503
    assert login_body["status"] == "disabled"


def test_dashboard_public_controls_work_without_authentication_and_admin_endpoints_require_authentication(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        state_body = _fetch_json(f"{base_url}/api/current-display-state")
        control_body = _fetch_json(f"{base_url}/api/control-state")
        skip_status, skip_body = _post_json(f"{base_url}/api/skip-category")
        switch_status, switch_body = _post_json(
            f"{base_url}/api/switch-category",
            {"category": "weather"},
        )
        skip_lock_status, skip_lock_body = _post_json_expect_error(
            f"{base_url}/api/lock-skip"
        )
        switch_unlock_status, switch_unlock_body = _post_json_expect_error(
            f"{base_url}/api/unlock-switch"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert state_body["has_data"] is False
    assert control_body["auth"]["configured"] is True
    assert control_body["auth"]["authenticated"] is False
    assert control_body["controls"]["skip_category"]["locked"] is False
    assert control_body["controls"]["switch_category"]["locked"] is False
    assert control_body["controls"]["custom_text"]["locked"] is False
    assert skip_status == 200
    assert skip_body["accepted"] is True
    assert switch_status == 200
    assert switch_body["accepted"] is True
    assert skip_lock_status == 401
    assert skip_lock_body["configured"] is True
    assert switch_unlock_status == 401
    assert switch_unlock_body["configured"] is True


def test_dashboard_login_enables_protected_control_api(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
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
            },
        },
        db_path=str(isolated_db_path),
        updated_at="2026-03-15T11:00:01",
    )

    opener = _build_opener()
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        public_state = _fetch_json(f"{base_url}/api/current-display-state")
        public_page = _fetch_text(f"{base_url}/")
        status, login = _login(base_url, opener)
        state = _fetch_json(f"{base_url}/api/current-display-state", opener=opener)
        control_state = _fetch_json(f"{base_url}/api/control-state", opener=opener)
        page = _fetch_text(f"{base_url}/", opener=opener)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert login["authenticated"] is True
    assert public_state["category"] == "pokemon"
    assert "Current matrix payload" in public_page
    assert state["category"] == "pokemon"
    assert state["data"]["image_url"] == "https://example.test/bulbasaur.png"
    assert control_state["auth"]["authenticated"] is True
    assert "Current matrix payload" in page
    assert 'id="admin-control-button"' in page
    assert 'id="pokemon-image"' in page


def test_dashboard_wrong_password_is_rejected(monkeypatch, isolated_db_path) -> None:
    _install_admin(monkeypatch)
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, body = _post_json_expect_error(
            f"{base_url}/api/admin/login",
            {"username": "admin", "password": "wrong"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 401
    assert body["authenticated"] is False
    assert body["status"] == "invalid_credentials"


def test_dashboard_authenticated_control_endpoints_work(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    opener = _build_opener()
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        _login(base_url, opener)
        skip_status, skip_result = _post_json(
            f"{base_url}/api/skip-category",
            opener=opener,
        )
        switch_status, switch_result = _post_json(
            f"{base_url}/api/switch-category",
            {"category": "weather"},
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

    assert skip_status == 200
    assert skip_result["accepted"] is True
    assert get_skip_category_state(str(isolated_db_path)) == (1, 0)
    assert consume_skip_category_request(str(isolated_db_path)) == 1

    assert switch_status == 200
    assert switch_result["accepted"] is True
    assert switch_result["category"] == "weather"
    assert get_switch_category_state(str(isolated_db_path)) == (1, 0, "weather")
    assert consume_switch_category_request(str(isolated_db_path)) == (1, "weather")

    assert lock_status == 200
    assert lock_result["control"]["locked"] is True
    assert control_state["controls"]["skip_category"]["admin_override"] is True


def test_dashboard_admin_can_lock_and_unlock_public_controls(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    opener = _build_opener()
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        _login(base_url, opener)
        switch_lock_status, switch_lock_result = _post_json(
            f"{base_url}/api/lock-switch",
            opener=opener,
        )
        public_skip_status, public_skip_result = _post_json(
            f"{base_url}/api/skip-category"
        )
        public_switch_status, public_switch_result = _post_json_expect_error(
            f"{base_url}/api/switch-category",
            {"category": "science"},
        )
        admin_switch_status, admin_switch_result = _post_json(
            f"{base_url}/api/switch-category",
            {"category": "science"},
            opener=opener,
        )
        switch_unlock_status, switch_unlock_result = _post_json(
            f"{base_url}/api/unlock-switch",
            opener=opener,
        )
        skip_lock_status, skip_lock_result = _post_json(
            f"{base_url}/api/lock-skip",
            opener=opener,
        )
        skip_locked_state = _fetch_json(f"{base_url}/api/control-state")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert switch_lock_status == 200
    assert switch_lock_result["control"]["action"] == "switch_category"
    assert switch_lock_result["control"]["locked"] is True
    assert public_skip_status == 200
    assert public_skip_result["accepted"] is True
    assert public_switch_status == 423
    assert public_switch_result["locked"] is True
    assert admin_switch_status == 200
    assert admin_switch_result["accepted"] is True
    assert admin_switch_result["admin_override"] is True
    assert switch_unlock_status == 200
    assert switch_unlock_result["control"]["locked"] is False
    assert skip_lock_status == 200
    assert skip_lock_result["control"]["action"] == "skip_category"
    assert skip_lock_result["control"]["locked"] is True
    assert skip_locked_state["controls"]["skip_category"]["locked"] is True
    assert skip_locked_state["controls"]["switch_category"]["locked"] is False


def test_dashboard_admin_can_lock_skip_without_affecting_switch(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    opener = _build_opener()
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        _login(base_url, opener)
        skip_lock_status, skip_lock_result = _post_json(
            f"{base_url}/api/lock-skip",
            opener=opener,
        )
        public_switch_status, public_switch_result = _post_json(
            f"{base_url}/api/switch-category",
            {"category": "science"},
        )
        public_skip_status, public_skip_result = _post_json_expect_error(
            f"{base_url}/api/skip-category"
        )
        admin_skip_status, admin_skip_result = _post_json(
            f"{base_url}/api/skip-category",
            opener=opener,
        )
        skip_unlock_status, skip_unlock_result = _post_json(
            f"{base_url}/api/unlock-skip",
            opener=opener,
        )
        public_state = _fetch_json(f"{base_url}/api/control-state")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert skip_lock_status == 200
    assert skip_lock_result["control"]["action"] == "skip_category"
    assert skip_lock_result["control"]["locked"] is True
    assert public_switch_status == 200
    assert public_switch_result["accepted"] is True
    assert public_skip_status == 423
    assert public_skip_result["locked"] is True
    assert admin_skip_status == 200
    assert admin_skip_result["accepted"] is True
    assert admin_skip_result["admin_override"] is True
    assert skip_unlock_status == 200
    assert skip_unlock_result["control"]["locked"] is False
    assert public_state["controls"]["skip_category"]["locked"] is False
    assert public_state["controls"]["switch_category"]["locked"] is False


def test_dashboard_api_reads_updated_snapshot_without_restart_after_login(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
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

    opener = _build_opener()
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/current-display-state"
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        _login(base_url, opener)
        first_state = _fetch_json(url, opener=opener)
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
        second_state = _fetch_json(url, opener=opener)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert first_state["category"] == "pokemon"
    assert second_state["category"] == "joke"
    assert second_state["setup"] == "I told my Pi a joke. It needed more bytes."


def test_dashboard_unknown_post_route_returns_404_after_login(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    opener = _build_opener()
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    request = urllib.request.Request(f"{base_url}/api/unknown", method="POST")

    try:
        _login(base_url, opener)
        try:
            with opener.open(request, timeout=5):
                raise AssertionError("Expected HTTPError")
        except urllib.error.HTTPError as error:
            status = error.code
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 404


def test_dashboard_control_state_reflects_public_lock_after_login(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    set_control_lock("switch_category", True, str(isolated_db_path))
    opener = _build_opener()

    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        _login(base_url, opener)
        state = _fetch_json(f"{base_url}/api/control-state", opener=opener)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert state["auth"]["authenticated"] is True
    assert state["controls"]["skip_category"]["locked"] is False
    assert state["controls"]["switch_category"]["locked"] is True
    assert state["controls"]["switch_category"]["admin_override"] is True
    assert state["controls"]["custom_text"]["locked"] is False


def test_dashboard_custom_text_submission_updates_control_state(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, body = _post_json(
            f"{base_url}/api/custom-text",
            {
                "text": "Maintenance window at 3 PM",
                "duration_minutes": 5,
                "style": {
                    "bold": True,
                    "italic": False,
                    "underline": True,
                    "font_family": "mono",
                    "font_size": 18,
                    "text_brightness": 55,
                    "background_brightness": 35,
                    "text_color": "orange",
                    "background_color": "black",
                    "alignment": "center",
                },
            },
        )
        control_state = _fetch_json(f"{base_url}/api/control-state")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert body["accepted"] is True
    assert body["override"]["duration_minutes"] == 5
    assert body["override"]["style"]["text_brightness"] == 55
    assert body["override"]["style"]["background_brightness"] == 35
    assert body["override"]["style"]["text_color"] == "orange"
    assert control_state["controls"]["custom_text"]["active_override"] is True
    assert (
        control_state["controls"]["custom_text"]["override_text"]
        == "Maintenance window at 3 PM"
    )


def test_dashboard_custom_text_stop_requires_admin_and_clears_active_override(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    opener = _build_opener()
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        _post_json(
            f"{base_url}/api/custom-text",
            {"text": "Stop now", "duration_minutes": 5, "style": {}},
        )
        unauthorized_status, unauthorized_body = _post_json_expect_error(
            f"{base_url}/api/admin/custom-text/stop"
        )
        _login(base_url, opener)
        stop_status, stop_body = _post_json(
            f"{base_url}/api/admin/custom-text/stop",
            opener=opener,
        )
        control_state = _fetch_json(f"{base_url}/api/control-state", opener=opener)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert unauthorized_status == 401
    assert unauthorized_body["configured"] is True
    assert stop_status == 200
    assert stop_body["stopped"] is True
    assert stop_body["message"] == "Custom text stopped."
    assert control_state["controls"]["custom_text"]["active_override"] is False


def test_dashboard_custom_text_stop_is_safe_when_override_inactive(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    opener = _build_opener()
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        _login(base_url, opener)
        stop_status, stop_body = _post_json(
            f"{base_url}/api/admin/custom-text/stop",
            opener=opener,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert stop_status == 200
    assert stop_body["stopped"] is False
    assert stop_body["message"] == "No active custom text."


def test_dashboard_custom_text_rejects_blocked_words(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, body = _post_json_expect_error(
            f"{base_url}/api/custom-text",
            {
                "text": "This obscene message is blocked.",
                "duration_minutes": 5,
                "style": {},
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 400
    assert body["error"] == "Custom text contains blocked words and was rejected."


def test_dashboard_custom_text_rate_limits_rapid_repeats(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        first_status, first_body = _post_json(
            f"{base_url}/api/custom-text",
            {"text": "First request", "duration_minutes": 5, "style": {}},
        )
        second_status, second_body = _post_json_expect_error(
            f"{base_url}/api/custom-text",
            {"text": "Second request", "duration_minutes": 5, "style": {}},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert first_status == 200
    assert first_body["accepted"] is True
    assert second_status == 429
    assert second_body["rate_limited"] is True
    assert 1 <= second_body["retry_after_seconds"] <= 3


def test_dashboard_custom_text_lock_requires_admin_and_allows_admin_override(
    monkeypatch, isolated_db_path
) -> None:
    _install_admin(monkeypatch)
    _install_bad_words(monkeypatch, isolated_db_path.parent)
    opener = _build_opener()
    server = create_dashboard_server(
        host="127.0.0.1", port=0, db_path=str(isolated_db_path)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        unauthorized_status, unauthorized_body = _post_json_expect_error(
            f"{base_url}/api/lock-custom-text"
        )
        _login(base_url, opener)
        lock_status, lock_body = _post_json(
            f"{base_url}/api/lock-custom-text",
            opener=opener,
        )
        public_status, public_body = _post_json_expect_error(
            f"{base_url}/api/custom-text",
            {"text": "Public request", "duration_minutes": 5, "style": {}},
        )
        admin_status, admin_body = _post_json(
            f"{base_url}/api/custom-text",
            {"text": "Admin request", "duration_minutes": 5, "style": {}},
            opener=opener,
        )
        unlock_status, unlock_body = _post_json(
            f"{base_url}/api/unlock-custom-text",
            opener=opener,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert unauthorized_status == 401
    assert unauthorized_body["configured"] is True
    assert lock_status == 200
    assert lock_body["control"]["locked"] is True
    assert public_status == 423
    assert public_body["locked"] is True
    assert public_body["error"] == "Custom text is currently locked by admin."
    assert admin_status == 200
    assert admin_body["accepted"] is True
    assert admin_body["admin_override"] is True
    assert unlock_status == 200
    assert unlock_body["control"]["locked"] is False
