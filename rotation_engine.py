import hashlib
import random
from datetime import datetime
from typing import Iterable

from db_manager import connect
from apis.jokes import get_random_joke
from apis.pokemon import FALLBACK_POKEMON_IDS, get_valid_pokemon_ids
from apis.science import get_random_science_fact, get_science_fact_fallback

DISPLAY_SEQUENCE = ["pokemon", "weather", "joke", "science"]
SLOT_MINUTES = 5


def _now_or_default(now: datetime | None = None) -> datetime:
    return now or datetime.now()


def get_current_slot_number(now: datetime | None = None) -> int:
    current = _now_or_default(now)
    return ((current.hour * 60) + current.minute) // SLOT_MINUTES


def get_current_slot_key(now: datetime | None = None) -> str:
    current = _now_or_default(now)
    return f"{current.date().isoformat()}:{get_current_slot_number(current)}"


def get_current_category(now: datetime | None = None) -> str:
    return DISPLAY_SEQUENCE[get_current_slot_number(now) % len(DISPLAY_SEQUENCE)]


def seconds_until_next_slot(now: datetime | None = None) -> int:
    current = _now_or_default(now)
    seconds_today = (current.hour * 3600) + (current.minute * 60) + current.second
    slot_seconds = SLOT_MINUTES * 60
    next_boundary = ((seconds_today // slot_seconds) + 1) * slot_seconds
    remaining = next_boundary - seconds_today
    return max(1, remaining)


def _get_meta(conn, key: str) -> str | None:
    cur = conn.cursor()
    cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
    row = cur.fetchone()
    return row["value"] if row else None


def _set_meta(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _get_system_state(conn):
    cur = conn.cursor()
    cur.execute("SELECT * FROM system_state WHERE id = 1")
    return cur.fetchone()


def _catalog_hash(values: Iterable[int]) -> str:
    joined = ",".join(str(v) for v in values)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _shuffle_copy(values: list[int], avoid_first: int | None = None) -> list[int]:
    shuffled = values[:]
    for _ in range(20):
        random.shuffle(shuffled)
        if avoid_first is None or not shuffled or shuffled[0] != avoid_first:
            break
    return shuffled


def _pokemon_table_count(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM pokemon_rotation")
    return cur.fetchone()["c"]


def _get_all_pokemon_ids(conn) -> list[int]:
    cur = conn.cursor()
    cur.execute("SELECT pokemon_id FROM pokemon_rotation ORDER BY position ASC")
    return [row["pokemon_id"] for row in cur.fetchall()]


def _get_pokemon_at_pos(conn, pos: int) -> int:
    cur = conn.cursor()
    cur.execute("SELECT pokemon_id FROM pokemon_rotation WHERE position = ?", (pos,))
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Missing Pokémon at position {pos}")
    return row["pokemon_id"]


def _replace_pokemon_rotation(conn, pokemon_ids: list[int]) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM pokemon_rotation")
    for position, pokemon_id in enumerate(pokemon_ids):
        cur.execute(
            "INSERT INTO pokemon_rotation (position, pokemon_id) VALUES (?, ?)",
            (position, pokemon_id),
        )


def _reset_pokemon_state(conn) -> None:
    conn.execute(
        """
        UPDATE system_state
        SET pokemon_pos = 0,
            pokemon_date = NULL,
            current_pokemon_id = NULL
        WHERE id = 1
        """
    )


def _ensure_pokemon_rotation(conn) -> list[int]:
    try:
        pokemon_ids = get_valid_pokemon_ids()
    except Exception:
        pokemon_ids = []

    if not pokemon_ids:
        existing_ids = _get_all_pokemon_ids(conn)
        pokemon_ids = existing_ids or FALLBACK_POKEMON_IDS

    pokemon_ids = sorted(set(pokemon_ids))
    new_hash = _catalog_hash(pokemon_ids)

    stored_hash = _get_meta(conn, "pokemon_catalog_hash")
    stored_count = _pokemon_table_count(conn)

    if stored_hash != new_hash or stored_count != len(pokemon_ids):
        shuffled_ids = _shuffle_copy(pokemon_ids)
        _replace_pokemon_rotation(conn, shuffled_ids)
        _set_meta(conn, "pokemon_catalog_hash", new_hash)
        _set_meta(conn, "pokemon_catalog_size", str(len(pokemon_ids)))
        _reset_pokemon_state(conn)

    return pokemon_ids


def _advance_pokemon_cycle(conn, current_pokemon_id: int) -> None:
    current_ids = _get_all_pokemon_ids(conn)
    reshuffled = _shuffle_copy(current_ids, avoid_first=current_pokemon_id)
    _replace_pokemon_rotation(conn, reshuffled)


def get_today_pokemon_id(today: str | None = None, db_path: str = "content.db") -> int:
    today = today or datetime.now().date().isoformat()

    conn = connect(db_path)
    try:
        _ensure_pokemon_rotation(conn)
        row = _get_system_state(conn)

        if row["pokemon_date"] == today and row["current_pokemon_id"] is not None:
            return row["current_pokemon_id"]

        total_rows = _pokemon_table_count(conn)
        if total_rows == 0:
            raise RuntimeError("pokemon_rotation is empty")

        pokemon_pos = row["pokemon_pos"]
        if pokemon_pos >= total_rows:
            pokemon_pos = 0

        pokemon_id = _get_pokemon_at_pos(conn, pokemon_pos)

        if pokemon_pos >= total_rows - 1:
            _advance_pokemon_cycle(conn, pokemon_id)
            next_pokemon_pos = 0
        else:
            next_pokemon_pos = pokemon_pos + 1

        conn.execute(
            """
            UPDATE system_state
            SET pokemon_date = ?,
                current_pokemon_id = ?,
                pokemon_pos = ?
            WHERE id = 1
            """,
            (today, pokemon_id, next_pokemon_pos),
        )
        conn.commit()
        return pokemon_id
    finally:
        conn.close()


def _joke_exists(conn, joke_key: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM used_jokes WHERE joke_key = ?", (joke_key,))
    return cur.fetchone() is not None


def _store_used_joke(conn, joke: dict, seen_at: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO used_jokes (
            joke_key, joke_type, joke_text, joke_setup, joke_delivery, first_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            joke["key"],
            joke["type"],
            joke.get("text"),
            joke.get("setup"),
            joke.get("delivery"),
            seen_at,
        ),
    )


def _fallback_joke(slot_key: str) -> dict:
    return {
        "key": f"fallback:{slot_key}",
        "type": "single",
        "text": "Backup joke: the API ghosted us, but the Pi is still pretending to be a comedian.",
        "setup": None,
        "delivery": None,
    }


def get_current_joke(now: datetime | None = None, db_path: str = "content.db") -> dict:
    current = _now_or_default(now)
    slot_key = get_current_slot_key(current)
    timestamp = current.isoformat(timespec="seconds")

    conn = connect(db_path)
    try:
        row = _get_system_state(conn)

        if row["current_joke_slot"] == slot_key and row["current_joke_id"]:
            return {
                "key": row["current_joke_id"],
                "type": row["current_joke_type"] or "single",
                "text": row["current_joke_text"],
                "setup": row["current_joke_setup"],
                "delivery": row["current_joke_delivery"],
            }

        joke = None
        for _ in range(10):
            try:
                candidate = get_random_joke()
            except Exception:
                continue

            if not _joke_exists(conn, candidate["key"]):
                joke = candidate
                break

        if joke is None:
            joke = _fallback_joke(slot_key)

        _store_used_joke(conn, joke, timestamp)
        conn.execute(
            """
            UPDATE system_state
            SET current_joke_slot = ?,
                current_joke_id = ?,
                current_joke_type = ?,
                current_joke_text = ?,
                current_joke_setup = ?,
                current_joke_delivery = ?
            WHERE id = 1
            """,
            (
                slot_key,
                joke["key"],
                joke["type"],
                joke.get("text"),
                joke.get("setup"),
                joke.get("delivery"),
            ),
        )
        conn.commit()
        return joke
    finally:
        conn.close()


def get_current_science_fact(now: datetime | None = None, db_path: str = "content.db") -> dict:
    current = _now_or_default(now)
    slot_key = get_current_slot_key(current)

    conn = connect(db_path)
    try:
        row = _get_system_state(conn)

        if row["current_science_slot"] == slot_key and row["current_science_key"]:
            return {
                "key": row["current_science_key"],
                "text": row["current_science_text"],
                "name": row["current_science_name"],
                "symbol": row["current_science_symbol"],
                "atomic_number": row["current_science_atomic_number"],
                "category": "element",
            }

        try:
            fact = get_random_science_fact()
        except Exception:
            fact = get_science_fact_fallback()

        conn.execute(
            """
            UPDATE system_state
            SET current_science_slot = ?,
                current_science_key = ?,
                current_science_text = ?,
                current_science_name = ?,
                current_science_symbol = ?,
                current_science_atomic_number = ?
            WHERE id = 1
            """,
            (
                slot_key,
                fact.get("key"),
                fact.get("text"),
                fact.get("name"),
                fact.get("symbol"),
                fact.get("atomic_number"),
            ),
        )
        conn.commit()


        
i don't like this!
