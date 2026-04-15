import math
from datetime import datetime

from config import (
    DB_PATH,
    SKIP_CATEGORY_COOLDOWN_SECONDS,
    SWITCH_CATEGORY_COOLDOWN_SECONDS,
)
from custom_text import (
    get_active_custom_text_override_from_conn,
    get_custom_text_override_from_conn,
)
from db_manager import connect
from rotation_engine import DISPLAY_SEQUENCE
from snake_control import (
    SNAKE_ACTIVE_BLOCKED_MESSAGE,
    is_snake_mode_enabled_from_conn,
)

SKIP_CATEGORY_REQUEST_KEY = "skip_category_request_count"
SKIP_CATEGORY_HANDLED_KEY = "skip_category_handled_count"
SKIP_CATEGORY_LAST_REQUESTED_AT_KEY = "skip_category_last_requested_at"
SKIP_CATEGORY_LAST_ACCEPTED_AT_KEY = "skip_category_last_accepted_at"
SKIP_CATEGORY_LOCKED_KEY = "skip_category_locked"

SWITCH_CATEGORY_REQUEST_KEY = "switch_category_request_count"
SWITCH_CATEGORY_HANDLED_KEY = "switch_category_handled_count"
SWITCH_CATEGORY_LAST_REQUESTED_AT_KEY = "switch_category_last_requested_at"
SWITCH_CATEGORY_LAST_ACCEPTED_AT_KEY = "switch_category_last_accepted_at"
SWITCH_CATEGORY_VALUE_KEY = "switch_category_value"
SWITCH_CATEGORY_LOCKED_KEY = "switch_category_locked"
CUSTOM_TEXT_FORCE_KEY = "custom_text_force"

CONTROL_ACTIONS = {
    "skip_category": {
        "label": "Skip Category",
        "request_key": SKIP_CATEGORY_REQUEST_KEY,
        "handled_key": SKIP_CATEGORY_HANDLED_KEY,
        "last_requested_key": SKIP_CATEGORY_LAST_REQUESTED_AT_KEY,
        "last_accepted_key": SKIP_CATEGORY_LAST_ACCEPTED_AT_KEY,
        "lock_key": SKIP_CATEGORY_LOCKED_KEY,
        "cooldown_seconds": SKIP_CATEGORY_COOLDOWN_SECONDS,
        "value_key": None,
    },
    "switch_category": {
        "label": "Switch Category",
        "request_key": SWITCH_CATEGORY_REQUEST_KEY,
        "handled_key": SWITCH_CATEGORY_HANDLED_KEY,
        "last_requested_key": SWITCH_CATEGORY_LAST_REQUESTED_AT_KEY,
        "last_accepted_key": SWITCH_CATEGORY_LAST_ACCEPTED_AT_KEY,
        "lock_key": SWITCH_CATEGORY_LOCKED_KEY,
        "cooldown_seconds": SWITCH_CATEGORY_COOLDOWN_SECONDS,
        "value_key": SWITCH_CATEGORY_VALUE_KEY,
    },
}

CATEGORY_CHANGE_BLOCKED_MESSAGE = "Cannot change category while custom text is active"


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


def _get_forced_custom_text_override_from_conn(
    conn,
    *,
    now: datetime | None = None,
) -> dict | None:
    if not _get_meta_bool(conn, CUSTOM_TEXT_FORCE_KEY):
        return None

    return get_custom_text_override_from_conn(conn, now=now)


def _normalize_category(category: str) -> str:
    normalized = str(category).strip().lower()
    if normalized not in DISPLAY_SEQUENCE:
        raise ValueError(
            f"Invalid category '{category}'. Expected one of: {', '.join(DISPLAY_SEQUENCE)}"
        )
    return normalized


def _normalize_action(action: str) -> str:
    normalized = str(action).strip().lower()
    if normalized not in CONTROL_ACTIONS:
        raise ValueError(
            f"Invalid control action '{action}'. Expected one of: {', '.join(sorted(CONTROL_ACTIONS))}"
        )
    return normalized


def _cooldown_remaining_seconds(
    last_accepted_at: str | None,
    cooldown_seconds: int,
    current: datetime,
) -> int:
    if cooldown_seconds <= 0:
        return 0

    accepted_at = _parse_timestamp(last_accepted_at)
    if accepted_at is None:
        return 0

    elapsed = (current - accepted_at).total_seconds()
    remaining = cooldown_seconds - elapsed
    if remaining <= 0:
        return 0
    return max(1, math.ceil(remaining))


