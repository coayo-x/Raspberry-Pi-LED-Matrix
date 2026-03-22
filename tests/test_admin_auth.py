from datetime import datetime

import admin_auth


def _configure_admin(monkeypatch, password: str = "s3cret!") -> str:
    password_hash = admin_auth.build_password_hash(password)
    monkeypatch.setattr(admin_auth, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(admin_auth, "ADMIN_PASSWORD_HASH", password_hash)
    return password_hash


def test_build_password_hash_verifies_correct_password() -> None:
    password_hash = admin_auth.build_password_hash("pikachu-123")

    assert admin_auth.verify_password("pikachu-123", password_hash) is True
    assert admin_auth.verify_password("wrong-password", password_hash) is False


def test_authenticate_admin_success_creates_session(
    monkeypatch, isolated_db_path
) -> None:
    _configure_admin(monkeypatch)
    monkeypatch.setattr(admin_auth, "ADMIN_SESSION_TTL_SECONDS", 600)

    result = admin_auth.authenticate_admin(
        username="admin",
        password="s3cret!",
        client_ip="127.0.0.1",
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 0, 0),
    )

    assert result["authenticated"] is True
    assert result["status"] == "ok"
    assert result["session_token"]

    session = admin_auth.get_admin_session(
        result["session_token"],
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 1, 0),
    )
    assert session is not None
    assert session["username"] == "admin"

    admin_auth.logout_admin(result["session_token"], db_path=str(isolated_db_path))
    assert (
        admin_auth.get_admin_session(
            result["session_token"],
            db_path=str(isolated_db_path),
            now=datetime(2026, 3, 15, 14, 2, 0),
        )
        is None
    )


def test_authenticate_admin_applies_progressive_lockouts(
    monkeypatch,
    isolated_db_path,
) -> None:
    _configure_admin(monkeypatch)
    client_ip = "127.0.0.1"

    attempts = [
        admin_auth.authenticate_admin(
            username="admin",
            password="wrong",
            client_ip=client_ip,
            db_path=str(isolated_db_path),
            now=datetime(2026, 3, 15, 14, 10, second),
        )
        for second in range(5)
    ]
    first_lockout = admin_auth.authenticate_admin(
        username="admin",
        password="s3cret!",
        client_ip=client_ip,
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 10, 30),
    )
    stage_two_attempts = [
        admin_auth.authenticate_admin(
            username="admin",
            password="wrong",
            client_ip=client_ip,
            db_path=str(isolated_db_path),
            now=datetime(2026, 3, 15, 14, 11, second + 5),
        )
        for second in range(3)
    ]
    stage_three_attempt = admin_auth.authenticate_admin(
        username="admin",
        password="wrong",
        client_ip=client_ip,
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 16, 10),
    )
    progressive_attempt = admin_auth.authenticate_admin(
        username="admin",
        password="wrong",
        client_ip=client_ip,
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 46, 11),
    )

    assert [result["status"] for result in attempts[:4]] == [
        "invalid_credentials",
        "invalid_credentials",
        "invalid_credentials",
        "invalid_credentials",
    ]
    assert attempts[4]["status"] == "locked"
    assert attempts[4]["retry_after_seconds"] == 60
    assert first_lockout["status"] == "locked"
    assert first_lockout["retry_after_seconds"] >= 1

    assert stage_two_attempts[0]["status"] == "invalid_credentials"
    assert stage_two_attempts[0]["remaining_attempts"] == 2
    assert stage_two_attempts[1]["status"] == "invalid_credentials"
    assert stage_two_attempts[1]["remaining_attempts"] == 1
    assert stage_two_attempts[2]["status"] == "locked"
    assert stage_two_attempts[2]["retry_after_seconds"] == 300

    assert stage_three_attempt["status"] == "locked"
    assert stage_three_attempt["retry_after_seconds"] == 1800
    assert progressive_attempt["status"] == "locked"
    assert progressive_attempt["retry_after_seconds"] == 3600


def test_successful_admin_login_resets_rate_limit_state(
    monkeypatch, isolated_db_path
) -> None:
    _configure_admin(monkeypatch)
    client_ip = "127.0.0.1"

    for second in range(4):
        result = admin_auth.authenticate_admin(
            username="admin",
            password="wrong",
            client_ip=client_ip,
            db_path=str(isolated_db_path),
            now=datetime(2026, 3, 15, 14, 40, second),
        )
        assert result["status"] == "invalid_credentials"

    success = admin_auth.authenticate_admin(
        username="admin",
        password="s3cret!",
        client_ip=client_ip,
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 40, 10),
    )
    reset_attempt = admin_auth.authenticate_admin(
        username="admin",
        password="wrong",
        client_ip=client_ip,
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 40, 20),
    )

    assert success["status"] == "ok"
    assert reset_attempt["status"] == "invalid_credentials"
    assert reset_attempt["remaining_attempts"] == 4


def test_admin_session_expires(monkeypatch, isolated_db_path) -> None:
    _configure_admin(monkeypatch)
    monkeypatch.setattr(admin_auth, "ADMIN_SESSION_TTL_SECONDS", 60)

    result = admin_auth.authenticate_admin(
        username="admin",
        password="s3cret!",
        client_ip="127.0.0.1",
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 20, 0),
    )

    session = admin_auth.get_admin_session(
        result["session_token"],
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 21, 1),
    )

    assert session is None
