import math
from datetime import datetime

from config import (
    DB_PATH,
    SKIP_CATEGORY_COOLDOWN_SECONDS,
    SWITCH_CATEGORY_COOLDOWN_SECONDS,
)
from db_manager import connect
from rotation_engine import DISPLAY_SEQUENCE

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

ALIEN_MODE_ACTIVE_KEY = "alien_mode_active"
ALIEN_MODE_UPDATED_AT_KEY = "alien_mode_updated_at"

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
    locked = _get_meta_bool(conn, definition["lock_key"])
    cooldown_remaining = _cooldown_remaining_seconds(
        _get_meta_text(conn, definition["last_accepted_key"]),
        definition["cooldown_seconds"],
        current,
    )
    requested_category = None
    if definition["value_key"] is not None:
        requested_category = _get_meta_text(conn, definition["value_key"])

    is_blocked = cooldown_remaining > 0 or (locked and not is_admin)
    if locked and not is_admin:
        status = "locked"
    elif cooldown_remaining > 0:
        status = "cooldown"
    else:
        status = "ready"

    return {
        "action": normalized_action,
        "label": definition["label"],
        "locked": locked,
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
    }


def _build_alien_mode_state(conn) -> dict:
    active = _get_meta_bool(conn, ALIEN_MODE_ACTIVE_KEY)
    updated_at = _get_meta_text(conn, ALIEN_MODE_UPDATED_AT_KEY) or ""
    return {
        "action": "alien_mode",
        "label": "Alien Dance",
        "locked": False,
        "admin_override": False,
        "cooldown_seconds": 0,
        "cooldown_remaining_seconds": 0,
        "request_count": 0,
        "handled_count": 0,
        "pending_request_count": 0,
        "last_requested_at": updated_at,
        "last_accepted_at": updated_at,
        "available": True,
        "status": "active" if active else "inactive",
        "active": active,
        "updated_at": updated_at,
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
        controls = {
            action: _build_action_state(
                conn, action, current=current, is_admin=is_admin
            )
            for action in CONTROL_ACTIONS
        }
        controls["alien_mode"] = _build_alien_mode_state(conn)
        return controls
    finally:
        conn.close()


def get_alien_mode_state(db_path: str = DB_PATH) -> dict:
    conn = connect(db_path)
    try:
        return _build_alien_mode_state(conn)
    finally:
        conn.close()


def set_alien_mode(
    active: bool,
    db_path: str = DB_PATH,
    updated_at: str | None = None,
) -> dict:
    current = _parse_timestamp(updated_at) if updated_at else None
    timestamp = updated_at or _isoformat(_now_or_default(current))

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _set_meta(conn, ALIEN_MODE_ACTIVE_KEY, "1" if active else "0")
        _set_meta(conn, ALIEN_MODE_UPDATED_AT_KEY, timestamp)
        conn.commit()
        return _build_alien_mode_state(conn)
    finally:
        conn.close()


def start_alien_mode(
    db_path: str = DB_PATH,
    updated_at: str | None = None,
) -> dict:
    return set_alien_mode(True, db_path=db_path, updated_at=updated_at)


def stop_alien_mode(
    db_path: str = DB_PATH,
    updated_at: str | None = None,
) -> dict:
    return set_alien_mode(False, db_path=db_path, updated_at=updated_at)


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
