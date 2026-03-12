import json
import re
import urllib.request
from typing import List

BASE_URL = "https://pokeapi.co/api/v2"
DEFAULT_TIMEOUT = 10
FALLBACK_POKEMON_IDS = list(range(1, 1026))


def _fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    last_error = None

    for _ in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "RaspberryPi-Pokemon-LED/1.0"},
            )

            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"API request failed with status {response.status}: {url}")
                return json.loads(response.read().decode("utf-8"))

        except Exception as e:
            last_error = e

    raise RuntimeError(f"Pokémon API failed after retries: {last_error}")


def _extract_pokemon_id(url: str) -> int | None:
    match = re.search(r"/pokemon/(\d+)/?$", url)
    if not match:
        return None
    return int(match.group(1))


def get_valid_pokemon_ids() -> List[int]:
    try:
        data = _fetch_json(f"{BASE_URL}/pokemon?limit=2000&offset=0")
        results = data.get("results", [])

        ids = []
        for item in results:
            url = item.get("url", "")
            pokemon_id = _extract_pokemon_id(url)
            if pokemon_id is not None:
                ids.append(pokemon_id)

        ids = sorted(set(ids))
        return ids or FALLBACK_POKEMON_IDS

    except Exception:
        return FALLBACK_POKEMON_IDS


def get_total_pokemon() -> int:
    return len(get_valid_pokemon_ids())


def get_pokemon_data(pokemon_id: int) -> dict:
    data = _fetch_json(f"{BASE_URL}/pokemon/{pokemon_id}")

    types = [
        item["type"]["name"].title()
        for item in sorted(data.get("types", []), key=lambda x: x["slot"])
    ]

    stats_map = {
        item["stat"]["name"]: item["base_stat"]
        for item in data.get("stats", [])
    }

    sprites = data.get("sprites", {})
    artwork = (
        sprites.get("other", {})
        .get("official-artwork", {})
        .get("front_default")
    )
    fallback_sprite = sprites.get("front_default")

    return {
        "id": data["id"],
        "name": data["name"].title(),
        "types": types,
        "height": data.get("height"),
        "weight": data.get("weight"),
        "hp": stats_map.get("hp"),
        "attack": stats_map.get("attack"),
        "defense": stats_map.get("defense"),
        "image_url": artwork or fallback_sprite,
    }


def get_pokemon_fallback(pokemon_id: int | None = None) -> dict:
    return {
        "id": pokemon_id,
        "name": "Pokémon unavailable",
        "types": ["Unknown"],
        "height": "--",
        "weight": "--",
        "hp": "--",
        "attack": "--",
        "defense": "--",
        "image_url": None,
    }