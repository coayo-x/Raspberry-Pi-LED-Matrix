# AGENT.md

## Purpose

This repository is a single-process Python application that drives a `64x32` RGB LED matrix on a Raspberry Pi. It rotates through four content categories on a fixed time schedule:

1. `pokemon`
2. `weather`
3. `joke`
4. `science`

The system is not event-driven, web-based, or service-oriented. It is a blocking loop with SQLite-backed state. The database is essential because it preserves content stability across slot boundaries, day changes, and restarts.

The current repo also contains a checked-in `content.db`. Treat that file as mutable runtime state, not as a canonical fixture.

## High-Level Architecture

```text
                        +----------------------+
                        |      main.py         |
                        | CLI + slot loop      |
                        +----------+-----------+
                                   |
                     build_content_for_now(now)
                                   |
            +----------------------+----------------------+
            |                      |                      |
            v                      v                      v
 +--------------------+  +--------------------+  +--------------------+
 | rotation_engine.py |  |    apis/*.py       |  | display_manager.py |
 | schedule + state   |  | network adapters   |  | render + animate   |
 +---------+----------+  +--------------------+  +---------+----------+
           |                                                |
           v                                                v
 +--------------------+                          +----------------------+
 |    db_manager.py   |                          | Piomatter / previews |
 | SQLite bootstrap   |                          | PIL images / matrix  |
 +---------+----------+                          +----------------------+
           |
           v
 +--------------------+
 |     content.db     |
 | persisted state    |
 +--------------------+
```

## Module Responsibilities

| Module | Responsibility | Notes |
| --- | --- | --- |
| `main.py` | Entry point, CLI flag parsing, main loop, payload assembly | Owns runtime orchestration only |
| `rotation_engine.py` | Slot math and stateful content selection | This is the real domain core |
| `db_manager.py` | SQLite connection and schema bootstrap | Uses ad hoc migration-by-column-existence |
| `display_manager.py` | Rendering, animation, sprite fetch, hardware bridge | Mixes pure rendering with I/O and timing |
| `apis/pokemon.py` | PokeAPI adapter | Also exposes fallback ID list |
| `apis/weather.py` | Open-Meteo adapter | Stateless, fetch-per-call |
| `apis/jokes.py` | JokeAPI adapter | Stateless; uniqueness handled elsewhere |
| `apis/science.py` | Periodic table adapter | Keeps an in-process cache of elements |

## Actual Control Flow

### Boot Path

```text
python main.py [flags]
  -> main()
    -> parse raw argv into a set
    -> construct DisplayManager(...)
    -> run_once(...) or run_forever(...)
      -> init_db()
      -> build_content_for_now(...)
      -> print_payload(...)
      -> display.display_payload(...)
```

### Continuous Runtime

```text
run_forever()
  -> init_db()
  -> optional boot delay (default 10s)
  -> while True:
       now = datetime.now()
       slot_key = get_current_slot_key(now)
       if slot changed:
         payload = build_content_for_now(now)
         duration = seconds_until_next_slot(now)
         display.display_payload(payload, duration_seconds=duration)
         last_slot_key = slot_key
       else:
         sleep(1)
```

The display path is blocking. There is no background fetching, no worker thread, and no async scheduling.

## Scheduling Model

`rotation_engine.py` is the scheduler of record.

- `SLOT_MINUTES = 5`
- `DISPLAY_SEQUENCE = ["pokemon", "weather", "joke", "science"]`
- Slot number = minutes since midnight divided by `5`
- Slot key format = `YYYY-MM-DD:<slot_number>`
- There are `288` slots per day
- Each category appears every `20` minutes
- Each category gets `72` slots per day

### Important nuance

The category rotates every `5` minutes, but the content freshness is category-specific:

| Category | Refresh cadence in practice | Persistence scope |
| --- | --- | --- |
| `pokemon` | Once per calendar day | DB-backed |
| `weather` | Each weather slot call | No DB cache |
| `joke` | Once per joke slot | DB-backed |
| `science` | Once per science slot | DB-backed |

That means the Pokémon shown at `00:00`, `00:20`, and `23:40` is the same for the whole day.

## Payload Contract

`main.build_content_for_now()` produces:

```python
{
    "slot_key": "YYYY-MM-DD:<slot>",
    "time": "YYYY-MM-DD HH:MM:SS",
    "category": "<pokemon|weather|joke|science>",
    "data": {...}
}
```

Category payload shapes:

| Category | Required fields used downstream |
| --- | --- |
| `pokemon` | `id`, `name`, `types`, `height`, `weight`, `hp`, `attack`, `defense`, `image_url` |
| `weather` | `location`, `temperature_f`, `weather_code`, `condition`, `wind_mph` |
| `joke` | `key`, `type`, plus either `text` or `setup` + `delivery` |
| `science` | `key`, `text`, `name`, `symbol`, `atomic_number`, `category` |

`display_manager.py` assumes those shapes directly. There is no schema object, validation layer, or typed DTO.

## Persistence Model

`content.db` is the only persistent store. `db_manager.init_db()` creates tables and adds missing columns opportunistically.

### Active Tables

