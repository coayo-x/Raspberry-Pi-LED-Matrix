import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import DB_PATH
from db_manager import connect

CUSTOM_TEXT_OVERRIDE_KEY = "custom_text_override"
CUSTOM_TEXT_REQUEST_KEY = "custom_text_request_count"
CUSTOM_TEXT_HANDLED_KEY = "custom_text_handled_count"
CUSTOM_TEXT_LAST_REQUESTED_AT_KEY = "custom_text_last_requested_at"
CUSTOM_TEXT_LAST_ACCEPTED_AT_KEY = "custom_text_last_accepted_at"
CUSTOM_TEXT_LOCKED_KEY = "custom_text_locked"

BAD_WORDS_PATH = Path(__file__).with_name("badwordslist.txt")
TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")

CUSTOM_TEXT_COOLDOWN_SECONDS = 3
MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 300
DEFAULT_DURATION_SECONDS = 300
DEFAULT_DURATION_MINUTES = DEFAULT_DURATION_SECONDS / 60
MIN_DURATION_MINUTES = MIN_DURATION_SECONDS / 60
MAX_DURATION_MINUTES = MAX_DURATION_SECONDS / 60
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 32

COLOR_PALETTE = {
    "red": {"label": "Red", "hex": "#ff3b30"},
    "green": {"label": "Green", "hex": "#34c759"},
    "blue": {"label": "Blue", "hex": "#0a84ff"},
    "yellow": {"label": "Yellow", "hex": "#ffd60a"},
    "magenta": {"label": "Magenta", "hex": "#ff2d55"},
    "cyan": {"label": "Cyan", "hex": "#64d2ff"},
    "white": {"label": "White", "hex": "#f5f7fa"},
    "black": {"label": "Black", "hex": "#000000"},
    "orange": {"label": "Orange", "hex": "#ff9f0a"},
    "purple": {"label": "Purple", "hex": "#bf5af2"},
}
ALLOWED_FONT_FAMILIES = {"sans", "serif", "mono"}
ALLOWED_ALIGNMENTS = {"left", "center", "right", "justify"}

