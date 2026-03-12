import hashlib
import json
import urllib.request

JOKE_URL = "https://v2.jokeapi.dev/joke/Any?safe-mode&type=single,twopart"
DEFAULT_TIMEOUT = 10


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

    raise RuntimeError(f"Joke API failed after retries: {last_error}")


def _fallback_key(text: str) -> str:
    return "hash:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_random_joke() -> dict:
    data = _fetch_json(JOKE_URL)

    if data.get("error"):
        raise RuntimeError("Joke API returned an error")

    joke_type = data.get("type")
    joke_id = data.get("id")

    if joke_type == "single":
        text = str(data.get("joke", "")).strip()
        if not text:
            raise RuntimeError("Joke API returned an empty joke")
        return {
            "key": f"jokeapi:{joke_id}" if joke_id is not None else _fallback_key(text),
            "type": "single",
            "text": text,
            "setup": None,
            "delivery": None,
        }

    setup = str(data.get("setup", "")).strip()
    delivery = str(data.get("delivery", "")).strip()
    if not setup or not delivery:
        raise RuntimeError("Joke API returned an incomplete two-part joke")

    return {
        "key": f"jokeapi:{joke_id}" if joke_id is not None else _fallback_key(setup + "\n" + delivery),
        "type": "twopart",
        "text": None,
        "setup": setup,
        "delivery": delivery,
    }