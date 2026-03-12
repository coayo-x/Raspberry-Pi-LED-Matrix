import random
from datetime import date

from db_manager import connect
from apis.pokemon import get_total_pokemon

CATEGORIES = ["pokemon", "weather", "joke"]


def _get_system_state(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT
            last_date,
            category_pos,
            pokemon_pos,
            pokemon_date,
            current_pokemon_id
        FROM system_state
        WHERE id = 1
    """)
    return cur.fetchone()


def _set_system_state_category(conn, last_date: str, category_pos: int) -> None:
    cur = conn.cursor()
    cur.execute("""
        UPDATE system_state
        SET last_date = ?, category_pos = ?
        WHERE id = 1
    """, (last_date, category_pos))


def _set_system_state_pokemon(conn, pokemon_date: str, current_pokemon_id: int, pokemon_pos: int) -> None:
    cur = conn.cursor()
    cur.execute("""
        UPDATE system_state
        SET pokemon_date = ?, current_pokemon_id = ?, pokemon_pos = ?
        WHERE id = 1
    """, (pokemon_date, current_pokemon_id, pokemon_pos))


# -----------------------------
# Category rotation
# -----------------------------

def _category_table_count(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM category_rotation")
    return cur.fetchone()["c"]


def _get_category_at_pos(conn, pos: int) -> str:
    cur = conn.cursor()
    cur.execute("SELECT category FROM category_rotation WHERE position = ?", (pos,))
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Missing category at position {pos}")
    return row["category"]


def _seed_categories_if_empty(conn) -> None:
    if _category_table_count(conn) > 0:
        return

    order = CATEGORIES[:]
    random.shuffle(order)

    cur = conn.cursor()
    for i, category in enumerate(order):
        cur.execute("""
            INSERT INTO category_rotation (position, category)
            VALUES (?, ?)
        """, (i, category))


def _reshuffle_categories(conn, avoid_first=None) -> None:
    order = CATEGORIES[:]

    for _ in range(20):
        random.shuffle(order)
        if avoid_first is None or order[0] != avoid_first:
            break

    cur = conn.cursor()
    cur.execute("DELETE FROM category_rotation")

    for i, category in enumerate(order):
        cur.execute("""
            INSERT INTO category_rotation (position, category)
            VALUES (?, ?)
        """, (i, category))


def get_today_category(db_path="content.db") -> str:
    today = date.today().isoformat()

    conn = connect(db_path)
    try:
        _seed_categories_if_empty(conn)
        row = _get_system_state(conn)

        last_date = row["last_date"]
        category_pos = row["category_pos"]

        # First run ever
        if last_date is None:
            _set_system_state_category(conn, today, 0)
            conn.commit()
            return _get_category_at_pos(conn, 0)

        # Same day -> return same category
        if last_date == today:
            return _get_category_at_pos(conn, category_pos)

        # New day -> advance category
        total_categories = len(CATEGORIES)

        if category_pos >= total_categories - 1:
            last_category = _get_category_at_pos(conn, category_pos)
            _reshuffle_categories(conn, avoid_first=last_category)
            category_pos = 0
        else:
            category_pos += 1

        _set_system_state_category(conn, today, category_pos)
        conn.commit()

        return _get_category_at_pos(conn, category_pos)

    finally:
        conn.close()


# -----------------------------
# Pokémon rotation
# -----------------------------

def _pokemon_table_count(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM pokemon_rotation")
    return cur.fetchone()["c"]


def _get_pokemon_at_pos(conn, pos: int) -> int:
    cur = conn.cursor()
    cur.execute("SELECT pokemon_id FROM pokemon_rotation WHERE position = ?", (pos,))
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Missing Pokémon at position {pos}")
    return row["pokemon_id"]


def _seed_pokemon_if_empty(conn, total_pokemon: int) -> None:
    if _pokemon_table_count(conn) > 0:
        return

    ids = list(range(1, total_pokemon + 1))
    random.shuffle(ids)

    cur = conn.cursor()
    for i, pokemon_id in enumerate(ids):
        cur.execute("""
            INSERT INTO pokemon_rotation (position, pokemon_id)
            VALUES (?, ?)
        """, (i, pokemon_id))


def _reshuffle_pokemon(conn, total_pokemon: int, avoid_first=None) -> None:
    ids = list(range(1, total_pokemon + 1))

    for _ in range(20):
        random.shuffle(ids)
        if avoid_first is None or ids[0] != avoid_first:
            break

    cur = conn.cursor()
    cur.execute("DELETE FROM pokemon_rotation")

    for i, pokemon_id in enumerate(ids):
        cur.execute("""
            INSERT INTO pokemon_rotation (position, pokemon_id)
            VALUES (?, ?)
        """, (i, pokemon_id))


def get_today_pokemon_id(db_path="content.db") -> int:
    today = date.today().isoformat()

    conn = connect(db_path)
    try:
        existing_count = _pokemon_table_count(conn)

        try:
            total_pokemon = get_total_pokemon()
        except Exception:
            if existing_count > 0:
                total_pokemon = existing_count
            else:
                raise

        _seed_pokemon_if_empty(conn, total_pokemon)
        row = _get_system_state(conn)

        # Same Pokémon for the same day
        if row["pokemon_date"] == today and row["current_pokemon_id"] is not None:
            return row["current_pokemon_id"]

        pokemon_pos = row["pokemon_pos"]
        total_rows = _pokemon_table_count(conn)

        if total_rows == 0:
            raise RuntimeError("pokemon_rotation is empty")

        if pokemon_pos >= total_rows:
            pokemon_pos = 0

        pokemon_id = _get_pokemon_at_pos(conn, pokemon_pos)

        # Prepare next position
        if pokemon_pos >= total_rows - 1:
            _reshuffle_pokemon(conn, total_pokemon, avoid_first=pokemon_id)
            next_pokemon_pos = 0
        else:
            next_pokemon_pos = pokemon_pos + 1

        _set_system_state_pokemon(
            conn,
            pokemon_date=today,
            current_pokemon_id=pokemon_id,
            pokemon_pos=next_pokemon_pos
        )
        conn.commit()

        return pokemon_id

    finally:
        conn.close()