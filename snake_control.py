from datetime import datetime

from config import DB_PATH
from db_manager import connect

SNAKE_MODE_ENABLED_KEY = "snake_game_enabled"
SNAKE_MODE_STATUS_KEY = "snake_game_status"
SNAKE_MODE_SCORE_KEY = "snake_game_score"
SNAKE_MODE_LAST_ENABLED_AT_KEY = "snake_game_last_enabled_at"
SNAKE_MODE_LAST_DISABLED_AT_KEY = "snake_game_last_disabled_at"
SNAKE_INPUT_REQUEST_KEY = "snake_game_input_request_count"
SNAKE_INPUT_HANDLED_KEY = "snake_game_input_handled_count"
SNAKE_INPUT_DIRECTION_KEY = "snake_game_input_direction"
SNAKE_INPUT_LAST_REQUESTED_AT_KEY = "snake_game_input_last_requested_at"

SNAKE_ACTIVE_BLOCKED_MESSAGE = (
    "Cannot change display content while snake game mode is active"
)
SNAKE_ADMIN_REQUIRED_MESSAGE = "Dashboard authentication is required."

VALID_DIRECTIONS = {"up", "down", "left", "right"}
VALID_INPUTS = VALID_DIRECTIONS | {"pause"}
VALID_STATUSES = {"idle", "waiting", "playing", "paused", "game_over"}


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


def _get_meta_text(conn, key: str) -> str | None:
    cur = conn.cursor()
    cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
    row = cur.fetchone()
    return row["value"] if row else None


def _get_meta_int(conn, key: str) -> int:
    value = _get_meta_text(conn, key)
    if value is None:
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _get_meta_bool(conn, key: str) -> bool:
    return (_get_meta_text(conn, key) or "").strip().lower() in {"1", "true", "yes"}