def _build_action_state(
    conn, action: str, *, current: datetime, is_admin: bool
) -> dict:
    normalized_action = _normalize_action(action)
    definition = CONTROL_ACTIONS[normalized_action]
    request_count = _get_meta_int(conn, definition["request_key"])
    handled_count = _get_meta_int(conn, definition["handled_key"])
    action_locked = _get_meta_bool(conn, definition["lock_key"])
    locked = action_locked
    cooldown_remaining = _cooldown_remaining_seconds(
        _get_meta_text(conn, definition["last_accepted_key"]),
        definition["cooldown_seconds"],
        current,
    )
    requested_category = None
    if definition["value_key"] is not None:
        requested_category = _get_meta_text(conn, definition["value_key"])

    custom_text_active = (
        get_active_custom_text_override_from_conn(conn, now=current) is not None
    )
    forced_custom_text_active = (
        _get_forced_custom_text_override_from_conn(conn, now=current) is not None
    )
    snake_game_active = is_snake_mode_enabled_from_conn(conn)
    is_blocked = (
        snake_game_active
        or custom_text_active
        or forced_custom_text_active
        or cooldown_remaining > 0
        or (locked and not is_admin)
    )
    if snake_game_active:
        status = "snake_game_active"
    elif custom_text_active or forced_custom_text_active:
        status = "custom_text_active"
    elif locked and not is_admin:
        status = "locked"
    elif cooldown_remaining > 0:
        status = "cooldown"
    else:
        status = "ready"

    return {
        "action": normalized_action,
        "label": definition["label"],
        "locked": locked,
        "action_locked": action_locked,
        "admin_override": bool(locked and is_admin),
        "cooldown_seconds": definition["cooldown_seconds"],
        "cooldown_remaining_seconds": cooldown_remaining,
        "request_count": request_count,
        "handled_count": handled_count,
        "pending_request_count": max(0, request_count - handled_count),
        "last_requested_at": _get_meta_text(conn, definition["last_requested_key"])
        or "",
        "last_accepted_at": _get_meta_text(conn, definition["last_accepted_key"]) or "",
        "available": not is_blocked,
        "status": status,
        "requested_category": requested_category,
        "blocked_by_custom_text": custom_text_active or forced_custom_text_active,
        "blocked_by_snake": snake_game_active,
        "blocked_reason": (
            SNAKE_ACTIVE_BLOCKED_MESSAGE
            if snake_game_active
            else (
                CATEGORY_CHANGE_BLOCKED_MESSAGE
                if custom_text_active or forced_custom_text_active
                else ""
            )
        ),
        "custom_text_blocked_reason": (
            CATEGORY_CHANGE_BLOCKED_MESSAGE
            if custom_text_active or forced_custom_text_active
            else ""
        ),
    }


def _request_action(
    action: str,
    *,
    db_path: str = DB_PATH,
    is_admin: bool = False,
    requested_at: str | None = None,
    now: datetime | None = None,
    category: str | None = None,
) -> dict:
    normalized_action = _normalize_action(action)
    definition = CONTROL_ACTIONS[normalized_action]
    current = _parse_timestamp(requested_at) if requested_at else None
    current = _now_or_default(now or current)
    timestamp = requested_at or _isoformat(current)
    requested_category = (
        _normalize_category(category) if definition["value_key"] is not None else None
    )

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        current_state = _build_action_state(
            conn, normalized_action, current=current, is_admin=is_admin
        )
        if current_state["blocked_by_snake"]:
            conn.rollback()
            return {
                **current_state,
                "accepted": False,
                "requested": False,
                "rate_limited": False,
                "error": SNAKE_ACTIVE_BLOCKED_MESSAGE,
            }

        if current_state["blocked_by_custom_text"]:
            conn.rollback()
            return {
                **current_state,
                "accepted": False,
                "requested": False,
                "rate_limited": False,
                "error": CATEGORY_CHANGE_BLOCKED_MESSAGE,
            }

        if current_state["locked"] and not is_admin:
            conn.rollback()
            return {
                **current_state,
                "accepted": False,
                "requested": False,
                "rate_limited": False,
                "error": f"{definition['label']} is locked by an admin.",
            }

        if current_state["cooldown_remaining_seconds"] > 0:
            conn.rollback()
            return {
                **current_state,
                "accepted": False,
                "requested": False,
                "rate_limited": True,
                "error": f"{definition['label']} is cooling down.",
                "retry_after_seconds": current_state["cooldown_remaining_seconds"],
            }

        request_count = current_state["request_count"] + 1
        _set_meta(conn, definition["request_key"], str(request_count))
        _set_meta(conn, definition["last_requested_key"], timestamp)
        _set_meta(conn, definition["last_accepted_key"], timestamp)
        if definition["value_key"] is not None and requested_category is not None:
            _set_meta(conn, definition["value_key"], requested_category)

        conn.commit()

        updated_state = _build_action_state(
            conn, normalized_action, current=current, is_admin=is_admin
        )
        response = {
            **updated_state,
            "accepted": True,
            "requested": True,
            "requested_at": timestamp,
            "rate_limited": False,
        }
        if requested_category is not None:
            response["category"] = requested_category
        return response
    finally:
        conn.close()


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