#### `meta`

Current active keys:

- `pokemon_catalog_hash`
- `pokemon_catalog_size`
- `schema_version`

Only the Pokémon rotation currently uses `meta` at runtime.

#### `system_state`

This is a singleton table keyed by `id = 1`.

Active columns:

- `pokemon_pos`
- `pokemon_date`
- `current_pokemon_id`
- `current_joke_slot`
- `current_joke_id`
- `current_joke_type`
- `current_joke_text`
- `current_joke_setup`
- `current_joke_delivery`
- `current_science_slot`
- `current_science_key`
- `current_science_text`
- `current_science_name`
- `current_science_symbol`
- `current_science_atomic_number`

Inactive legacy columns still present:

- `last_date`
- `category_pos`
- `joke_pos`

Those legacy columns are created but are not read by current code.

#### `pokemon_rotation`

Stores a shuffled queue of Pokémon IDs:

- `position`
- `pokemon_id`

`pokemon_pos` in `system_state` points into this queue.

#### `used_jokes`

Stores historical joke keys to avoid repeats:

- `joke_key`
- `joke_type`
- `joke_text`
- `joke_setup`
- `joke_delivery`
- `first_seen_at`

This table grows monotonically under normal operation.

### Legacy / Unused Tables

Created by `init_db()` but unused by the current implementation:

- `category_rotation`
- `jokes_rotation`

Do not build new features on top of these tables unless you intentionally revive that abandoned design.

## Content Selection Logic

### Pokémon

Control path:

```text
main.build_content_for_now()
  -> rotation_engine.get_today_pokemon_id()
    -> _ensure_pokemon_rotation()
      -> apis.pokemon.get_valid_pokemon_ids()
      -> compare hash and row count
      -> possibly rewrite pokemon_rotation and reset pokemon state
    -> use system_state.pokemon_date/current_pokemon_id
    -> if same day: return cached ID
    -> else take pokemon_rotation[pokemon_pos]
    -> advance pokemon_pos
    -> reshuffle when queue wraps
  -> apis.pokemon.get_pokemon_data(id)
     or get_pokemon_fallback(id)
```

Properties:

- Stable for a full calendar day.
- Advances to the next Pokémon only when the date changes.
- Uses DB state, so restarts do not change today’s Pokémon.
- Refreshes the catalog from PokeAPI before checking daily state.

Non-obvious coupling:

- Catalog validation fetches the full Pokémon listing repeatedly.
- If the fetched catalog hash changes, the system rewrites `pokemon_rotation` and resets Pokémon state.
- If the API fails, `get_valid_pokemon_ids()` falls back to `1..1025`, which can also change the hash and trigger a reset.
- The renderer separately downloads the sprite/art image from `image_url`; Pokémon display therefore depends on both the PokeAPI JSON call and a second image URL fetch.

### Weather

Control path:

```text
main.build_content_for_now()
  -> apis.weather.get_weather_data()
     or get_weather_fallback()
```

Properties:

- No database persistence.
- Fresh fetch on each weather slot.
- If the process restarts during a weather slot, the weather payload can change inside the same slot.

### Joke

Control path:

```text
main.build_content_for_now()
  -> rotation_engine.get_current_joke()
    -> if current_joke_slot matches: return cached DB payload
    -> else try up to 10 JokeAPI fetches
    -> reject jokes already in used_jokes
    -> store selected joke
    -> persist current slot payload in system_state
    -> fallback to synthetic backup joke if needed
```

Properties:

- Stable for the duration of a joke slot.
- Resistant to duplicates across restarts because uniqueness is DB-backed.
- Over time, `used_jokes` can make selection harder; after 10 failed/duplicate attempts the code falls back to a fixed backup joke.

### Science

Control path:

```text
main.build_content_for_now()
  -> rotation_engine.get_current_science_fact()
    -> if current_science_slot matches: return cached DB payload
    -> else apis.science.get_random_science_fact()
       or get_science_fact_fallback()
    -> persist chosen fact in system_state
```

Properties:

- Stable for the duration of a science slot.
- No long-term dedupe across slots or days.
- Under the hood, `apis/science.py` caches the full element list in memory for the life of the process.

## Rendering and Hardware Path

`display_manager.py` is responsible for all visual output and most user-visible timing.

### Rendering Stack

```text
payload
  -> category-specific renderer
  -> PIL Image frame(s)
  -> _prepare_image()
  -> optional matrix push
  -> optional preview save
```

### Category Rendering Behavior

| Category | Behavior |
| --- | --- |
| `pokemon` | Intro title, then art + stat overlays cycled with fades |
| `weather` | Static icon + scrolling ticker |
| `joke` | Paginates lines into up to 3 lines per page; two-part jokes split setup and punchline into separate segments |
| `science` | Static centered text with name, symbol, and atomic number |

### Important Display Couplings

- `numpy` is imported at module import time, not only when hardware mode is enabled.
- `piomatter` is optional, but `numpy` is effectively mandatory in the current implementation even for `--simulate`.
- In this inspected environment, `python main.py --once --simulate` fails because `numpy` is missing.
- `DisplayManager` mixes rendering, network I/O, animation timing, preview writing, and hardware writes in one class.
- `_render_pokemon_base()` downloads artwork during rendering. Rendering is therefore impure and network-dependent.