def _set_meta(conn, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO meta (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _normalize_direction(direction: str) -> str:
    raw_value = str(direction or "").lower()
    aliases = {
        "arrowup": "up",
        "w": "up",
        "arrowdown": "down",
        "s": "down",
        "arrowleft": "left",
        "a": "left",
        "arrowright": "right",
        "d": "right",
        " ": "pause",
        "space": "pause",
        "spacebar": "pause",
    }
    stripped_value = raw_value.strip()
    normalized = aliases.get(
        raw_value,
        aliases.get(stripped_value, stripped_value),
    )
    if normalized not in VALID_INPUTS:
        raise ValueError(
            f"Invalid snake direction '{direction}'. Expected one of: {', '.join(sorted(VALID_INPUTS))}"
        )
    return normalized


def _normalize_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized not in VALID_STATUSES:
        raise ValueError(
            f"Invalid snake status '{status}'. Expected one of: {', '.join(sorted(VALID_STATUSES))}"
        )
    return normalized


def is_snake_mode_enabled_from_conn(conn) -> bool:
    return _get_meta_bool(conn, SNAKE_MODE_ENABLED_KEY)


def _build_snake_state(conn, *, current: datetime, is_admin: bool) -> dict:
    enabled = is_snake_mode_enabled_from_conn(conn)
    status = (_get_meta_text(conn, SNAKE_MODE_STATUS_KEY) or "").strip().lower()
    if not enabled:
        status = "idle"
    elif status not in VALID_STATUSES or status == "idle":
        status = "waiting"

    request_count = _get_meta_int(conn, SNAKE_INPUT_REQUEST_KEY)
    handled_count = _get_meta_int(conn, SNAKE_INPUT_HANDLED_KEY)
    score = _get_meta_int(conn, SNAKE_MODE_SCORE_KEY)
    last_input_at = _get_meta_text(conn, SNAKE_INPUT_LAST_REQUESTED_AT_KEY) or ""
    last_enabled_at = _get_meta_text(conn, SNAKE_MODE_LAST_ENABLED_AT_KEY) or ""
    last_disabled_at = _get_meta_text(conn, SNAKE_MODE_LAST_DISABLED_AT_KEY) or ""

    return {
        "action": "snake_game",
        "label": "Snake Game Mode",
        "admin_only": True,
        "enabled": enabled,
        "active": enabled,
        "available": is_admin,
        "status": status,
        "score": score,
        "request_count": request_count,
        "handled_count": handled_count,
        "pending_request_count": max(0, request_count - handled_count),
        "direction": _get_meta_text(conn, SNAKE_INPUT_DIRECTION_KEY) or "",
        "last_requested_at": last_input_at,
        "last_enabled_at": last_enabled_at,
        "last_disabled_at": last_disabled_at,
        "updated_at": _isoformat(current),
        "error": "" if is_admin else SNAKE_ADMIN_REQUIRED_MESSAGE,
    }


def get_snake_control_state(
    db_path: str = DB_PATH,
    *,
    is_admin: bool = False,
    now: datetime | None = None,
) -> dict:
    current = _now_or_default(now)
    conn = connect(db_path)
    try:
        return _build_snake_state(conn, current=current, is_admin=is_admin)
    finally:
        conn.close()


def is_snake_mode_enabled(db_path: str = DB_PATH) -> bool:
    conn = connect(db_path)
    try:
        return is_snake_mode_enabled_from_conn(conn)
    finally:
        conn.close()


def set_snake_mode_enabled(
    enabled: bool,
    db_path: str = DB_PATH,
    *,
    is_admin: bool = False,
    now: datetime | None = None,
) -> dict:
    current = _now_or_default(now)

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        current_state = _build_snake_state(
            conn,
            current=current,
            is_admin=is_admin,
        )
        if not is_admin:
            conn.rollback()
            return {
                **current_state,
                "accepted": False,
                "updated": False,
                "error": SNAKE_ADMIN_REQUIRED_MESSAGE,
            }

        timestamp = _isoformat(current)
        _set_meta(conn, SNAKE_MODE_ENABLED_KEY, "1" if enabled else "0")
        _set_meta(conn, SNAKE_MODE_STATUS_KEY, "waiting" if enabled else "idle")
        _set_meta(conn, SNAKE_MODE_SCORE_KEY, "0")
        if enabled:
            _set_meta(conn, SNAKE_MODE_LAST_ENABLED_AT_KEY, timestamp)
        else:
            _set_meta(conn, SNAKE_MODE_LAST_DISABLED_AT_KEY, timestamp)

        request_count = _get_meta_int(conn, SNAKE_INPUT_REQUEST_KEY)
        _set_meta(conn, SNAKE_INPUT_HANDLED_KEY, str(request_count))
        _set_meta(conn, SNAKE_INPUT_DIRECTION_KEY, "")
        conn.commit()

        updated_state = _build_snake_state(
            conn,
            current=current,
            is_admin=is_admin,
        )
        return {
            **updated_state,
            "accepted": True,
            "updated": True,
            "enabled": enabled,
        }
    finally:
        conn.close()


def request_snake_input(
    direction: str,
    db_path: str = DB_PATH,
    *,
    is_admin: bool = False,
    requested_at: str | None = None,
    now: datetime | None = None,
) -> dict:
    normalized_direction = _normalize_direction(direction)
    current = _parse_timestamp(requested_at) if requested_at else None
    current = _now_or_default(now or current)
    timestamp = requested_at or _isoformat(current)

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        current_state = _build_snake_state(
            conn,
            current=current,
            is_admin=is_admin,
        )
        if not is_admin:
            conn.rollback()
            return {
                **current_state,
                "accepted": False,
                "requested": False,
                "error": SNAKE_ADMIN_REQUIRED_MESSAGE,
            }

        if not current_state["enabled"]:
            conn.rollback()
            return {
                **current_state,
                "accepted": False,
                "requested": False,
                "error": "Snake game mode is not active.",
            }

        request_count = current_state["request_count"] + 1
        _set_meta(conn, SNAKE_INPUT_REQUEST_KEY, str(request_count))
        _set_meta(conn, SNAKE_INPUT_DIRECTION_KEY, normalized_direction)
        _set_meta(conn, SNAKE_INPUT_LAST_REQUESTED_AT_KEY, timestamp)
        conn.commit()

        updated_state = _build_snake_state(
            conn,
            current=current,
            is_admin=is_admin,
        )
        return {
            **updated_state,
            "accepted": True,
            "requested": True,
            "direction": normalized_direction,
            "requested_at": timestamp,
        }
    finally:
        conn.close()


def consume_snake_input(db_path: str = DB_PATH) -> tuple[int, str] | None:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        request_count = _get_meta_int(conn, SNAKE_INPUT_REQUEST_KEY)
        handled_count = _get_meta_int(conn, SNAKE_INPUT_HANDLED_KEY)

        if not is_snake_mode_enabled_from_conn(conn):
            if handled_count < request_count:
                _set_meta(conn, SNAKE_INPUT_HANDLED_KEY, str(request_count))
                _set_meta(conn, SNAKE_INPUT_DIRECTION_KEY, "")
                conn.commit()
            else:
                conn.rollback()
            return None

        if handled_count >= request_count:
            conn.rollback()
            return None

        direction = _get_meta_text(conn, SNAKE_INPUT_DIRECTION_KEY) or ""
        try:
            normalized_direction = _normalize_direction(direction)
        except ValueError:
            _set_meta(conn, SNAKE_INPUT_HANDLED_KEY, str(request_count))
            conn.commit()
            return None

        _set_meta(conn, SNAKE_INPUT_HANDLED_KEY, str(request_count))
        conn.commit()
        return request_count, normalized_direction
    finally:
        conn.close()


def set_snake_runtime_status(
    status: str,
    *,
    score: int = 0,
    db_path: str = DB_PATH,
    now: datetime | None = None,
) -> dict:
    normalized_status = _normalize_status(status)
    current = _now_or_default(now)

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if not is_snake_mode_enabled_from_conn(conn):
            normalized_status = "idle"
            score = 0
        _set_meta(conn, SNAKE_MODE_STATUS_KEY, normalized_status)
        _set_meta(conn, SNAKE_MODE_SCORE_KEY, str(max(0, int(score))))
        conn.commit()
        return _build_snake_state(conn, current=current, is_admin=True)
    finally:
        conn.close()