def get_runtime_control_state(
    db_path: str = DB_PATH,
    *,
    is_admin: bool = False,
    now: datetime | None = None,
) -> dict:
    current = _now_or_default(now)
    conn = connect(db_path)
    try:
        return {
            action: _build_action_state(
                conn, action, current=current, is_admin=is_admin
            )
            for action in CONTROL_ACTIONS
        }
    finally:
        conn.close()


def is_custom_text_force_enabled(db_path: str = DB_PATH) -> bool:
    conn = connect(db_path)
    try:
        return _get_meta_bool(conn, CUSTOM_TEXT_FORCE_KEY)
    finally:
        conn.close()


def set_custom_text_force(
    enabled: bool,
    db_path: str = DB_PATH,
) -> bool:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _set_meta(conn, CUSTOM_TEXT_FORCE_KEY, "1" if enabled else "0")
        conn.commit()
        return _get_meta_bool(conn, CUSTOM_TEXT_FORCE_KEY)
    finally:
        conn.close()


def toggle_custom_text_force(db_path: str = DB_PATH) -> bool:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        enabled = not _get_meta_bool(conn, CUSTOM_TEXT_FORCE_KEY)
        _set_meta(conn, CUSTOM_TEXT_FORCE_KEY, "1" if enabled else "0")
        conn.commit()
        return enabled
    finally:
        conn.close()


def set_control_lock(
    action: str,
    locked: bool,
    db_path: str = DB_PATH,
) -> dict:
    normalized_action = _normalize_action(action)
    definition = CONTROL_ACTIONS[normalized_action]

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _set_meta(conn, definition["lock_key"], "1" if locked else "0")
        conn.commit()
        return _build_action_state(
            conn,
            normalized_action,
            current=datetime.now(),
            is_admin=True,
        )
    finally:
        conn.close()


def request_skip_category(
    db_path: str = DB_PATH,
    requested_at: str | None = None,
    *,
    is_admin: bool = False,
    now: datetime | None = None,
) -> dict:
    return _request_action(
        "skip_category",
        db_path=db_path,
        is_admin=is_admin,
        requested_at=requested_at,
        now=now,
    )


def request_switch_category(
    category: str,
    db_path: str = DB_PATH,
    requested_at: str | None = None,
    *,
    is_admin: bool = False,
    now: datetime | None = None,
) -> dict:
    return _request_action(
        "switch_category",
        db_path=db_path,
        is_admin=is_admin,
        requested_at=requested_at,
        now=now,
        category=category,
    )


def consume_skip_category_request(db_path: str = DB_PATH) -> int | None:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        request_count = _get_meta_int(conn, SKIP_CATEGORY_REQUEST_KEY)
        handled_count = _get_meta_int(conn, SKIP_CATEGORY_HANDLED_KEY)

        if handled_count >= request_count:
            conn.rollback()
            return None

        if (
            get_active_custom_text_override_from_conn(conn, now=datetime.now())
            is not None
        ):
            _set_meta(conn, SKIP_CATEGORY_HANDLED_KEY, str(request_count))
            conn.commit()
            return None

        if (
            _get_forced_custom_text_override_from_conn(conn, now=datetime.now())
            is not None
        ):
            _set_meta(conn, SKIP_CATEGORY_HANDLED_KEY, str(request_count))
            conn.commit()
            return None

        if is_snake_mode_enabled_from_conn(conn):
            _set_meta(conn, SKIP_CATEGORY_HANDLED_KEY, str(request_count))
            conn.commit()
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

        if (
            get_active_custom_text_override_from_conn(conn, now=datetime.now())
            is not None
        ):
            _set_meta(conn, SWITCH_CATEGORY_HANDLED_KEY, str(request_count))
            conn.commit()
            return None

        if (
            _get_forced_custom_text_override_from_conn(conn, now=datetime.now())
            is not None
        ):
            _set_meta(conn, SWITCH_CATEGORY_HANDLED_KEY, str(request_count))
            conn.commit()
            return None

        if is_snake_mode_enabled_from_conn(conn):
            _set_meta(conn, SWITCH_CATEGORY_HANDLED_KEY, str(request_count))
            conn.commit()
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
