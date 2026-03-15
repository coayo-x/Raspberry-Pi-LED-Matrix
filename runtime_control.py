from datetime import datetime

from config import DB_PATH
from db_manager import connect
from rotation_engine import DISPLAY_SEQUENCE

SKIP_CATEGORY_REQUEST_KEY = "skip_category_request_count"
SKIP_CATEGORY_HANDLED_KEY = "skip_category_handled_count"
SKIP_CATEGORY_LAST_REQUESTED_AT_KEY = "skip_category_last_requested_at"
SWITCH_CATEGORY_REQUEST_KEY = "switch_category_request_count"
SWITCH_CATEGORY_HANDLED_KEY = "switch_category_handled_count"
SWITCH_CATEGORY_LAST_REQUESTED_AT_KEY = "switch_category_last_requested_at"
SWITCH_CATEGORY_VALUE_KEY = "switch_category_value"


def _get_meta_text(conn, key: str) -> str | None:
    cur = conn.cursor()
    cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
    row = cur.fetchone()
    return row["value"] if row else None


def _normalize_category(category: str) -> str:
    normalized = str(category).strip().lower()
    if normalized not in DISPLAY_SEQUENCE:
        raise ValueError(
            f"Invalid category '{category}'. Expected one of: {', '.join(DISPLAY_SEQUENCE)}"
        )
    return normalized


def _get_meta_int(conn, key: str) -> int:
    cur = conn.cursor()
    cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
    row = cur.fetchone()
    if row is None:
        return 0

    try:
        return int(row["value"])
    except (TypeError, ValueError):
        return 0


def _set_meta(conn, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO meta (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def get_skip_category_state(db_path: str = DB_PATH) -> tuple[int, int]:
    conn = connect(db_path)
    try:
        return (
            _get_meta_int(conn, SKIP_CATEGORY_REQUEST_KEY),
            _get_meta_int(conn, SKIP_CATEGORY_HANDLED_KEY),
        )
    finally:
        conn.close()


def get_switch_category_state(db_path: str = DB_PATH) -> tuple[int, int, str | None]:
    conn = connect(db_path)
    try:
        return (
            _get_meta_int(conn, SWITCH_CATEGORY_REQUEST_KEY),
            _get_meta_int(conn, SWITCH_CATEGORY_HANDLED_KEY),
            _get_meta_text(conn, SWITCH_CATEGORY_VALUE_KEY),
        )
    finally:
        conn.close()


def request_skip_category(
    db_path: str = DB_PATH, requested_at: str | None = None
) -> dict:
    timestamp = requested_at or datetime.now().isoformat(timespec="seconds")

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        request_count = _get_meta_int(conn, SKIP_CATEGORY_REQUEST_KEY) + 1
        _set_meta(conn, SKIP_CATEGORY_REQUEST_KEY, str(request_count))
        _set_meta(conn, SKIP_CATEGORY_LAST_REQUESTED_AT_KEY, timestamp)
        conn.commit()
        return {
            "requested": True,
            "request_count": request_count,
            "requested_at": timestamp,
        }
    finally:
        conn.close()


def request_switch_category(
    category: str, db_path: str = DB_PATH, requested_at: str | None = None
) -> dict:
    normalized_category = _normalize_category(category)
    timestamp = requested_at or datetime.now().isoformat(timespec="seconds")

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        request_count = _get_meta_int(conn, SWITCH_CATEGORY_REQUEST_KEY) + 1
        _set_meta(conn, SWITCH_CATEGORY_REQUEST_KEY, str(request_count))
        _set_meta(conn, SWITCH_CATEGORY_VALUE_KEY, normalized_category)
        _set_meta(conn, SWITCH_CATEGORY_LAST_REQUESTED_AT_KEY, timestamp)
        conn.commit()
        return {
            "requested": True,
            "category": normalized_category,
            "request_count": request_count,
            "requested_at": timestamp,
        }
    finally:
        conn.close()


def consume_skip_category_request(db_path: str = DB_PATH) -> int | None:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        request_count = _get_meta_int(conn, SKIP_CATEGORY_REQUEST_KEY)
        handled_count = _get_meta_int(conn, SKIP_CATEGORY_HANDLED_KEY)

        if handled_count >= request_count:
            conn.rollback()
            return None

        handled_count += 1
        _set_meta(conn, SKIP_CATEGORY_HANDLED_KEY, str(handled_count))
        conn.commit()
        return handled_count
    finally:
        conn.close()


def consume_switch_category_request(
    db_path: str = DB_PATH,
) -> tuple[int, str] | None:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        request_count = _get_meta_int(conn, SWITCH_CATEGORY_REQUEST_KEY)
        handled_count = _get_meta_int(conn, SWITCH_CATEGORY_HANDLED_KEY)

        if handled_count >= request_count:
            conn.rollback()
            return None

        category = _get_meta_text(conn, SWITCH_CATEGORY_VALUE_KEY)
        if category is None:
            _set_meta(conn, SWITCH_CATEGORY_HANDLED_KEY, str(request_count))
            conn.commit()
            return None

        normalized_category = _normalize_category(category)
        handled_count = request_count
        _set_meta(conn, SWITCH_CATEGORY_HANDLED_KEY, str(handled_count))
        conn.commit()
        return handled_count, normalized_category
    finally:
        conn.close()
