import sys
import time
from datetime import datetime
from typing import Callable

from config import DB_PATH
from current_display_state import save_current_display_state
from db_manager import connect, init_db
from display_manager import DisplayManager
from rotation_engine import (
    DISPLAY_SEQUENCE,
    get_current_category,
    get_current_joke,
    get_next_category,
    get_current_science_fact,
    get_current_slot_key,
    get_today_pokemon_id,
    seconds_until_next_slot,
)
from apis.pokemon import get_pokemon_data, get_pokemon_fallback
from apis.weather import get_weather_data, get_weather_fallback

try:
    from runtime_control import (
        consume_skip_category_request,
        consume_switch_category_request,
        get_skip_category_state,
        get_switch_category_state,
    )
except Exception:
    SKIP_CATEGORY_REQUEST_KEY = "skip_category_request_count"
    SKIP_CATEGORY_HANDLED_KEY = "skip_category_handled_count"
    SWITCH_CATEGORY_REQUEST_KEY = "switch_category_request_count"
    SWITCH_CATEGORY_HANDLED_KEY = "switch_category_handled_count"
    SWITCH_CATEGORY_VALUE_KEY = "switch_category_value"

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

    def get_switch_category_state(
        db_path: str = DB_PATH,
    ) -> tuple[int, int, str | None]:
        conn = connect(db_path)
        try:
            return (
                _get_meta_int(conn, SWITCH_CATEGORY_REQUEST_KEY),
                _get_meta_int(conn, SWITCH_CATEGORY_HANDLED_KEY),
                _get_meta_text(conn, SWITCH_CATEGORY_VALUE_KEY),
            )
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

            category = (_get_meta_text(conn, SWITCH_CATEGORY_VALUE_KEY) or "").strip()
            if category not in DISPLAY_SEQUENCE:
                _set_meta(conn, SWITCH_CATEGORY_HANDLED_KEY, str(request_count))
                conn.commit()
                return None

            handled_count = request_count
            _set_meta(conn, SWITCH_CATEGORY_HANDLED_KEY, str(handled_count))
            conn.commit()
            return handled_count, category
        finally:
            conn.close()


def build_runtime_payload(
    now: datetime | None = None, category_override: str | None = None
) -> dict:
    payload = build_content_for_now(now, category_override=category_override)
    save_current_display_state(payload)
    return payload


def build_content_for_now(
    now: datetime | None = None, category_override: str | None = None
) -> dict:
    now = now or datetime.now()
    category = category_override or get_current_category(now)

    payload = {
        "slot_key": get_current_slot_key(now),
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "category": category,
        "data": None,
    }

    if category == "pokemon":
        pokemon_id = get_today_pokemon_id(today=now.date().isoformat())
        try:
            payload["data"] = get_pokemon_data(pokemon_id)
        except Exception:
            payload["data"] = get_pokemon_fallback(pokemon_id)

    elif category == "weather":
        try:
            payload["data"] = get_weather_data()
        except Exception:
            payload["data"] = get_weather_fallback()

    elif category == "joke":
        payload["data"] = get_current_joke(now=now)

    elif category == "science":
        payload["data"] = get_current_science_fact(now=now)

    else:
        raise RuntimeError(f"Unknown category: {category}")

    return payload


def print_payload(payload: dict) -> None:
    category = payload["category"]
    data = payload["data"]

    print("=" * 50)
    print(f"Time: {payload['time']}")
    print(f"Slot: {payload['slot_key']}")
    print(f"Category: {category}")

    if category == "pokemon":
        print(f"Today's Pokémon is: {data['name']}")
        print(f"Types: {' / '.join(data['types'])}")
        print(f"HP: {data['hp']} | ATK: {data['attack']} | DEF: {data['defense']}")
        print(f"Height: {data['height']} | Weight: {data['weight']}")
        print(f"Image URL: {data['image_url']}")

    elif category == "weather":
        print(f"Weather in {data['location']}: {data['condition']}")
        print(f"Temperature: {data['temperature_f']}°F")
        print(f"Wind: {data['wind_mph']} mph")

    elif category == "joke":
        if data["type"] == "single":
            print(f"Joke: {data['text']}")
        else:
            print(f"Setup: {data['setup']}")
            print(f"Punchline: {data['delivery']}")

    elif category == "science":
        print(f"Science Fact: {data['text']}")


def run_once(display: DisplayManager, now: datetime | None = None) -> dict:
    init_db()
    payload = build_runtime_payload(now)
    print_payload(payload)
    display.display_payload(payload)
    return payload


def _get_interrupt_baselines() -> tuple[int, int]:
    _, skip_handled_count = get_skip_category_state()
    _, switch_handled_count, _ = get_switch_category_state()
    return skip_handled_count, switch_handled_count


def _build_interrupt_checker(
    skip_baseline: int, switch_baseline: int
) -> Callable[[], bool]:
    return lambda: (
        get_skip_category_state()[0] > skip_baseline
        or get_switch_category_state()[0] > switch_baseline
    )


def _clear_expired_runtime_control_requests() -> tuple[int, int]:
    while consume_switch_category_request() is not None:
        pass

    while consume_skip_category_request() is not None:
        pass

    return _get_interrupt_baselines()


def run_forever(display: DisplayManager, boot_delay: int = 10) -> None:
    init_db()

    if boot_delay > 0:
        time.sleep(boot_delay)

    active_slot_key = None
    active_category = None

    while True:
        now = datetime.now()
        slot_key = get_current_slot_key(now)
        category_override = None
        skip_handled_count: int
        switch_handled_count: int

        if slot_key != active_slot_key:
            skip_handled_count, switch_handled_count = (
                _clear_expired_runtime_control_requests()
            )
        else:
            if active_category is None:
                time.sleep(1)
                continue

            switch_result = consume_switch_category_request()
            if switch_result is not None:
                switch_handled_count, category_override = switch_result
                _, skip_handled_count = get_skip_category_state()
            else:
                skip_handled_count = consume_skip_category_request()
                if skip_handled_count is None:
                    time.sleep(1)
                    continue

                _, switch_handled_count, _ = get_switch_category_state()
                category_override = get_next_category(active_category)

        payload = build_runtime_payload(now, category_override=category_override)
        print_payload(payload)
        duration = seconds_until_next_slot(now)
        display.display_payload(
            payload,
            duration_seconds=duration,
            should_interrupt=_build_interrupt_checker(
                skip_handled_count,
                switch_handled_count,
            ),
        )
        active_slot_key = slot_key
        active_category = payload["category"]


def main() -> None:
    args = set(sys.argv[1:])
    use_matrix = "--simulate" not in args
    save_previews = "--save-previews" in args

    display = DisplayManager(
        use_matrix=use_matrix,
        save_previews=save_previews,
    )
    display.run_startup_test()

    if "--once" in args:
        run_once(display)
    else:
        run_forever(display)


if __name__ == "__main__":
    main()
