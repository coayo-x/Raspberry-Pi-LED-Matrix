import json
from datetime import datetime

from config import DB_PATH
from db_manager import connect

DISPLAY_STATE_VERSION = 1


def empty_current_display_state() -> dict:
    return {
        "snapshot_version": DISPLAY_STATE_VERSION,
        "has_data": False,
        "updated_at": "",
        "time": "",
        "slot": "",
        "category": "",
        "setup": "",
        "punchline": "",
        "data": {},
    }


def _stringify(value) -> str:
    if value is None:
        return "--"
    return str(value)


def _join_parts(*parts: str) -> str:
    return " | ".join(part for part in parts if part)


def _normalize_dashboard_fields(category: str, data: dict) -> tuple[str, str]:
    if category == "pokemon":
        types = data.get("types") or []
        type_text = " / ".join(str(value) for value in types if value) or "Unknown"
        return (
            str(data.get("name", "Pokemon unavailable")),
            _join_parts(
                type_text,
                f"HP {_stringify(data.get('hp'))}",
                f"ATK {_stringify(data.get('attack'))}",
                f"DEF {_stringify(data.get('defense'))}",
            ),
        )

    if category == "weather":
        return (
            str(data.get("location", "Unknown location")),
            _join_parts(
                str(data.get("condition", "Unknown")),
                f"{_stringify(data.get('temperature_f'))}F",
                f"Wind {_stringify(data.get('wind_mph'))} mph",
            ),
        )

    if category == "joke":
        if data.get("type") == "twopart":
            return (
                str(data.get("setup") or ""),
                str(data.get("delivery") or ""),
            )
        return (
            str(data.get("text") or ""),
            "",
        )

    if category == "science":
        symbol = str(data.get("symbol", "?"))
        atomic_number = _stringify(data.get("atomic_number"))
        return (
            f"{data.get('name', 'Unknown')} ({symbol})",
            f"Atomic {atomic_number}",
        )

    if category == "custom_text":
        style = data.get("style") or {}
        style_flags = [
            label
            for enabled, label in (
                (style.get("bold"), "Bold"),
                (style.get("italic"), "Italic"),
                (style.get("underline"), "Underline"),
            )
            if enabled
        ]
        duration_minutes = data.get("duration_minutes")
        if duration_minutes in {None, ""}:
            duration_summary = f"{_stringify(data.get('duration_seconds'))}s"
        else:
            duration_summary = f"{_stringify(duration_minutes)}m"

        style_summary = _join_parts(
            f"{style.get('font_family', 'sans')} {style.get('font_size', '--')}px",
            str(style.get("alignment", "center")).title(),
            "/".join(style_flags) if style_flags else "Plain",
            f"{style.get('text_color', 'white')} on {style.get('background_color', 'black')}",
            duration_summary,
        )
        return (
            str(data.get("text") or ""),
            style_summary,
        )

    if category == "snake_game":
        state = str(data.get("state") or "idle").replace("_", " ").title()
        score = _stringify(data.get("score", 0))
        summary = str(data.get("summary") or state)
        return (
            "Snake Game Mode",
            _join_parts(summary, f"Score {score}"),
        )

    return ("", "")


def normalize_current_display_state(
    payload: dict, updated_at: str | None = None
) -> dict:
    category = str(payload.get("category", ""))
    data = payload.get("data") or {}
    snapshot_time = updated_at or datetime.now().isoformat(timespec="seconds")
    setup, punchline = _normalize_dashboard_fields(category, data)

    return {
        "snapshot_version": DISPLAY_STATE_VERSION,
        "has_data": True,
        "updated_at": snapshot_time,
        "time": str(payload.get("time", "")),
        "slot": str(payload.get("slot_key", "")),
        "category": category,
        "setup": setup,
        "punchline": punchline,
        "data": data,
    }


def save_current_display_state(
    payload: dict, db_path: str = DB_PATH, updated_at: str | None = None
) -> dict:
    state = normalize_current_display_state(payload, updated_at=updated_at)
    serialized_state = json.dumps(state, sort_keys=True)

    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO current_display_state (id, state_json, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE
            SET state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (serialized_state, state["updated_at"]),
        )
        conn.commit()
        return state
    finally:
        conn.close()


def load_current_display_state(db_path: str = DB_PATH) -> dict:
    conn = connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT state_json FROM current_display_state WHERE id = 1")
        row = cur.fetchone()
        if row is None or not row["state_json"]:
            return empty_current_display_state()

        state = json.loads(row["state_json"])
        empty_state = empty_current_display_state()
        empty_state.update(state)
        empty_state["has_data"] = bool(state.get("has_data"))
        return empty_state
    finally:
        conn.close()
