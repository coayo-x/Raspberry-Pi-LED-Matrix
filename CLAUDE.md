# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Raspberry Pi display controller that rotates through content categories (Pokémon, weather, jokes, science facts) on a chain of three 64×32 HUB75 LED matrix panels (192×32 pixels total). A web dashboard (served by `dashboard_server.py`) lets users skip/switch categories, send custom text, and play snake on the display in real time.

## Running the project

```bash
# Development (no physical matrix required)
python main.py --simulate

# Single render pass (useful for testing a specific category)
python main.py --simulate --once

# Save preview frames as PNG files
python main.py --simulate --save-previews

# Production (on Raspberry Pi with matrix attached)
python main.py

# Web dashboard (separate process)
python dashboard_server.py
```

## Tests, linting, formatting

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_rotation_engine.py

# Run a single test by name
pytest tests/test_rotation_engine.py -k "test_function_name"

# Lint
ruff check .

# Format
black .
```

Pre-commit hooks enforce ruff, black, and basic file hygiene. Install with `pre-commit install`.

**CI caveat:** `.github/workflows/pylint.yml` runs ruff, black, and pytest with `|| true`, so GitHub Actions always reports success even when checks fail. Do not rely on a green CI badge as proof of correctness.

## Configuration

Copy `.env.example` to `.env`. All config is loaded in `config.py` from environment variables at **import time** — later `.env` changes do not affect already-imported modules. The key ones:
- `WEATHER_API_KEY` — parsed but unused; Open-Meteo does not require an API key
- `ROTATION_INTERVAL` — seconds per category slot (default 300)
- `DASHBOARD_PORT` — default 8080
- `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` — enables admin features in the dashboard
- `DISPLAY_BRIGHTNESS` — parsed but not currently applied to matrix output
- `DB_PATH` — path to the SQLite database (default `content.db`); relative paths depend on the working directory

## Architecture

### Key files

| Path | Role |
| --- | --- |
| `main.py` | Runtime CLI, rotation loop, one-shot simulation, and display handoff |
| `display_manager.py` | PIL/numpy rendering and optional hardware matrix output |
| `dashboard_server.py` | Threaded HTTP dashboard server and JSON API routes |
| `db_manager.py` | SQLite schema creation, connections, metadata helpers, and state tables |
| `runtime_control.py` | DB-backed skip, switch, locks, cooldowns, and custom-text force controls |
| `rotation_engine.py` | Slot-based category selection and per-slot content selection |
| `custom_text.py` | Public/admin custom text validation, moderation, style normalization, and storage |
| `current_display_state.py` | Normalized dashboard snapshot table for what the runtime is showing |
| `admin_auth.py` | Admin password verification, login throttling, and DB-backed sessions |
| `snake_control.py` | Admin API helpers and DB state for Snake mode/input |
| `snake_game.py` | Snake game loop, levels, rendering payloads, controls, and score state |
| `apis/` | Weather, Pokémon, joke, and science API clients with fallbacks |
| `dashboard_assets/` | Dashboard HTML, CSS, JavaScript, and icon |
| `systemd/` | Example runtime and dashboard unit files — review before installing |
| `tests/` | Pytest coverage for runtime controls, dashboard APIs, display behavior, custom text, auth, snapshots, and Snake |

### Two-process model

`main.py` drives the display in a blocking loop. `dashboard_server.py` runs as a separate HTTP server. They communicate exclusively through a shared SQLite database (`content.db`, WAL mode).

### Interrupt pattern

`DisplayManager.display_payload()` accepts a `should_interrupt: Callable[[], bool]` parameter. All animations poll this callable every ~50ms and abort early if it returns `True`. `main.py` constructs this callable by comparing DB counters at the start of each display cycle against counters that `runtime_control.py` increments when the dashboard sends a skip/switch request.

### Content pipeline

1. `rotation_engine.py` — determines the active category based on `(seconds_since_midnight // ROTATION_INTERVAL) % 4`, cycling through `DISPLAY_SEQUENCE = ["pokemon", "weather", "joke", "science"]`
2. `main.py:build_content_for_now()` — fetches data for the current category from `apis/`
3. `main.py:build_runtime_payload()` — saves the payload to DB via `current_display_state.py` (for the dashboard to poll)
4. `DisplayManager.display_payload()` — renders and animates the content on the panels

The dashboard snapshot is saved **before** display rendering begins. A render or hardware failure after that point can leave the dashboard showing the intended payload rather than a confirmed visible frame.

### Database (`db_manager.py`)

SQLite in WAL mode. Schema is initialized by `init_db()` and evolved additively via `_ensure_column()` — no destructive migrations. `schema_version` is stored as a `meta` value but is not a real migration system.

Key tables:
- `meta` — key/value store for runtime control signals (request counters, locks, custom text override JSON)
- `system_state` — single row (id=1) holding current Pokémon, joke, and science fact for the active slot
- `current_display_state` — single row (id=1) with the latest rendered payload as JSON; polled by the dashboard
- `pokemon_rotation` — shuffled Pokémon ID list; reshuffled each full cycle
- `used_jokes` — deduplication log so jokes don't repeat until all are exhausted; grows indefinitely with no cleanup policy
- `admin_sessions` / `admin_login_attempts` — session auth with lockout; note `admin_login_attempts` table exists in schema but current throttling is **in-process memory**, not DB-backed — it resets on server restart

Legacy/lightly-used tables: `category_rotation`, `jokes_rotation`.

### Priority order in `main.py:run_forever()`

1. **Snake mode** — takes full control of the display; all other signals are drained and ignored
2. **Forced custom text** (`custom_text_force` meta flag) — admin-pinned overlay, blocks skip/switch
3. **Active custom text override** — time-limited user-submitted text
4. **Skip / switch category requests** — consume counters from the `meta` table; if both are pending in the same slot, switch wins first, then skip
5. **Time-slot rotation** — normal category cycling

Skip/switch requests are discarded while Snake or custom text is active. A user action can appear accepted by the API and then have no visible effect.

`run_forever()` has no top-level crash containment — an unhandled exception in API fetch, DB access, rendering, or game code can terminate the runtime unless systemd restarts it.

### `DisplayManager` (`display_manager.py`)

Wraps `adafruit_blinka_raspberry_pi5_piomatter` (absent on non-Pi; the manager degrades gracefully in simulation mode, but raises at initialization if hardware mode is requested without the backend). Physical layout constants: `PANEL_ROWS=32`, `PANEL_COLS=64`, `PANEL_CHAIN_LENGTH=3`. `GLOBAL_ROTATE_180=True` flips the framebuffer to match the physical mount orientation.

Frames are rendered with PIL, converted to numpy arrays, resized with nearest-neighbor scaling, rotated 180°, then flipped before `matrix.show()`. Preview images are saved after the rotate step but before the final flip — so saved previews may not exactly match the hardware framebuffer orientation.

Each category has a dedicated `_animate_*` method that handles transitions and interrupt polling. `render_payload()` is a static helper used by tests; it does not exercise every animated runtime path. Pokémon artwork is fetched during rendering, so network latency can affect frame timing.

### `apis/`

Four API clients (`weather.py`, `pokemon.py`, `jokes.py`, `science.py`). Each has a fallback function that returns hardcoded data when the external call fails.

- **Weather** — Open-Meteo, default location Erie PA. Fetches `is_day` but the current rendering path does not use it.
- **Pokémon** — PokeAPI; falls back to IDs 1–1025 on catalog failure. If fallback triggers during daily rotation setup it becomes the stored rotation source for that day.
- **Jokes** — JokeAPI safe mode; static fallback repeats the same joke across extended outages.
- **Science** — periodic table JSON endpoint; in-memory cache with a local fallback list. If the upstream returns an empty array, `random.choice([])` will raise.

### Custom text

Custom text is stored as JSON in the `meta` key `custom_text_override`. `custom_text.py` handles validation, moderation (checked against `badwordslist.txt` when present), and normalization.

- Text is trimmed and length-limited.
- Duration is clamped to 5–300 seconds.
- Styles are normalized: bold, italic, underline, font family/size, text/background color and brightness, and alignment.
- Public custom text is blocked while Snake mode is active, while an admin lock or cooldown applies, or during a short submission cooldown.
- Admin force mode (`custom_text_force` meta flag) keeps the stored override on screen outside the normal timer until force is disabled or the override is removed.

### Snake game

Snake is controlled through admin dashboard APIs and DB `meta` keys. Enabling Snake resets mode state, score, level, direction, and pending inputs. While enabled, Snake blocks normal rotation and custom text submission.

`snake_game.py` uses a 2-pixel cell grid over the 192×32 matrix. Phases: waiting → level intro → playing → paused → game over. The first movement control starts a level intro; pause toggles during play; after game over any control restarts the current level. Score, level, phase, and active direction are mirrored into DB state for the dashboard. Levels add obstacles and speed pressure; food and obstacles avoid the score HUD area. Keyboard input from the dashboard is sent only while the user is admin-authenticated, Snake mode is enabled, and focus is not in a text input.

### Dashboard (`dashboard_server.py`)

Pure stdlib HTTP server (`ThreadingHTTPServer`). Serves static files from `dashboard_assets/` and a set of REST endpoints under `/api/`. Admin endpoints require a session cookie set by `POST /api/admin/login`. All endpoints return JSON. The frontend polls `/api/current-display-state` and `/api/control-state` on a configurable interval.

**Endpoint inconsistency:** Most admin routes are under `/api/admin/...`, but the forced custom text endpoint is `/admin/custom-text/force`. The server and frontend agree today, but watch for this when adding routes or tests.

`admin_auth.py` supports bcrypt password hashes and a PBKDF2 legacy fallback. Sessions are stored as SHA-256 token hashes in SQLite.

## systemd deployment

Two service units in `systemd/`:
- `led-matrix.service` — runs `main.py`
- `led-matrix-dashboard.service` — runs `dashboard_server.py --host 0.0.0.0`

Both read `.env` from the project directory and restart automatically on failure.

**Before installing:** the unit files contain duplicated `User`, `Group`, `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` directives for different deployment accounts (`pi` and `human` examples). A plain install may fail or run the wrong command. Clean them for the target host first. `Notes/systemd.md` has additional deployment notes but is inconsistent — verify against the current service files.

`requirements.txt` does not include `adafruit_blinka_raspberry_pi5_piomatter`. A fresh hardware install based only on requirements will miss a required package.

## Change guidance

- Keep runtime behavior coordinated through the DB helpers (`runtime_control.py`, `db_manager.py`) instead of ad hoc writes to SQLite.
- Update tests when changing category payloads, dashboard API contracts, custom text behavior, or Snake controls.
- Be careful with import-time config in tests — modules may need reloads when environment values change.
- Do not rely on local runtime artifacts (`content.db`, preview frames, `badwordslist.txt`) being present in a fresh checkout.
- `main.py` catches any exception while importing `runtime_control` and falls back to a partial inline implementation — a real runtime-control bug can be silently hidden.
- After touching display, control flow, or DB code, run:

```bash
python -m pytest
python main.py --simulate --once
```
