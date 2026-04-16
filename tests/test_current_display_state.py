from current_display_state import (
    load_current_display_state,
    normalize_current_display_state,
    save_current_display_state,
)


def test_normalize_current_display_state_maps_non_joke_categories() -> None:
    pokemon_state = normalize_current_display_state(
        {
            "time": "2026-03-15 09:00:00",
            "slot_key": "2026-03-15:108",
            "category": "pokemon",
            "data": {
                "name": "Bulbasaur",
                "types": ["Grass", "Poison"],
                "hp": 45,
                "attack": 49,
                "defense": 49,
                "image_url": "https://example.test/bulbasaur.png",
            },
        },
        updated_at="2026-03-15T09:00:01",
    )

    weather_state = normalize_current_display_state(
        {
            "time": "2026-03-15 09:05:00",
            "slot_key": "2026-03-15:109",
            "category": "weather",
            "data": {
                "location": "Erie, PA",
                "condition": "Cloudy",
                "temperature_f": 37,
                "wind_mph": 11,
            },
        },
        updated_at="2026-03-15T09:05:01",
    )

    science_state = normalize_current_display_state(
        {
            "time": "2026-03-15 09:15:00",
            "slot_key": "2026-03-15:111",
            "category": "science",
            "data": {
                "name": "Helium",
                "symbol": "He",
                "atomic_number": 2,
            },
        },
        updated_at="2026-03-15T09:15:01",
    )

    assert pokemon_state["setup"] == "Bulbasaur"
    assert pokemon_state["punchline"] == "Grass / Poison | HP 45 | ATK 49 | DEF 49"
    assert pokemon_state["data"]["image_url"] == "https://example.test/bulbasaur.png"

    assert weather_state["setup"] == "Erie, PA"
    assert weather_state["punchline"] == "Cloudy | 37F | Wind 11 mph"

    assert science_state["setup"] == "Helium (He)"
    assert science_state["punchline"] == "Atomic 2"


def test_save_and_load_current_display_state_uses_isolated_database(
    isolated_db_path,
) -> None:
    payload = {
        "time": "2026-03-15 10:00:00",
        "slot_key": "2026-03-15:120",
        "category": "joke",
        "data": {
            "type": "twopart",
            "setup": "Why did the byte cross the bus?",
            "delivery": "To get to the other side of memory.",
        },
    }

    save_current_display_state(
        payload, db_path=str(isolated_db_path), updated_at="2026-03-15T10:00:01"
    )
    state = load_current_display_state(db_path=str(isolated_db_path))

    assert state["has_data"] is True
    assert state["slot"] == "2026-03-15:120"
    assert state["category"] == "joke"
    assert state["setup"] == "Why did the byte cross the bus?"
    assert state["punchline"] == "To get to the other side of memory."
    assert state["data"]["type"] == "twopart"


def test_normalize_current_display_state_maps_custom_text_style_summary() -> None:
    custom_text_state = normalize_current_display_state(
        {
            "time": "2026-03-23 12:00:00",
            "slot_key": "2026-03-23:144",
            "category": "custom_text",
            "data": {
                "text": "Maintenance window at 3 PM",
                "duration_minutes": 5,
                "style": {
                    "bold": True,
                    "italic": False,
                    "underline": True,
                    "font_family": "mono",
                    "font_size": 18,
                    "text_color": "orange",
                    "background_color": "black",
                    "alignment": "center",
                },
            },
        },
        updated_at="2026-03-23T12:00:01",
    )

    assert custom_text_state["setup"] == "Maintenance window at 3 PM"
    assert (
        custom_text_state["punchline"]
        == "mono 18px | Center | Bold/Underline | orange on black | 5m"
    )


def test_normalize_current_display_state_maps_snake_game_summary() -> None:
    snake_state = normalize_current_display_state(
        {
            "time": "2026-03-26 12:00:00",
            "slot_key": "2026-03-26:144",
            "category": "snake_game",
            "data": {
                "state": "waiting",
                "score": 0,
                "summary": "Press any button to start",
            },
        },
        updated_at="2026-03-26T12:00:01",
    )

    assert snake_state["setup"] == "Snake Game Mode"
    assert snake_state["punchline"] == "Press any button to start | Score 0"
