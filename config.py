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


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DB_PATH = os.getenv("DB_PATH", "content.db")
ROTATION_INTERVAL = max(1, _get_int("ROTATION_INTERVAL", 300))
DISPLAY_BRIGHTNESS = max(0.0, min(1.0, _get_float("DISPLAY_BRIGHTNESS", 0.7)))
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = max(1, _get_int("DASHBOARD_PORT", 8080))
DASHBOARD_POLL_INTERVAL_MS = max(500, _get_int("DASHBOARD_POLL_INTERVAL_MS", 2000))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
ADMIN_SESSION_TTL_SECONDS = max(300, _get_int("ADMIN_SESSION_TTL_SECONDS", 43200))
ADMIN_LOGIN_MAX_ATTEMPTS = max(1, _get_int("ADMIN_LOGIN_MAX_ATTEMPTS", 5))
ADMIN_LOGIN_LOCKOUT_SECONDS = max(30, _get_int("ADMIN_LOGIN_LOCKOUT_SECONDS", 900))
ADMIN_SESSION_COOKIE_NAME = (
    os.getenv("ADMIN_SESSION_COOKIE_NAME", "led_matrix_admin_session").strip()
    or "led_matrix_admin_session"
)
ADMIN_SESSION_COOKIE_SECURE = _get_bool("ADMIN_SESSION_COOKIE_SECURE", False)
SKIP_CATEGORY_COOLDOWN_SECONDS = max(0, _get_int("SKIP_CATEGORY_COOLDOWN_SECONDS", 10))
SWITCH_CATEGORY_COOLDOWN_SECONDS = max(
    0, _get_int("SWITCH_CATEGORY_COOLDOWN_SECONDS", 10)
)
