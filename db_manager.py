import sqlite3
from pathlib import Path

DB_FILE = "content.db"


def connect(db_path: str = DB_FILE) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = cur.fetchall()
    return any(col["name"] == column_name for col in columns)


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    if not _column_exists(conn, table_name, column_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db(db_path: str = DB_FILE) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    cur.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '4')")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS system_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_date TEXT,
            category_pos INTEGER NOT NULL DEFAULT 0,
            pokemon_pos INTEGER NOT NULL DEFAULT 0,
            joke_pos INTEGER NOT NULL DEFAULT 0,
            pokemon_date TEXT,
            current_pokemon_id INTEGER,
            current_joke_slot TEXT,
            current_joke_id TEXT,
            current_joke_type TEXT,
            current_joke_text TEXT,
            current_joke_setup TEXT,
            current_joke_delivery TEXT,
            current_science_slot TEXT,
            current_science_key TEXT,
            current_science_text TEXT,
            current_science_name TEXT,
            current_science_symbol TEXT,
            current_science_atomic_number INTEGER
        )
        """
    )
    cur.execute("INSERT OR IGNORE INTO system_state (id) VALUES (1)")

    _ensure_column(conn, "system_state", "last_date", "TEXT")
    _ensure_column(conn, "system_state", "category_pos", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "system_state", "pokemon_pos", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "system_state", "joke_pos", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "system_state", "pokemon_date", "TEXT")
    _ensure_column(conn, "system_state", "current_pokemon_id", "INTEGER")
    _ensure_column(conn, "system_state", "current_joke_slot", "TEXT")
    _ensure_column(conn, "system_state", "current_joke_id", "TEXT")
    _ensure_column(conn, "system_state", "current_joke_type", "TEXT")
    _ensure_column(conn, "system_state", "current_joke_text", "TEXT")
    _ensure_column(conn, "system_state", "current_joke_setup", "TEXT")
    _ensure_column(conn, "system_state", "current_joke_delivery", "TEXT")
    _ensure_column(conn, "system_state", "current_science_slot", "TEXT")
    _ensure_column(conn, "system_state", "current_science_key", "TEXT")
    _ensure_column(conn, "system_state", "current_science_text", "TEXT")
    _ensure_column(conn, "system_state", "current_science_name", "TEXT")
    _ensure_column(conn, "system_state", "current_science_symbol", "TEXT")
    _ensure_column(conn, "system_state", "current_science_atomic_number", "INTEGER")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pokemon_rotation (
            position INTEGER PRIMARY KEY,
            pokemon_id INTEGER NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS used_jokes (
            joke_key TEXT PRIMARY KEY,
            joke_type TEXT NOT NULL,
            joke_text TEXT,
            joke_setup TEXT,
            joke_delivery TEXT,
            first_seen_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS category_rotation (
            position INTEGER PRIMARY KEY,
            category TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS jokes_rotation (
            position INTEGER PRIMARY KEY,
            joke_text TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()
