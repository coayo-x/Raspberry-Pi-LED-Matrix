import json
import urllib.request

BASE_URL = "https://pokeapi.co/api/v2"
DEFAULT_TIMEOUT = 10


def _fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"API request failed with status {response.status}: {url}")
        return json.loads(response.read().decode("utf-8"))


def get_total_pokemon() -> int:
    data = _fetch_json(f"{BASE_URL}/pokemon?limit=1")
    count = data.get("count")

    if not isinstance(count, int) or count <= 0:
        raise ValueError("Invalid Pokémon count returned by PokeAPI")

    return count


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
        "height": data.get("height"),   # decimetres
        "weight": data.get("weight"),   # hectograms
        "hp": stats_map.get("hp"),
        "attack": stats_map.get("attack"),
        "defense": stats_map.get("defense"),
        "image_url": artwork or fallback_sprite,
    }