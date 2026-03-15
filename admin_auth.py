import argparse
import base64
import binascii
import hashlib
import hmac
import math
import secrets
from datetime import datetime, timedelta
from getpass import getpass

from config import (
    ADMIN_LOGIN_LOCKOUT_SECONDS,
    ADMIN_LOGIN_MAX_ATTEMPTS,
    ADMIN_PASSWORD_HASH,
    ADMIN_SESSION_TTL_SECONDS,
    ADMIN_USERNAME,
    DB_PATH,
)
from db_manager import connect

PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 600_000


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


def _get_login_attempt_row(conn, subject: str):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT failed_attempts, locked_until, last_failed_at
        FROM admin_login_attempts
        WHERE subject = ?
        """,
        (subject,),
    )
    return cur.fetchone()


def _set_login_attempt(
    conn,
    subject: str,
    failed_attempts: int,
    locked_until: str | None,
    last_failed_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO admin_login_attempts (
            subject, failed_attempts, locked_until, last_failed_at
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(subject) DO UPDATE
        SET failed_attempts = excluded.failed_attempts,
            locked_until = excluded.locked_until,
            last_failed_at = excluded.last_failed_at
        """,
        (subject, failed_attempts, locked_until, last_failed_at),
    )


def _clear_login_attempt(conn, subject: str) -> None:
    conn.execute("DELETE FROM admin_login_attempts WHERE subject = ?", (subject,))


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


def build_password_hash(
    password: str,
    *,
    iterations: int = PASSWORD_HASH_ITERATIONS,
    salt: bytes | None = None,
) -> str:
    if not password:
        raise ValueError("Password must not be empty.")

    active_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        active_salt,
        iterations,
    )
    salt_b64 = base64.b64encode(active_salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"{PASSWORD_HASH_SCHEME}${iterations}${salt_b64}${digest_b64}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_b64, digest_b64 = encoded_hash.split("$", 3)
    except ValueError:
        return False

    if scheme != PASSWORD_HASH_SCHEME:
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

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _cleanup_expired_sessions(conn, current)
        attempt_row = _get_login_attempt_row(conn, subject)
        locked_until = _parse_timestamp(
            attempt_row["locked_until"] if attempt_row else None
        )

        if locked_until is not None and locked_until > current:
            conn.commit()
            retry_after = max(1, math.ceil((locked_until - current).total_seconds()))
            return {
                "configured": True,
                "authenticated": False,
                "status": "locked",
                "error": "Too many failed login attempts. Try again after the lockout expires.",
                "locked_until": _isoformat(locked_until),
                "retry_after_seconds": retry_after,
            }

        normalized_username = str(username).strip()
        valid_username = hmac.compare_digest(normalized_username, ADMIN_USERNAME)
        valid_password = valid_username and verify_password(
            password, ADMIN_PASSWORD_HASH
        )

        if not valid_password:
            failed_attempts = (attempt_row["failed_attempts"] if attempt_row else 0) + 1
            response = {
                "configured": True,
                "authenticated": False,
                "status": "invalid_credentials",
                "error": "Invalid username or password.",
                "failed_attempts": failed_attempts,
                "remaining_attempts": max(
                    0, ADMIN_LOGIN_MAX_ATTEMPTS - failed_attempts
                ),
            }

            lockout_until = None
            if failed_attempts >= ADMIN_LOGIN_MAX_ATTEMPTS:
                lockout_until = current + timedelta(seconds=ADMIN_LOGIN_LOCKOUT_SECONDS)
                response.update(
                    {
                        "status": "locked",
                        "error": "Too many failed login attempts. Try again after the lockout expires.",
                        "locked_until": _isoformat(lockout_until),
                        "retry_after_seconds": ADMIN_LOGIN_LOCKOUT_SECONDS,
                        "remaining_attempts": 0,
                    }
                )

            _set_login_attempt(
                conn,
                subject,
                failed_attempts=failed_attempts,
                locked_until=_isoformat(lockout_until) if lockout_until else None,
                last_failed_at=attempted_at,
            )
            conn.commit()
            return response

        _clear_login_attempt(conn, subject)
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
        help="Prompt for a password and print a PBKDF2 hash for ADMIN_PASSWORD_HASH.",
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
