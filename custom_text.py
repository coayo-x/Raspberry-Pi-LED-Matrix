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
BAD_WORDS_PATH = Path(__file__).with_name("badwordslist.txt")

MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 300
DEFAULT_DURATION_SECONDS = 300
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 32

DEFAULT_STYLE = {
    "bold": False,
    "italic": False,
    "underline": False,
    "font_family": "sans",
    "font_size": 16,
    "text_color": "#eef5fb",
    "background_color": "#08111b",
    "alignment": "center",
}

ALLOWED_FONT_FAMILIES = {"sans", "serif", "mono"}
ALLOWED_ALIGNMENTS = {"left", "center", "right", "justify"}
HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")
TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


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


def _normalize_duration(value: Any) -> int:
    if value in {None, ""}:
        return DEFAULT_DURATION_SECONDS

    try:
        duration_seconds = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("'duration_seconds' must be an integer.") from error

    if (
        duration_seconds < MIN_DURATION_SECONDS
        or duration_seconds > MAX_DURATION_SECONDS
    ):
        raise ValueError(
            f"'duration_seconds' must be between {MIN_DURATION_SECONDS} and {MAX_DURATION_SECONDS} seconds."
        )
    return duration_seconds


def _normalize_color(value: Any, field_name: str, default: str) -> str:
    if value in {None, ""}:
        return default

    normalized = str(value).strip()
    if not HEX_COLOR_RE.fullmatch(normalized):
        raise ValueError(f"'{field_name}' must be a hex color like '#112233'.")

    if not normalized.startswith("#"):
        normalized = f"#{normalized}"
    return normalized.lower()


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
        return set()

    words: set[str] = set()
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        normalized = " ".join(raw_line.strip().lower().split())
        if not normalized or normalized.startswith("#"):
            continue
        words.add(normalized)
    return words


def find_banned_words(text: str, bad_words: set[str] | None = None) -> list[str]:
    normalized_text = " ".join(str(text).strip().lower().split())
    if not normalized_text:
        return []

    active_bad_words = bad_words if bad_words is not None else load_bad_words()
    if not active_bad_words:
        return []

    tokens = {token for token in TOKEN_SPLIT_RE.split(normalized_text) if token}
    found: set[str] = set()
    for banned_word in active_bad_words:
        if " " in banned_word:
            if banned_word in normalized_text:
                found.add(banned_word)
            continue

        if banned_word in tokens:
            found.add(banned_word)

    return sorted(found)


def _build_override_state(override: dict, *, current: datetime) -> dict:
    duration_seconds = _normalize_duration(override.get("duration_seconds"))
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

    return {
        "request_id": str(override.get("request_id") or ""),
        "text": normalize_custom_text_text(override.get("text", "")),
        "style": normalize_custom_text_style(override.get("style") or {}),
        "duration_seconds": duration_seconds,
        "started_at": started_at_text,
        "expires_at": expires_at_text,
        "active": active,
        "remaining_seconds": remaining_seconds,
    }


def get_custom_text_override(
    db_path: str = DB_PATH,
    *,
    now: datetime | None = None,
) -> dict | None:
    current = _now_or_default(now)
    conn = connect(db_path)
    try:
        raw_value = _get_meta_text(conn, CUSTOM_TEXT_OVERRIDE_KEY)
    finally:
        conn.close()

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


def request_custom_text_override(
    text: Any,
    *,
    duration_seconds: Any = None,
    style: dict | None = None,
    db_path: str = DB_PATH,
    requested_at: str | None = None,
    now: datetime | None = None,
) -> dict:
    current = _parse_timestamp(requested_at) if requested_at else None
    current = _now_or_default(now or current)
    normalized_text = normalize_custom_text_text(text)

    banned_words = find_banned_words(normalized_text)
    if banned_words:
        raise ValueError("Custom text contains banned words and was rejected.")

    normalized_style = normalize_custom_text_style(style)
    normalized_duration = _normalize_duration(duration_seconds)
    started_at = _isoformat(current)
    expires_at = _isoformat(current + timedelta(seconds=normalized_duration))
    override = {
        "request_id": uuid4().hex,
        "text": normalized_text,
        "style": normalized_style,
        "duration_seconds": normalized_duration,
        "started_at": started_at,
        "expires_at": expires_at,
    }

    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _set_meta(conn, CUSTOM_TEXT_OVERRIDE_KEY, json.dumps(override, sort_keys=True))
        conn.commit()
    finally:
        conn.close()

    return _build_override_state(override, current=current)
