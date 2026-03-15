import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False

load_dotenv()


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


DB_PATH = os.getenv("DB_PATH", "content.db")
ROTATION_INTERVAL = max(1, _get_int("ROTATION_INTERVAL", 300))
DISPLAY_BRIGHTNESS = max(0.0, min(1.0, _get_float("DISPLAY_BRIGHTNESS", 0.7)))
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
