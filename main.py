import sys
import time
from datetime import datetime

from db_manager import init_db
from rotation_engine import (
    get_current_category,
    get_current_joke,
    get_current_slot_key,
    get_today_pokemon_id,
    seconds_until_next_slot,
)
from apis.pokemon import get_pokemon_data
from apis.weather import get_weather_data


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
        payload["data"] = get_pokemon_data(pokemon_id)
    elif category == "weather":
        payload["data"] = get_weather_data()
    elif category == "temperature":
        payload["data"] = get_weather_data()
    elif category == "joke":
        payload["data"] = get_current_joke(now=now)
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


def run_once(now: datetime | None = None) -> dict:
    init_db()
    payload = build_content_for_now(now)
    print_payload(payload)
    return payload


def run_forever() -> None:
    init_db()
    last_slot_key = None

    while True:
        now = datetime.now()
        slot_key = get_current_slot_key(now)

        if slot_key != last_slot_key:
            payload = build_content_for_now(now)
            print_payload(payload)
            last_slot_key = slot_key

        time.sleep(min(5, seconds_until_next_slot(now)))


def main() -> None:
    if "--once" in sys.argv:
        run_once()
    else:
        run_forever()


if __name__ == "__main__":
    main()