### Orientation Pipeline

There are two separate orientation transforms:

1. `_prepare_image()` optionally rotates by `180` degrees when `GLOBAL_ROTATE_180 = True`
2. `_push_prepared()` flips the final array vertically and horizontally before writing to the framebuffer

Treat the hardware orientation as already encoded in this combination. Do not “simplify” it without testing on real hardware.

## CLI Semantics

Flags are parsed by raw string membership in `sys.argv`; there is no `argparse`.

Supported flags:

- `--simulate`: skip matrix initialization
- `--save-previews`: save rendered frames under `preview_frames/`
- `--once`: execute one payload cycle instead of the endless loop

### Important nuance

`--once` does not mean “render a single frame and exit” for all categories.

- For `pokemon`, `weather`, and `joke`, `display_payload()` defaults to `300` seconds when no explicit duration is supplied.
- For `science`, `display_payload()` shows one transitioned frame and exits quickly.

So `--once` is currently closer to “run one content program” than “perform one cheap snapshot.”

## External Dependencies

### Python Packages

Expected imports:

- `Pillow`
- `numpy`
- `adafruit_blinka_raspberry_pi5_piomatter` on hardware deployments

There is no dependency manifest in the repository right now.

### Network Endpoints

- PokeAPI: `https://pokeapi.co/api/v2`
- Open-Meteo: `https://api.open-meteo.com/v1/forecast`
- JokeAPI: `https://v2.jokeapi.dev/joke/Any?...`
- Periodic table API: `https://neelpatel05.github.io/periodic-table-api/api/v1/element.json`
- Pokémon artwork URLs returned by PokeAPI

All adapters use simple `urllib.request` retry loops with up to three attempts.

## Repository State Observed During Inspection

The checked-in `content.db` is populated.

Observed in this checkout:

- `pokemon_rotation` contained `1350` rows
- `used_jokes` contained `44` rows
- `category_rotation` and `jokes_rotation` were empty
- `system_state` had persisted current joke/science payloads from `2026-03-13`
- `meta.schema_version` was still `3`, even though `init_db()` inserts `4` only when missing

Interpretation:

- The database has evolved in place.
- `schema_version` is not a reliable migration mechanism in the current code.
- The checked-in DB is useful for understanding behavior, but not authoritative for schema intent.

## Coupling and Risk Map

### Tight Couplings

- `main.py` depends directly on the payload shapes returned by both `rotation_engine.py` and `apis/*.py`
- `display_manager.py` depends on category-specific payload field names with no validation layer
- `rotation_engine.py` is coupled to SQLite schema details and adapter behavior
- Pokémon rendering is coupled to live network image fetches
- The scheduler is coupled to local wall-clock time via `datetime.now()`

### Operational Assumptions

- One writer process owns `content.db`
- The process is started from the repository root, or at least from a directory where relative `content.db` is intended
- Network access may fail, so all categories except the display shell require fallbacks
- Real matrix orientation has been tuned empirically, not abstracted cleanly

### Sharp Edges

- Missing `numpy` prevents startup even with `--simulate`
- Database schema drift is handled by “add column if missing,” not by a formal migration framework
- Pokémon catalog fetch failure can rewrite the stored rotation to the fallback catalog
- `used_jokes` never expires entries
- Science facts can repeat across slots because they are random with only slot-level caching

## If You Need To Change The System

### Adding a New Category

You will need to touch all of the following:

- `rotation_engine.DISPLAY_SEQUENCE`
- `main.build_content_for_now()`
- `main.print_payload()`
- `display_manager.render_payload()` and likely `display_manager.display_payload()`
- `db_manager.init_db()` if the new category needs persistence
- Possibly `rotation_engine.py` if the category must be slot-stable or restart-stable

Do not add a category in only one layer. The code assumes the category enum is manually synchronized across modules.

### Refactor Priorities That Actually Matter

If you are improving maintainability, the highest-value changes are:

1. Split pure rendering from hardware output and network sprite fetches
2. Make simulation mode independent of `numpy` and `piomatter`
3. Replace ad hoc DB migration with an explicit schema version upgrade path
4. Separate content selection policy from persistence primitives
5. Add tests around slot math and state transitions in `rotation_engine.py`

### Safe Areas for Local Refactors

- API adapters are isolated and easy to replace
- Slot math in `rotation_engine.py` is compact and testable
- Rendering helpers in `display_manager.py` can be extracted if payload shapes remain stable

### Areas To Touch Carefully

- `get_today_pokemon_id()` because it combines catalog sync, queue rotation, and daily caching
- `display_payload()` because user-visible timing depends on it
- `system_state` column semantics because multiple categories share the same singleton row

## What Is Not In This Repository

- No tests
- No dependency file
- No service wrapper
- No deployment scripts
- No meaningful existing documentation beyond the code

The empty `README.md`, `ARCHITECTURE.md`, and `CONTRIBUTING.md` should not be treated as sources of truth.
