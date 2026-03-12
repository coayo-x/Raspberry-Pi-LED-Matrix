
import json
import urllib.parse
import urllib.request

BASE_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEOUT = 10
DEFAULT_LATITUDE = 42.1292
DEFAULT_LONGITUDE = -80.0851
DEFAULT_LOCATION_NAME = "Erie, PA"

WEATHER_CODES = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Cloudy",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with hail",
}


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
    raise RuntimeError(f"Weather API failed after retries: {last_error}")


def get_weather_data(
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    location_name: str = DEFAULT_LOCATION_NAME,
) -> dict:
    params = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code,is_day,wind_speed_10m",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "auto",
        }
    )

    data = _fetch_json(f"{BASE_URL}?{params}")
    current = data.get("current", {})

    weather_code = current.get("weather_code")
    return {
        "location": location_name,
        "temperature_f": current.get("temperature_2m"),
        "weather_code": weather_code,
        "condition": WEATHER_CODES.get(weather_code, "Unknown"),
        "wind_mph": current.get("wind_speed_10m"),
    }


def get_weather_fallback(location_name: str = DEFAULT_LOCATION_NAME) -> dict:
    return {
        "location": location_name,
        "temperature_f": "--",
        "weather_code": None,
        "condition": "Weather unavailable",
        "wind_mph": "--",
    }
