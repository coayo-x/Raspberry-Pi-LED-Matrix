from datetime import datetime

from config import DB_PATH
from db_manager import connect

SKIP_CATEGORY_REQUEST_KEY = "skip_category_request_count"
SKIP_CATEGORY_HANDLED_KEY = "skip_category_handled_count"
SKIP_CATEGORY_LAST_REQUESTED_AT_KEY = "skip_category_last_requested_at"


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
