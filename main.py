import sys
import time
from datetime import datetime
from typing import Callable

from config import DB_PATH
from custom_text import (
    get_active_custom_text_override,
    get_custom_text_interrupt_token,
    get_custom_text_remaining_seconds,
)
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
    now: datetime | None = None,
    category_override: str | None = None,
    custom_override: dict | None = None,
) -> dict:
    payload = build_content_for_now(
        now,
        category_override=category_override,
        custom_override=custom_override,
    )
    save_current_display_state(payload)
    return payload


def _build_custom_text_payload(now: datetime, override: dict) -> dict:
    return {
        "slot_key": get_current_slot_key(now),
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "category": "custom_text",
        "data": {
            "request_id": override["request_id"],
            "text": override["text"],
            "style": override["style"],
            "duration_seconds": override["duration_seconds"],
            "duration_minutes": override["duration_minutes"],
            "started_at": override["started_at"],
            "expires_at": override["expires_at"],
            "remaining_seconds": override["remaining_seconds"],
            "text_color_hex": override["text_color_hex"],
            "background_color_hex": override["background_color_hex"],
        },
    }


def build_content_for_now(
    now: datetime | None = None,
    category_override: str | None = None,
    custom_override: dict | None = None,
) -> dict:
    now = now or datetime.now()
    active_custom_override = custom_override or get_active_custom_text_override(now=now)
    if active_custom_override is not None:
        return _build_custom_text_payload(now, active_custom_override)

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

    elif category == "custom_text":
        style = data.get("style") or {}
        style_flags = [
            label
            for enabled, label in (
                (style.get("bold"), "bold"),
                (style.get("italic"), "italic"),
                (style.get("underline"), "underline"),
            )
            if enabled
        ]
        print(f"Custom Text: {data.get('text', '')}")
        print(
            f"Style: {style.get('font_family', 'sans')} {style.get('font_size', '--')}px | "
            f"{style.get('alignment', 'center')} | "
            f"{', '.join(style_flags) if style_flags else 'plain'} | "
            f"{style.get('text_color', 'white')} on {style.get('background_color', 'black')}"
        )
        print(
            f"Duration: {data.get('duration_minutes', '--')}m | Expires: {data.get('expires_at', '')}"
        )


def run_once(display: DisplayManager, now: datetime | None = None) -> dict:
    init_db()
    payload = build_runtime_payload(now)
    print_payload(payload)
    display.display_payload(payload, duration_seconds=1)
    return payload


def _get_interrupt_baselines(
    now: datetime | None = None,
) -> tuple[int, int, str | None]:
    _, skip_handled_count = get_skip_category_state()
    _, switch_handled_count, _ = get_switch_category_state()
    custom_interrupt_token = get_custom_text_interrupt_token(now=now)
    return skip_handled_count, switch_handled_count, custom_interrupt_token


def _build_interrupt_checker(
    skip_baseline: int,
    switch_baseline: int,
    custom_text_baseline: str | None,
) -> Callable[[], bool]:
    return lambda: (
        (
            custom_text_baseline is None
            and (
                get_skip_category_state()[0] > skip_baseline
                or get_switch_category_state()[0] > switch_baseline
            )
        )
        get_skip_category_state()[0] > skip_baseline
        or get_switch_category_state()[0] > switch_baseline
        or get_custom_text_interrupt_token() != custom_text_baseline
    )


def _clear_expired_runtime_control_requests(
    now: datetime | None = None,
) -> tuple[int, int, str | None]:
    while consume_switch_category_request() is not None:
        pass

    while consume_skip_category_request() is not None:
        pass

    return _get_interrupt_baselines(now=now)


def run_forever(display: DisplayManager, boot_delay: int = 10) -> None:
    init_db()

    if boot_delay > 0:
        time.sleep(boot_delay)

    active_slot_key = None
    active_category = None
    active_rotation_category = None

    while True:
        now = datetime.now()
        slot_key = get_current_slot_key(now)
        custom_override = get_active_custom_text_override(now=now)
        category_override = None
        skip_handled_count: int
        switch_handled_count: int
        custom_text_baseline: str | None

        if custom_override is not None:
            (
                skip_handled_count,
                switch_handled_count,
                custom_text_baseline,
            ) = _clear_expired_runtime_control_requests(now=now)

            payload = build_runtime_payload(now, custom_override=custom_override)
            print_payload(payload)
            display.display_payload(
                payload,
                duration_seconds=max(
                    1,
                    get_custom_text_remaining_seconds(custom_override, now=now),
                ),
                should_interrupt=_build_interrupt_checker(
                    skip_handled_count,
                    switch_handled_count,
                    custom_text_baseline,
                ),
            )
            active_slot_key = slot_key
            active_category = payload["category"]
            continue


        if custom_override is not None:
            if slot_key != active_slot_key:
                (
                    skip_handled_count,
                    switch_handled_count,
                    custom_text_baseline,
                ) = _clear_expired_runtime_control_requests(now=now)
            else:
                _, skip_handled_count = get_skip_category_state()
                _, switch_handled_count, _ = get_switch_category_state()
                custom_text_baseline = get_custom_text_interrupt_token(now=now)

            payload = build_runtime_payload(now, custom_override=custom_override)
            print_payload(payload)
            display.display_payload(
                payload,
                duration_seconds=max(
                    1,
                    get_custom_text_remaining_seconds(custom_override, now=now),
                ),
                should_interrupt=_build_interrupt_checker(
                    skip_handled_count,
                    switch_handled_count,
                    custom_text_baseline,
                ),
            )
            active_slot_key = slot_key
            active_category = payload["category"]
            continue

        if slot_key != active_slot_key:
            (
                skip_handled_count,
                switch_handled_count,
                custom_text_baseline,
            ) = _clear_expired_runtime_control_requests(now=now)
        else:
            if active_category is None:
                time.sleep(1)
                continue

            should_render_current_slot = active_category == "custom_text"
            switch_result = consume_switch_category_request()
            if switch_result is not None:
                switch_handled_count, category_override = switch_result
                _, skip_handled_count = get_skip_category_state()
            else:
                consumed_skip_count = consume_skip_category_request()
                if consumed_skip_count is None:
                    _, skip_handled_count = get_skip_category_state()
                    _, switch_handled_count, _ = get_switch_category_state()
                    if not should_render_current_slot:
                        time.sleep(1)
                        continue
                else:
                    skip_handled_count = consumed_skip_count
                    _, switch_handled_count, _ = get_switch_category_state()
                    base_category = active_rotation_category or get_current_category(now)
                    category_override = get_next_category(base_category)

            custom_text_baseline = get_custom_text_interrupt_token(now=now)

        payload = build_runtime_payload(now, category_override=category_override)
        print_payload(payload)
        duration = seconds_until_next_slot(now)
        display.display_payload(
            payload,
            duration_seconds=duration,
            should_interrupt=_build_interrupt_checker(
                skip_handled_count,
                switch_handled_count,
                custom_text_baseline,
            ),
        )
        active_slot_key = slot_key
        active_category = payload["category"]
        if payload["category"] in DISPLAY_SEQUENCE:
            active_rotation_category = payload["category"]


def main() -> None:
    args = set(sys.argv[1:])
    use_matrix = "--simulate" not in args
    save_previews = "--save-previews" in args

    display = DisplayManager(
        use_matrix=use_matrix,
        save_previews=save_previews,
    )

    if "--once" in args:
        run_once(display)
    else:
        run_forever(display)


if __name__ == "__main__":
    main()
