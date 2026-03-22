import argparse
import base64
import binascii
import hashlib
import hmac
import math
import secrets
import threading
from datetime import datetime, timedelta
from getpass import getpass

try:
    import bcrypt
except ImportError:
    bcrypt = None

from config import (
    ADMIN_PASSWORD_HASH,
    ADMIN_SESSION_TTL_SECONDS,
    ADMIN_USERNAME,
    DB_PATH,
)
from db_manager import connect

PASSWORD_HASH_SCHEME = "bcrypt"
LEGACY_PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 600_000
BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
BCRYPT_DEFAULT_ROUNDS = 12
LOGIN_LOCKOUT_STAGES = (
    {"max_failures": 5, "lockout_seconds": 60},
    {"max_failures": 3, "lockout_seconds": 300},
    {"max_failures": 1, "lockout_seconds": 1800},
)
_LOGIN_ATTEMPT_STATE: dict[str, dict[str, int | datetime | None]] = {}
_LOGIN_ATTEMPT_STATE_LOCK = threading.Lock()


def _now_or_default(now: datetime | None = None) -> datetime:
    return now or datetime.now()


def _isoformat(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cleanup_expired_sessions(conn, now: datetime) -> None:
    conn.execute(
        "DELETE FROM admin_sessions WHERE expires_at <= ?",
        (_isoformat(now),),
    )


def _get_session_row(conn, session_token: str):
    token_hash = _hash_session_token(session_token)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT username, created_at, expires_at, last_seen_at, client_ip
        FROM admin_sessions
        WHERE token_hash = ?
        """,
        (token_hash,),
    )
    return cur.fetchone()


def is_admin_configured() -> bool:
    return bool(ADMIN_USERNAME and ADMIN_PASSWORD_HASH)


def reset_login_attempts(subject: str | None = None) -> None:
    with _LOGIN_ATTEMPT_STATE_LOCK:
        if subject is None:
            _LOGIN_ATTEMPT_STATE.clear()
            return
        _LOGIN_ATTEMPT_STATE.pop(subject, None)


def _default_login_attempt_state() -> dict[str, int | datetime | None]:
    return {
        "failed_attempts": 0,
        "violation_count": 0,
        "locked_until": None,
    }


def _get_login_attempt_state(
    subject: str, current: datetime
) -> dict[str, int | datetime | None]:
    state = _LOGIN_ATTEMPT_STATE.get(subject)
    if state is None:
        state = _default_login_attempt_state()
        _LOGIN_ATTEMPT_STATE[subject] = state

    locked_until = state.get("locked_until")
    if isinstance(locked_until, datetime) and locked_until <= current:
        state["failed_attempts"] = 0
        state["locked_until"] = None

    return state


def _get_login_lockout_stage(violation_count: int) -> dict[str, int]:
    if violation_count < len(LOGIN_LOCKOUT_STAGES):
        return LOGIN_LOCKOUT_STAGES[violation_count]

    last_stage = LOGIN_LOCKOUT_STAGES[-1]
    additional_violations = violation_count - (len(LOGIN_LOCKOUT_STAGES) - 1)
    return {
        "max_failures": last_stage["max_failures"],
        "lockout_seconds": last_stage["lockout_seconds"]
        * (2 ** additional_violations),
    }


def _build_locked_response(locked_until: datetime, current: datetime) -> dict:
    retry_after = max(1, math.ceil((locked_until - current).total_seconds()))
    return {
        "configured": True,
        "authenticated": False,
        "status": "locked",
        "error": "Too many failed login attempts. Try again after the lockout expires.",
        "locked_until": _isoformat(locked_until),
        "retry_after_seconds": retry_after,
    }


def _record_failed_login_attempt(subject: str, current: datetime) -> dict:
    with _LOGIN_ATTEMPT_STATE_LOCK:
        state = _get_login_attempt_state(subject, current)
        locked_until = state.get("locked_until")
        if isinstance(locked_until, datetime) and locked_until > current:
            return _build_locked_response(locked_until, current)

        violation_count = int(state["violation_count"] or 0)
        stage = _get_login_lockout_stage(violation_count)
        failed_attempts = int(state["failed_attempts"] or 0) + 1
        state["failed_attempts"] = failed_attempts

        response = {
            "configured": True,
            "authenticated": False,
            "status": "invalid_credentials",
            "error": "Invalid username or password.",
            "failed_attempts": failed_attempts,
            "remaining_attempts": max(0, stage["max_failures"] - failed_attempts),
        }

        if failed_attempts >= stage["max_failures"]:
            locked_until = current + timedelta(seconds=stage["lockout_seconds"])
            state["failed_attempts"] = 0
            state["violation_count"] = violation_count + 1
            state["locked_until"] = locked_until
            response.update(
                {
                    "status": "locked",
                    "error": "Too many failed login attempts. Try again after the lockout expires.",
                    "locked_until": _isoformat(locked_until),
                    "retry_after_seconds": stage["lockout_seconds"],
                    "remaining_attempts": 0,
                }
            )
        else:
            state["locked_until"] = None

        return response


def _build_pbkdf2_password_hash(
    password: str,
    *,
    iterations: int = PASSWORD_HASH_ITERATIONS,
    salt: bytes | None = None,
) -> str:
    active_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        active_salt,
        iterations,
    )
    salt_b64 = base64.b64encode(active_salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"{LEGACY_PASSWORD_HASH_SCHEME}${iterations}${salt_b64}${digest_b64}"


def build_password_hash(
    password: str,
    *,
    iterations: int = PASSWORD_HASH_ITERATIONS,
    salt: bytes | None = None,
) -> str:
    if not password:
        raise ValueError("Password must not be empty.")

    if bcrypt is not None and salt is None:
        return bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=BCRYPT_DEFAULT_ROUNDS),
        ).decode("utf-8")

    return _build_pbkdf2_password_hash(
        password,
        iterations=iterations,
        salt=salt,
    )


def _verify_pbkdf2_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_b64, digest_b64 = encoded_hash.split("$", 3)
    except ValueError:
        return False

    if scheme != LEGACY_PASSWORD_HASH_SCHEME:
        return False

    try:
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected_digest = base64.b64decode(digest_b64.encode("ascii"))
    except (TypeError, ValueError, binascii.Error):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def verify_password(password: str, encoded_hash: str) -> bool:
    if encoded_hash.startswith(BCRYPT_PREFIXES):
        if bcrypt is None:
            return False

        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                encoded_hash.encode("utf-8"),
            )
        except ValueError:
            return False

    return _verify_pbkdf2_password(password, encoded_hash)


def get_admin_session(
    session_token: str | None,
    db_path: str = DB_PATH,
    now: datetime | None = None,
) -> dict | None:
    if not session_token or not is_admin_configured():
        return None

    current = _now_or_default(now)
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _cleanup_expired_sessions(conn, current)
        row = _get_session_row(conn, session_token)
        if row is None:
            conn.commit()
            return None

        expires_at = _parse_timestamp(row["expires_at"])
        if expires_at is None or expires_at <= current:
            conn.execute(
                "DELETE FROM admin_sessions WHERE token_hash = ?",
                (_hash_session_token(session_token),),
            )
            conn.commit()
            return None

        conn.execute(
            """
            UPDATE admin_sessions
            SET last_seen_at = ?
            WHERE token_hash = ?
            """,
            (_isoformat(current), _hash_session_token(session_token)),
        )
        conn.commit()
        return {
            "authenticated": True,
            "username": row["username"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "client_ip": row["client_ip"],
        }
    finally:
        conn.close()


def get_admin_status(
    session_token: str | None = None,
    db_path: str = DB_PATH,
    now: datetime | None = None,
) -> dict:
    session = get_admin_session(session_token, db_path=db_path, now=now)
    return {
        "configured": is_admin_configured(),
        "authenticated": bool(session),
        "username": session["username"] if session else "",
        "expires_at": session["expires_at"] if session else "",
    }


def authenticate_admin(
    username: str,
    password: str,
    client_ip: str,
    db_path: str = DB_PATH,
    now: datetime | None = None,
) -> dict:
    if not is_admin_configured():
        return {
            "configured": False,
            "authenticated": False,
            "status": "disabled",
            "error": "Admin credentials are not configured on this dashboard host.",
        }

    current = _now_or_default(now)
    subject = (client_ip or "unknown").strip() or "unknown"
    attempted_at = _isoformat(current)

    with _LOGIN_ATTEMPT_STATE_LOCK:
        state = _get_login_attempt_state(subject, current)
        locked_until = state.get("locked_until")
        if isinstance(locked_until, datetime) and locked_until > current:
            return _build_locked_response(locked_until, current)

    normalized_username = str(username).strip()
    valid_username = hmac.compare_digest(normalized_username, ADMIN_USERNAME)
    valid_password = verify_password(password, ADMIN_PASSWORD_HASH)
    if not (valid_username and valid_password):
        return _record_failed_login_attempt(subject, current)

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _cleanup_expired_sessions(conn, current)
        session_token = secrets.token_urlsafe(32)
        expires_at = current + timedelta(seconds=ADMIN_SESSION_TTL_SECONDS)
        conn.execute(
            """
            INSERT INTO admin_sessions (
                token_hash, username, created_at, expires_at, last_seen_at, client_ip
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _hash_session_token(session_token),
                ADMIN_USERNAME,
                attempted_at,
                _isoformat(expires_at),
                attempted_at,
                subject,
            ),
        )
        conn.commit()
        reset_login_attempts(subject)
        return {
            "configured": True,
            "authenticated": True,
            "status": "ok",
            "username": ADMIN_USERNAME,
            "expires_at": _isoformat(expires_at),
            "session_token": session_token,
        }
    finally:
        conn.close()


def logout_admin(session_token: str | None, db_path: str = DB_PATH) -> None:
    if not session_token:
        return

    conn = connect(db_path)
    try:
        conn.execute(
            "DELETE FROM admin_sessions WHERE token_hash = ?",
            (_hash_session_token(session_token),),
        )
        conn.commit()
    finally:
        conn.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Admin auth helper utilities.")
    parser.add_argument(
        "--hash-password",
        action="store_true",
        help="Prompt for a password and print a secure ADMIN_PASSWORD_HASH value.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not args.hash_password:
        raise SystemExit(
            "Use --hash-password to generate an ADMIN_PASSWORD_HASH value."
        )

    password = getpass("Password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords did not match.")

    print(build_password_hash(password))


if __name__ == "__main__":
    main()
