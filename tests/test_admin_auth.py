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


def test_authenticate_admin_locks_after_too_many_failures(
    monkeypatch,
    isolated_db_path,
) -> None:
    _configure_admin(monkeypatch)
    monkeypatch.setattr(admin_auth, "ADMIN_LOGIN_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(admin_auth, "ADMIN_LOGIN_LOCKOUT_SECONDS", 120)

    first = admin_auth.authenticate_admin(
        username="admin",
        password="wrong",
        client_ip="127.0.0.1",
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 10, 0),
    )
    second = admin_auth.authenticate_admin(
        username="admin",
        password="wrong",
        client_ip="127.0.0.1",
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 10, 10),
    )
    third = admin_auth.authenticate_admin(
        username="admin",
        password="wrong",
        client_ip="127.0.0.1",
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 10, 20),
    )
    locked = admin_auth.authenticate_admin(
        username="admin",
        password="s3cret!",
        client_ip="127.0.0.1",
        db_path=str(isolated_db_path),
        now=datetime(2026, 3, 15, 14, 10, 30),
    )

    assert first["status"] == "invalid_credentials"
    assert second["status"] == "invalid_credentials"
    assert third["status"] == "locked"
    assert locked["status"] == "locked"
    assert locked["retry_after_seconds"] >= 1


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