DEFAULT_STYLE = {
    "bold": False,
    "italic": False,
    "underline": False,
    "font_family": "sans",
    "font_size": 16,
    "text_color": "white",
    "background_color": "black",
    "alignment": "center",
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


def _round_minutes(value: float) -> float:
    return round(value + 1e-9, 2)


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


def _normalize_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in {0, 1}:
        return bool(value)
    raise ValueError(f"'{field_name}' must be a boolean.")


def _normalize_font_family(value: Any) -> str:
    if value in {None, ""}:
        return DEFAULT_STYLE["font_family"]

    normalized = str(value).strip().lower()
    if normalized not in ALLOWED_FONT_FAMILIES:
        raise ValueError(
            f"'font_family' must be one of: {', '.join(sorted(ALLOWED_FONT_FAMILIES))}."
        )
    return normalized


def _normalize_alignment(value: Any) -> str:
    if value in {None, ""}:
        return DEFAULT_STYLE["alignment"]

    normalized = str(value).strip().lower()
    if normalized not in ALLOWED_ALIGNMENTS:
        raise ValueError(
            f"'alignment' must be one of: {', '.join(sorted(ALLOWED_ALIGNMENTS))}."
        )
    return normalized


def _normalize_font_size(value: Any) -> int:
    if value in {None, ""}:
        return DEFAULT_STYLE["font_size"]

    try:
        font_size = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("'font_size' must be an integer.") from error

    if font_size < MIN_FONT_SIZE or font_size > MAX_FONT_SIZE:
        raise ValueError(
            f"'font_size' must be between {MIN_FONT_SIZE} and {MAX_FONT_SIZE}."
        )
    return font_size


def _normalize_color(value: Any, field_name: str, default: str) -> str:
    if value in {None, ""}:
        return default

    normalized = str(value).strip().lower()
    if normalized not in COLOR_PALETTE:
        raise ValueError(
            f"'{field_name}' must be one of: {', '.join(COLOR_PALETTE.keys())}."
        )
    return normalized


def _normalize_duration_minutes(value: Any) -> tuple[int, float]:
    if value in {None, ""}:
        return DEFAULT_DURATION_SECONDS, _round_minutes(DEFAULT_DURATION_MINUTES)

    try:
        duration_minutes = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("'duration_minutes' must be a number.") from error

    if math.isnan(duration_minutes) or math.isinf(duration_minutes):
        raise ValueError("'duration_minutes' must be a finite number.")

    duration_seconds = int(round(duration_minutes * 60))
    if (
        duration_seconds < MIN_DURATION_SECONDS
        or duration_seconds > MAX_DURATION_SECONDS
    ):
        raise ValueError(
            f"'duration_minutes' must be between {_round_minutes(MIN_DURATION_MINUTES)} and {_round_minutes(MAX_DURATION_MINUTES)} minutes."
        )

    return duration_seconds, _round_minutes(duration_seconds / 60)


def _normalize_stored_duration(override: dict) -> tuple[int, float]:
    if override.get("duration_minutes") not in {None, ""}:
        return _normalize_duration_minutes(override.get("duration_minutes"))

    if override.get("duration_seconds") not in {None, ""}:
        try:
            duration_seconds = int(override.get("duration_seconds"))
        except (TypeError, ValueError) as error:
            raise ValueError("'duration_seconds' must be an integer.") from error

        if (
            duration_seconds < MIN_DURATION_SECONDS
            or duration_seconds > MAX_DURATION_SECONDS
        ):
            raise ValueError(
                f"'duration_seconds' must be between {MIN_DURATION_SECONDS} and {MAX_DURATION_SECONDS} seconds."
            )

        return duration_seconds, _round_minutes(duration_seconds / 60)

    return DEFAULT_DURATION_SECONDS, _round_minutes(DEFAULT_DURATION_MINUTES)


def normalize_custom_text_style(style: dict | None) -> dict:
    active_style = style or {}
    if not isinstance(active_style, dict):
        raise ValueError("'style' must be an object.")

    return {
        "bold": _normalize_bool(
            active_style.get("bold", DEFAULT_STYLE["bold"]), "bold"
        ),
        "italic": _normalize_bool(
            active_style.get("italic", DEFAULT_STYLE["italic"]), "italic"
        ),
        "underline": _normalize_bool(
            active_style.get("underline", DEFAULT_STYLE["underline"]), "underline"
        ),
        "font_family": _normalize_font_family(
            active_style.get("font_family", DEFAULT_STYLE["font_family"])
        ),
        "font_size": _normalize_font_size(
            active_style.get("font_size", DEFAULT_STYLE["font_size"])
        ),
        "text_color": _normalize_color(
            active_style.get("text_color"),
            "text_color",
            DEFAULT_STYLE["text_color"],
        ),
        "background_color": _normalize_color(
            active_style.get("background_color"),
            "background_color",
            DEFAULT_STYLE["background_color"],
        ),
        "alignment": _normalize_alignment(
            active_style.get("alignment", DEFAULT_STYLE["alignment"])
        ),
    }


def normalize_custom_text_text(text: Any) -> str:
    normalized = " ".join(str(text or "").strip().split())
    if not normalized:
        raise ValueError("'text' is required.")
    return normalized


def load_bad_words(path: Path | None = None) -> set[str]:
    source = path or BAD_WORDS_PATH
    if not source.exists():
        raise FileNotFoundError(f"{source.name} is missing.")

    words: set[str] = set()
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        normalized = " ".join(raw_line.strip().lower().split())
        if not normalized or normalized.startswith("#"):
            continue
        if normalized.startswith("create a new file "):
            continue
        words.add(normalized)

    if not words:
        raise ValueError(f"{source.name} is empty.")

    return words


def find_banned_words(text: str, bad_words: set[str]) -> list[str]:
    normalized_text = " ".join(str(text).strip().lower().split())
    if not normalized_text:
        return []

    tokens = {token for token in TOKEN_SPLIT_RE.split(normalized_text) if token}
    found: set[str] = set()
    for banned_word in bad_words:
        if " " in banned_word:
            if banned_word in normalized_text:
                found.add(banned_word)
            continue

        if banned_word in tokens:
            found.add(banned_word)

    return sorted(found)


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

    remaining = cooldown_seconds - (current - accepted_at).total_seconds()
    if remaining <= 0:
        return 0
    return max(1, math.ceil(remaining))


def _build_override_state(override: dict, *, current: datetime) -> dict:
    duration_seconds, duration_minutes = _normalize_stored_duration(override)
    started_at_text = str(override.get("started_at") or "")
    expires_at_text = str(override.get("expires_at") or "")
    started_at = _parse_timestamp(started_at_text)
    expires_at = _parse_timestamp(expires_at_text)
    if started_at is not None and expires_at is None:
        expires_at = started_at + timedelta(seconds=duration_seconds)
        expires_at_text = _isoformat(expires_at)

    remaining_seconds = 0
    active = False
    if expires_at is not None:
        remaining_seconds = max(0, math.ceil((expires_at - current).total_seconds()))
        active = remaining_seconds > 0

    style = normalize_custom_text_style(override.get("style") or {})
    return {
        "request_id": str(override.get("request_id") or ""),
        "text": normalize_custom_text_text(override.get("text", "")),
        "style": style,
        "duration_seconds": duration_seconds,
        "duration_minutes": duration_minutes,
        "started_at": started_at_text,
        "expires_at": expires_at_text,
        "active": active,
        "remaining_seconds": remaining_seconds,
        "text_color_hex": COLOR_PALETTE[style["text_color"]]["hex"],
        "background_color_hex": COLOR_PALETTE[style["background_color"]]["hex"],
    }


def _load_override_from_conn(conn, *, current: datetime) -> dict | None:
    raw_value = _get_meta_text(conn, CUSTOM_TEXT_OVERRIDE_KEY)
    if not raw_value:
        return None

    try:
        override = json.loads(raw_value)
    except json.JSONDecodeError:
        return None

    if not isinstance(override, dict):
        return None

    try:
        return _build_override_state(override, current=current)
    except ValueError:
        return None


def _build_custom_text_state(conn, *, current: datetime, is_admin: bool) -> dict:
    request_count = _get_meta_int(conn, CUSTOM_TEXT_REQUEST_KEY)
    handled_count = _get_meta_int(conn, CUSTOM_TEXT_HANDLED_KEY)
    locked = _get_meta_bool(conn, CUSTOM_TEXT_LOCKED_KEY)
    cooldown_remaining = _cooldown_remaining_seconds(
        _get_meta_text(conn, CUSTOM_TEXT_LAST_ACCEPTED_AT_KEY),
        CUSTOM_TEXT_COOLDOWN_SECONDS,
        current,
    )
    override = _load_override_from_conn(conn, current=current)
    admin_override = bool(locked and is_admin)
    is_blocked = cooldown_remaining > 0 or (locked and not is_admin)

    if locked and not is_admin:
        status = "locked"
    elif cooldown_remaining > 0:
        status = "cooldown"
    else:
        status = "ready"

    return {
        "action": "custom_text",
        "label": "Custom Text",
        "locked": locked,
        "action_locked": locked,
        "admin_override": admin_override,
        "cooldown_seconds": CUSTOM_TEXT_COOLDOWN_SECONDS,
        "cooldown_remaining_seconds": cooldown_remaining,
        "request_count": request_count,
        "handled_count": handled_count,
        "pending_request_count": max(0, request_count - handled_count),
        "last_requested_at": _get_meta_text(conn, CUSTOM_TEXT_LAST_REQUESTED_AT_KEY)
        or "",
        "last_accepted_at": _get_meta_text(conn, CUSTOM_TEXT_LAST_ACCEPTED_AT_KEY)
        or "",
        "available": not is_blocked,
        "status": status,
        "active_override": bool(override and override["active"]),
        "override_expires_at": override["expires_at"] if override else "",
        "override_remaining_seconds": override["remaining_seconds"] if override else 0,
        "override_text": override["text"] if override else "",
        "override": override,
    }


def get_custom_text_control_state(
    db_path: str = DB_PATH,
    *,
    is_admin: bool = False,
    now: datetime | None = None,
) -> dict:
    current = _now_or_default(now)
    conn = connect(db_path)
    try:
        return _build_custom_text_state(conn, current=current, is_admin=is_admin)
    finally:
        conn.close()


def get_custom_text_override(
    db_path: str = DB_PATH,
    *,
    now: datetime | None = None,
) -> dict | None:
    current = _now_or_default(now)
    conn = connect(db_path)
    try:
        return _load_override_from_conn(conn, current=current)
    finally:
        conn.close()


def get_active_custom_text_override(
    db_path: str = DB_PATH,
    *,
    now: datetime | None = None,
) -> dict | None:
    override = get_custom_text_override(db_path=db_path, now=now)
    if override is None or not override["active"]:
        return None
    return override


def get_custom_text_interrupt_token(
    db_path: str = DB_PATH,
    *,
    now: datetime | None = None,
) -> str | None:
    override = get_active_custom_text_override(db_path=db_path, now=now)
    if override is None:
        return None
    return override["request_id"]


def get_custom_text_remaining_seconds(
    override: dict | None,
    *,
    now: datetime | None = None,
) -> int:
    if override is None:
        return 0

    if "remaining_seconds" in override:
        try:
            return max(0, int(override["remaining_seconds"]))
        except (TypeError, ValueError):
            return 0

    current = _now_or_default(now)
    expires_at = _parse_timestamp(str(override.get("expires_at") or ""))
    if expires_at is None:
        return 0
    return max(0, math.ceil((expires_at - current).total_seconds()))


def set_custom_text_lock(
    locked: bool,
    db_path: str = DB_PATH,
) -> dict:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _set_meta(conn, CUSTOM_TEXT_LOCKED_KEY, "1" if locked else "0")
        conn.commit()
        return _build_custom_text_state(
            conn,
            current=datetime.now(),
            is_admin=True,
        )
    finally:
        conn.close()


def request_custom_text_override(
    text: Any,
    *,
    duration_minutes: Any = None,
    style: dict | None = None,
    db_path: str = DB_PATH,
    requested_at: str | None = None,
    is_admin: bool = False,
    now: datetime | None = None,
) -> dict:
    current = _parse_timestamp(requested_at) if requested_at else None
    current = _now_or_default(now or current)
    timestamp = requested_at or _isoformat(current)

    normalized_text = normalize_custom_text_text(text)
    duration_seconds, normalized_minutes = _normalize_duration_minutes(duration_minutes)
    normalized_style = normalize_custom_text_style(style)

    try:
        bad_words = load_bad_words()
    except FileNotFoundError as error:
        raise ValueError(
            "Custom text moderation is unavailable because badwordslist.txt is missing."
        ) from error
    except ValueError as error:
        raise ValueError(
            "Custom text moderation is unavailable because badwordslist.txt is empty."
        ) from error

    banned_words = find_banned_words(normalized_text, bad_words)
    if banned_words:
        raise ValueError("Custom text contains blocked words and was rejected.")

    override = {
        "request_id": uuid4().hex,
        "text": normalized_text,
        "style": normalized_style,
        "duration_seconds": duration_seconds,
        "duration_minutes": normalized_minutes,
        "started_at": timestamp,
        "expires_at": _isoformat(current + timedelta(seconds=duration_seconds)),
    }

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        current_state = _build_custom_text_state(
            conn, current=current, is_admin=is_admin
        )
        if current_state["locked"] and not is_admin:
            conn.rollback()
            return {
                **current_state,
                "accepted": False,
                "requested": False,
                "rate_limited": False,
                "error": "Custom text is currently locked by admin.",
            }

        if current_state["cooldown_remaining_seconds"] > 0:
            conn.rollback()
            return {
                **current_state,
                "accepted": False,
                "requested": False,
                "rate_limited": True,
                "error": "Custom Text is cooling down.",
                "retry_after_seconds": current_state["cooldown_remaining_seconds"],
            }

        request_count = current_state["request_count"] + 1
        _set_meta(conn, CUSTOM_TEXT_REQUEST_KEY, str(request_count))
        _set_meta(conn, CUSTOM_TEXT_HANDLED_KEY, str(request_count))
        _set_meta(conn, CUSTOM_TEXT_LAST_REQUESTED_AT_KEY, timestamp)
        _set_meta(conn, CUSTOM_TEXT_LAST_ACCEPTED_AT_KEY, timestamp)
        _set_meta(conn, CUSTOM_TEXT_OVERRIDE_KEY, json.dumps(override, sort_keys=True))
        conn.commit()

        updated_state = _build_custom_text_state(
            conn, current=current, is_admin=is_admin
        )
        return {
            **updated_state,
            "accepted": True,
            "requested": True,
            "requested_at": timestamp,
            "rate_limited": False,
            "override": updated_state["override"],
        }
    finally:
        conn.close()
