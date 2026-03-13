# science.py
import hashlib
import json
import random
import urllib.request
from typing import Optional, List, Dict

# Static JSON of all elements from periodic-table-api (public, no key required)
ELEMENTS_URL = "https://neelpatel05.github.io/periodic-table-api/api/v1/element.json"
DEFAULT_TIMEOUT = 10

# Fallback elements in case the API is unreachable
FALLBACK_ELEMENTS = [
    {"name": "Hydrogen", "symbol": "H", "atomicNumber": 1},
    {"name": "Helium", "symbol": "He", "atomicNumber": 2},
    {"name": "Lithium", "symbol": "Li", "atomicNumber": 3},
    {"name": "Carbon", "symbol": "C", "atomicNumber": 6},
    {"name": "Oxygen", "symbol": "O", "atomicNumber": 8},
    {"name": "Iron", "symbol": "Fe", "atomicNumber": 26},
    {"name": "Gold", "symbol": "Au", "atomicNumber": 79},
]

# Cache for elements list (to avoid re-fetching)
_elements_cache: List[Dict] = []


def _fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Fetch JSON from URL with retry logic (same pattern as other modules)."""
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
    raise RuntimeError(f"Science API failed after retries: {last_error}")


def _fallback_key(text: str) -> str:
    """Generate a fallback key using SHA256."""
    return "hash:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_elements(force_refresh: bool = False) -> List[Dict]:
    """Fetch and return the list of all elements, with caching."""
    global _elements_cache
    if not _elements_cache or force_refresh:
        try:
            data = _fetch_json(ELEMENTS_URL)
            # API returns an array of element objects
            if isinstance(data, list):
                _elements_cache = data
            else:
                # Fallback if response format is unexpected
                _elements_cache = FALLBACK_ELEMENTS
        except Exception:
            _elements_cache = FALLBACK_ELEMENTS
    return _elements_cache


def get_random_element_fact() -> dict:
    """
    Return a random element fact formatted for small displays.
    Example: "Hydrogen (H) - Atomic Number 1"
    """
    elements = _load_elements()
    element = random.choice(elements)

    # Build a short fact string
    name = element.get("name", "Unknown")
    symbol = element.get("symbol", "?")
    number = element.get("atomicNumber", "?")

    fact_text = f"{name} ({symbol}) - Atomic Number {number}"

    # Use a unique key (combination of name and number ensures uniqueness)
    key = f"element:{number}" if number != "?" else _fallback_key(fact_text)

    return {
        "key": key,
        "text": fact_text,
        "name": name,
        "symbol": symbol,
        "atomic_number": number,
        "category": "element",
    }


def get_element_by_number(atomic_number: int) -> dict:
    """Fetch a specific element by its atomic number."""
    elements = _load_elements()
    for element in elements:
        if element.get("atomicNumber") == atomic_number:
            name = element.get("name", "Unknown")
            symbol = element.get("symbol", "?")
            fact_text = f"{name} ({symbol}) - Atomic Number {atomic_number}"
            return {
                "key": f"element:{atomic_number}",
                "text": fact_text,
                "name": name,
                "symbol": symbol,
                "atomic_number": atomic_number,
                "category": "element",
            }
    # Fallback if not found
    return {
        "key": f"element:fallback:{atomic_number}",
        "text": f"Element {atomic_number} not found",
        "name": "Unknown",
        "symbol": "?",
        "atomic_number": atomic_number,
        "category": "element",
    }


def get_science_fact_fallback() -> dict:
    """Return a fallback fact (element) when all else fails."""
    element = random.choice(FALLBACK_ELEMENTS)
    fact_text = f"{element['name']} ({element['symbol']}) - Atomic Number {element['atomicNumber']}"
    return {
        "key": _fallback_key(fact_text),
        "text": fact_text,
        "name": element['name'],
        "symbol": element['symbol'],
        "atomic_number": element['atomicNumber'],
        "category": "element",
        "_fallback": True,
    }


# Optional: alias for consistency with other modules
get_random_science_fact = get_random_element_fact
