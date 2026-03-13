import sys
import time
from datetime import datetime

from db_manager import init_db
from display_manager import DisplayManager
from rotation_engine import (
    get_current_category,
    get_current_joke,
    get_current_science_fact,
    get_current_slot_key,
    get_today_pokemon_id,
    seconds_until_next_slot,
)
from apis.pokemon import get_pokemon_data, get_pokemon_fallback
from apis.weather import get_weather_data, get_weather_fallback


def build_content_for_now(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    category = get_current_category(now)

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

    elif category == "temperature":
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

    elif category == "temperature":
        print(f"Temperature in {data['location']}: {data['temperature_f']}°F")
        print(f"Condition: {data['condition']}")

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
    payload = build_content_for_now(now)
    print_payload(payload)
    display.display_payload(payload)
    return payload


def run_forever(display: DisplayManager, boot_delay: int = 10) -> None:
    init_db()

    if boot_delay > 0:
        time.sleep(boot_delay)

    last_slot_key = None

    while True:
        now = datetime.now()
        slot_key = get_current_slot_key(now)

        if slot_key != last_slot_key:
            payload = build_content_for_now(now)
            print_payload(payload)
            duration = seconds_until_next_slot(now)
            display.display_payload(payload, duration_seconds=duration)
            last_slot_key = slot_key
        else:
            time.sleep(1)


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
