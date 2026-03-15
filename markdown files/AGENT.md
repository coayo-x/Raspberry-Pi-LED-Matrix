# AGENT.md

## Purpose

This repository is a single-process Python application that rotates content on a `64x32` RGB LED matrix attached to a Raspberry Pi. It is not a web service, not event-driven, and not multi-process. The runtime model is:

1. determine the current 5-minute slot from local wall-clock time
2. build one category payload for that slot
3. render and animate that payload for most or all of the slot
4. repeat

Persistent state lives in SQLite (`content.db`). That database is part of the runtime behavior, not just storage. Daily Pokemon rotation, joke dedupe, slot-stable joke selection, and slot-stable science selection all depend on DB state surviving restarts.

The checked-in `content.db` is mutable runtime state, not a fixture. It is already populated and may contain stale cached slot data from an earlier run.

## Repository Map

Top-level files and directories that matter:

| Path | Purpose |
| --- | --- |
| `main.py` | Entry point, CLI flag parsing, main loop, payload assembly, console logging |
| `rotation_engine.py` | Slot math plus stateful content selection for Pokemon, jokes, and science |
| `db_manager.py` | SQLite connection setup and schema bootstrap |
| `display_manager.py` | Rendering, animation, preview writing, and matrix framebuffer output |
| `apis/pokemon.py` | PokeAPI catalog + Pokemon detail adapter |
| `apis/weather.py` | Open-Meteo adapter |
| `apis/jokes.py` | JokeAPI adapter |
| `apis/science.py` | Periodic table adapter with in-process cache |
| `content.db` | Runtime database, committed into the repo |
| `Notes/systemd.md` | Manual `systemctl` commands only; not a unit file |
| `.github/workflows/pylint.yml` | Basic lint workflow on push |
| `README.md` | Title only |
| `ARCHITECTURE.md` | Empty |
| `CONTRIBUTING.md` | Empty |

`__init__.py` is empty and `apis/__init__.py` is only a package marker.

## System Architecture

```text
                         +----------------------+
                         |       main.py        |
                         | CLI + slot loop      |
                         +----------+-----------+
                                    |
                      build_content_for_now(now)
                                    |
            +-----------------------+-----------------------+
            |                       |                       |
            v                       v                       v
 +---------------------+  +----------------------+  +----------------------+
 |  rotation_engine.py |  |      apis/*.py       |  |  display_manager.py  |
 | slot math + state   |  | network adapters     |  | render + animate     |
 +----------+----------+  +----------------------+  +----------+-----------+
            |                                                 |
            v                                                 v
 +---------------------+                           +------------------------+
 |    db_manager.py    |                           | PIL images + optional  |
 | SQLite bootstrap    |                           | piomatter framebuffer  |
 +----------+----------+                           +------------------------+
            |
            v
 +---------------------+
 |     content.db      |
 | persisted runtime   |
 +---------------------+
```

### Module responsibilities

| Module | Responsibility | Notes |
| --- | --- | --- |
| `main.py` | Top-level orchestration only | Does not own persistence or rendering details |
| `rotation_engine.py` | Canonical slot/category math and persisted content selection | This is the core domain module |
| `db_manager.py` | Connection defaults and best-effort schema bootstrap | Uses add-column-if-missing, not versioned migrations |
| `display_manager.py` | Visual composition, animation timing, preview output, hardware writes | Also performs Pokemon artwork downloads |
| `apis/pokemon.py` | Pokemon catalog fetch and per-Pokemon detail mapping | Provides fallback ID range `1..1025` |
| `apis/weather.py` | Current weather fetch and condition mapping | Default location is Erie, PA |
| `apis/jokes.py` | Safe-mode random joke fetch | Returns normalized single/twopart payloads |
| `apis/science.py` | Random periodic-table element facts | Caches the full element list in memory for the life of the process |

## Runtime Control Flow

### Boot path

```text
python main.py [flags]
  -> main()
     -> args = set(sys.argv[1:])
     -> DisplayManager(use_matrix=..., save_previews=...)
     -> run_once(...) or run_forever(...)
```

Important consequence: `DisplayManager` is constructed before any DB work. If `display_manager.py` cannot import its dependencies, the program fails before `init_db()` runs.

### `run_once()`

```text
run_once(display, now=None)
  -> init_db()
  -> payload = build_content_for_now(now or datetime.now())
  -> print_payload(payload)
  -> display.display_payload(payload)
  -> return payload
```

### `run_forever()`

```text
run_forever(display, boot_delay=10)
  -> init_db()
  -> sleep(boot_delay)
  -> last_slot_key = None
  -> while True:
       now = datetime.now()
       slot_key = get_current_slot_key(now)
       if slot_key != last_slot_key:
         payload = build_content_for_now(now)
         print_payload(payload)
         duration = seconds_until_next_slot(now)
         display.display_payload(payload, duration_seconds=duration)
         last_slot_key = slot_key
       else:
         sleep(1)
```

Key runtime properties:

- Startup in the middle of a slot renders the current slot immediately because `last_slot_key` starts as `None`.
- Rendering is blocking. There are no worker threads, no async tasks, and no background prefetching.
- Slot timing is best-effort rather than hard real-time. Display routines sleep internally and may overrun the exact slot boundary by transition or animation overhead.
- `print_payload()` is the only built-in observability path besides previews.

## Slot Scheduling Logic

`rotation_engine.py` is the scheduler of record.

- `SLOT_MINUTES = 5`
- `DISPLAY_SEQUENCE = ["pokemon", "weather", "joke", "science"]`
- slot number = `((hour * 60) + minute) // 5`
- slot key format = `YYYY-MM-DD:<slot_number>`
- there are `288` slots per day
- each category appears every `20` minutes
- each category receives `72` slots per day
- `seconds_until_next_slot()` returns at least `1`, never `0`

Category selection is purely time-based. The database does not decide which category is active. The `category_rotation` table is legacy and unused.

### Category freshness and stability

| Category | Selection function | Refresh cadence | Stable within a slot | Stable across restart | Long-term dedupe |
| --- | --- | --- | --- | --- | --- |
| `pokemon` | `get_today_pokemon_id()` + `apis.pokemon.get_pokemon_data()` | once per local calendar day | yes | yes | queue-based daily rotation |
| `weather` | `apis.weather.get_weather_data()` | every weather payload build | no | no | none |
| `joke` | `get_current_joke()` | once per joke slot | yes | yes | `used_jokes` table |
| `science` | `get_current_science_fact()` | once per science slot | yes | yes | none |

### Pokemon rotation details

Pokemon selection is more than "pick a random Pokemon":

```text
get_today_pokemon_id()
  -> connect()
  -> _ensure_pokemon_rotation()
       -> get_valid_pokemon_ids()
       -> normalize to sorted unique IDs
       -> hash catalog
       -> compare with stored hash and current table row count
       -> if changed: rewrite pokemon_rotation, update meta, reset Pokemon state
  -> read system_state singleton row
  -> if pokemon_date == today and current_pokemon_id is set:
       return cached current_pokemon_id
  -> else:
       read pokemon_rotation[pokemon_pos]
       update pokemon_date/current_pokemon_id
       advance pokemon_pos
       reshuffle whole table on wraparound
       commit
       return selected ID
```

Important implementation details:

- The Pokemon shown for all Pokemon slots on the same day is the same Pokemon.
- `pokemon_rotation` stores a full shuffled queue of valid IDs.
- `pokemon_pos` points to the next queue position to use on the next day change.
- When the queue wraps, the table is reshuffled. `_shuffle_copy(..., avoid_first=current_pokemon_id)` makes a best effort to avoid immediately repeating the just-shown Pokemon, but it is not a guarantee.
- `_ensure_pokemon_rotation()` compares the fetched catalog hash and the actual table row count. It does not read `meta.pokemon_catalog_size`.
- `apis.pokemon.get_valid_pokemon_ids()` never raises to callers; on any failure it returns the hardcoded fallback range `1..1025`.
- The checked-in DB currently reflects a live catalog size of `1350`. If the API is unavailable during `_ensure_pokemon_rotation()`, the fallback `1..1025` list can change the hash and cause the app to rewrite `pokemon_rotation`, shrink the stored catalog, and reset Pokemon state.

### Joke slot details

```text
get_current_joke()
  -> current slot key
  -> read system_state
  -> if current_joke_slot matches:
       return cached joke payload
  -> else:
       try up to 10 JokeAPI fetches
       reject any candidate whose key already exists in used_jokes
       if all attempts fail or duplicate:
         use synthetic fallback joke
       insert joke into used_jokes
       persist current joke fields into system_state
       commit
       return selected joke
```

Notes:

- Joke uniqueness is keyed only by `joke_key`.
- JokeAPI-backed keys look like `jokeapi:<id>` when an API `id` is present.
- Fallback jokes use key `fallback:<slot_key>`, so the same fallback text can be inserted repeatedly across different slots.
- `used_jokes` only grows. There is no retention or cleanup path.

### Science slot details

```text
get_current_science_fact()
  -> current slot key
  -> read system_state
  -> if current_science_slot matches:
       return cached science payload reconstructed from stored columns
  -> else:
       get_random_science_fact() or get_science_fact_fallback()
       persist selected fact fields into system_state
       commit
       return fact
```

Notes:

- Science facts are slot-stable but not deduped across slots or days.
- `apis/science.py` caches the full element list in memory after the first successful or fallback load.
- Only display-relevant science fields are persisted. If a freshly fetched fact carries extra keys such as `_fallback`, those extra keys are lost on subsequent cached reads.
- Cached reads always reconstruct `category: "element"` regardless of the original adapter payload.

## Payload Contract

`main.build_content_for_now()` always returns:

```python
{
    "slot_key": "YYYY-MM-DD:<slot>",
    "time": "YYYY-MM-DD HH:MM:SS",
    "category": "<pokemon|weather|joke|science>",
    "data": {...},
}
```

There is no schema object, validator, dataclass, or typed DTO layer. `main.py`, `rotation_engine.py`, and `display_manager.py` all assume raw dict shapes.

### Category payload shapes

| Category | Fields produced | Fields actually consumed downstream |
| --- | --- | --- |
| `pokemon` | `id`, `name`, `types`, `height`, `weight`, `hp`, `attack`, `defense`, `image_url` | renderer uses everything except `id`; console output prints all of them |
| `weather` | `location`, `temperature_f`, `weather_code`, `condition`, `wind_mph` | renderer uses `location`, `temperature_f`, `condition`, `wind_mph`; `weather_code` is informational only |
| `joke` | `key`, `type`, plus `text` or `setup` + `delivery` | renderer uses `type`, `text`, `setup`, `delivery`; `key` is persistence-only |
| `science` | `key`, `text`, `name`, `symbol`, `atomic_number`, `category` | renderer uses `name`, `symbol`, `atomic_number`; console output prints `text`; cached reads hardcode `category` to `"element"` |

Payload asymmetries that matter:

- `render_payload()` is only a still-image helper. For animated categories it does not represent the full on-matrix behavior.
- `render_payload("joke")` returns only the first joke page.
- `render_payload("weather")` returns the header/icon frame without the scrolling ticker text.
- `render_payload("pokemon")` returns the first base/name frame, not the intro or the stat cycle.

## Database Schema and Persistence

`db_manager.connect()` applies the same connection behavior everywhere:

- row factory = `sqlite3.Row`
- `PRAGMA foreign_keys = ON`
- `PRAGMA journal_mode = WAL`

The schema is created and patched by `db_manager.init_db()`. There is no migration framework. Existing databases are updated by checking column existence and issuing `ALTER TABLE ... ADD COLUMN ...` when needed.

### Default DB path

- default DB file is relative path `content.db`
- all callers rely on that default unless they explicitly pass `db_path`
- starting the app from a different working directory changes which DB file is used

### Active tables

#### `meta`

Columns:

- `key TEXT PRIMARY KEY`
- `value TEXT NOT NULL`

Observed and used keys:

| Key | Written by | Read by | Notes |
| --- | --- | --- | --- |
| `schema_version` | `init_db()` inserts `'4'` only if missing | nobody | not authoritative for migrations |
| `pokemon_catalog_hash` | `_ensure_pokemon_rotation()` | `_ensure_pokemon_rotation()` | actual runtime control value |
| `pokemon_catalog_size` | `_ensure_pokemon_rotation()` | nobody | informational only |

The checked-in DB still has `schema_version = 3`, which confirms that the value is not kept in sync once the key exists.

#### `system_state`

Singleton table keyed by `id = 1`.

Columns actively used by current code:

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

Legacy columns still created but unused by current runtime:

- `last_date`
- `category_pos`
- `joke_pos`

#### `pokemon_rotation`

Queue table for the Pokemon daily rotation:

- `position INTEGER PRIMARY KEY`
- `pokemon_id INTEGER NOT NULL`

Rows are replaced wholesale when:

- the Pokemon catalog hash changes
- the stored row count no longer matches the fetched catalog size
- the queue wraps and a reshuffle is performed

#### `used_jokes`

Historical joke ledger:

- `joke_key TEXT PRIMARY KEY`
- `joke_type TEXT NOT NULL`
- `joke_text TEXT`
- `joke_setup TEXT`
- `joke_delivery TEXT`
- `first_seen_at TEXT NOT NULL`

This table is append-only in normal operation.

### Legacy tables

These tables are created by `init_db()` but are unused by the current codebase:

- `category_rotation`
- `jokes_rotation`

Do not build new behavior on them unless you intentionally revive that abandoned design.

## Display and Rendering Pipeline

`display_manager.py` owns everything from payload-to-pixels.

### Import-time dependencies

`display_manager.py` imports these at module import time:

- `numpy`
- `PIL` / Pillow
- optionally `adafruit_blinka_raspberry_pi5_piomatter`

Implications:

- `numpy` and Pillow are required even when running with `--simulate`
- `piomatter` is optional; if it is missing, `DisplayManager(..., use_matrix=True)` silently degrades to `use_matrix=False`
- there is no dependency manifest in the repo, so dependency installation is external to the codebase

### Rendering pipeline

```text
payload
  -> category-specific render/animation helper
  -> PIL RGBA frame(s)
  -> _prepare_image()
       -> convert RGBA
       -> resize to 64x32 with NEAREST
       -> optional 180-degree rotate
  -> _push_prepared()
       -> numpy array conversion
       -> vertical + horizontal flip
       -> matrix.show() if matrix enabled
  -> _save_prepared() if previews enabled
```

`last_frame` is preserved across calls so transitions cross-fade from the previous content instead of always starting from black.

### Category display behavior

| Category | Actual display behavior |
| --- | --- |
| `pokemon` | title intro, then Pokemon image/name frame, then animated stat overlays with fade-in/hold/fade-out loops |
| `weather` | weather icon + header + horizontally scrolling ticker |
| `joke` | text is wrapped, paginated to 3 lines per page, and shown as one or two segments depending on joke type |
| `science` | one centered still frame with element name, symbol, and atomic number |

#### Pokemon rendering details

- Pokemon artwork is downloaded inside `DisplayManager` from `data["image_url"]`.
- That artwork fetch is a separate network call from the PokeAPI JSON request.
- Unlike the API adapters, `_download_image()` has no retry loop and no caching.
- If the image download fails, the renderer draws `NO IMG` in the art box.
- Long Pokemon names scroll horizontally by generating a list of frames.

#### Weather rendering details

- The weather icon is chosen from the human-readable `condition` string, not `weather_code`.
- The renderer does not use `is_day`; the adapter requests it but discards it.
- The scrolling ticker string is built as:

```text
<location> | <condition> | <temperature>F | Wind <wind> mph
```

#### Joke rendering details

- Joke pages are centered text pages with up to 3 lines each.
- Twopart jokes render setup pages in `TEXT_PRIMARY` and delivery pages in `TEXT_ACCENT`.
- Each segment is shown for up to 10 seconds before moving to the next segment.

#### Science rendering details

- Science display ignores `data["text"]` and uses only `name`, `symbol`, and `atomic_number`.
- `display_payload()` treats science as a still image plus optional slot sleep, not a custom animation loop.

### Preview behavior

- Previews are written only when `save_previews=True` / `--save-previews`.
- Files are saved after the orientation transforms in `_prepare_image()`.
- Animated categories often overwrite the same preview filename repeatedly.
- Previews are snapshots of key frames, not a complete frame-by-frame capture of the animation.

### Orientation behavior

There are two separate orientation transforms:

1. `_prepare_image()` rotates the frame by 180 degrees when `GLOBAL_ROTATE_180 = True`
2. `_push_prepared()` then applies `np.flipud(np.fliplr(arr))`

Treat the current output orientation as empirically tuned. Do not simplify those transforms without testing on real hardware.

### Pillow coupling

`render_scrolling_text()` reads `draw._image`, which is a private Pillow implementation detail. That helper is coupled to Pillow internals rather than only public APIs.

## External APIs and Adapter Behavior

All adapters use `urllib.request` with the same user-agent string and up to 3 retries, except the Pokemon artwork downloader in `display_manager.py`.

### Pokemon API

- base URL: `https://pokeapi.co/api/v2`
- catalog endpoint: `/pokemon?limit=2000&offset=0`
- detail endpoint: `/pokemon/<id>`
- live catalog IDs are extracted from result URLs via regex
- detail payload is normalized to title-cased name/types plus selected stats and artwork URL
- fallback returns placeholder values and `image_url = None`

### Weather API

- base URL: `https://api.open-meteo.com/v1/forecast`
- default coordinates: `42.1292, -80.0851`
- default location label: `Erie, PA`
- query asks for `temperature_2m`, `weather_code`, `is_day`, `wind_speed_10m`
- response is normalized to Fahrenheit and mph
- `WEATHER_CODES` maps numeric codes to display strings
- fallback returns placeholder values and `"Weather unavailable"`

### Joke API

- endpoint: `https://v2.jokeapi.dev/joke/Any?safe-mode&type=single,twopart`
- rejects API responses marked with `error`
- normalizes single and twopart formats into the repository's internal shape
- if API `id` is missing, a SHA-256 hash of the content is used as a synthetic key

### Science API

- endpoint: `https://neelpatel05.github.io/periodic-table-api/api/v1/element.json`
- expected response is a JSON array of element objects
- first successful load is cached in module-level `_elements_cache`
- fallback uses a small hardcoded list of elements
- runtime only uses the `get_random_science_fact` alias, which points to `get_random_element_fact()`
- `get_element_by_number()` exists but is not used by the application

## CLI Flags and Runtime Modes

Flags are parsed by raw membership checks in `sys.argv`. There is no `argparse`, no flag validation, and no support for flag values.

Supported flags:

- `--simulate`: request preview-only mode by disabling matrix initialization
- `--save-previews`: write preview images under `preview_frames/`
- `--once`: build and display one payload cycle, then return

Behavior details:

- unknown flags are ignored
- `run_forever()` applies a default `boot_delay=10`; `run_once()` does not
- `--simulate` still requires `display_manager.py` import dependencies
- `--save-previews` creates `preview_frames/` relative to the working directory

### `--once` is category-sensitive

`run_once()` calls `display.display_payload(payload)` without an explicit duration. `display_payload()` then behaves differently by category:

| Category | `duration_seconds` used | Practical result |
| --- | --- | --- |
| `pokemon` | defaults to `300` | runs the full Pokemon program for about 5 minutes |
| `weather` | defaults to `300` | runs the ticker for about 5 minutes |
| `joke` | defaults to `300` | runs joke paging for about 5 minutes |
| `science` | no custom animation loop | transitions to one frame and returns almost immediately |

So `--once` means "run one category program", not "render one cheap snapshot."

## Known Limitations and Design Couplings

### Tight couplings

- `main.py` is coupled to raw payload dict shapes and category names.
- `rotation_engine.py` is coupled directly to SQLite schema details.
- `display_manager.py` is coupled directly to category-specific payload fields.
- Pokemon rendering is coupled to an extra image URL fetch performed during rendering.
- Scheduling is coupled to local system time and local calendar date.

### Current limitations

- one process should own `content.db`; there is no explicit multi-writer coordination strategy
- DB migrations are ad hoc add-column patches; `schema_version` is not used as a real migration driver
- relative default DB path means launching from a different directory can create or use the wrong database
- `used_jokes` has no pruning strategy
- science facts can repeat across slots because there is no long-term dedupe
- weather payloads are not cached, so repeated builds in the same slot can differ
- `render_payload()` is not a drop-in substitute for real display behavior on animated categories
- dependency installation is undocumented in-repo; there is no `requirements.txt`, `pyproject.toml`, or equivalent
- `.github/workflows/pylint.yml` is lint-only and does not document or install runtime dependencies
- `Notes/systemd.md` documents manual service commands but the repository does not include the actual `led-matrix.service` unit file

### Legacy or unused code paths

- `category_rotation` table: unused
- `jokes_rotation` table: unused
- `system_state.last_date`: unused
- `system_state.category_pos`: unused
- `system_state.joke_pos`: unused
- `apis.pokemon.get_total_pokemon()`: unused
- `apis.science.get_element_by_number()`: unused by runtime

## If You Need To Change The System

### Adding a new category

A real new category requires synchronized changes in multiple modules:

1. add the category name to `rotation_engine.DISPLAY_SEQUENCE`
2. teach `main.build_content_for_now()` how to build its payload
3. update `main.print_payload()` for console output
4. add render/display support in `display_manager.py`
5. extend `db_manager.init_db()` and `rotation_engine.py` if the category needs slot-stable or restart-stable persistence

Do not change only one layer. Categories are manually coordinated across the repo.

### Safe refactor targets

- API adapters are isolated and easy to swap or test
- slot math in `rotation_engine.py` is compact and easy to unit test
- rendering helpers in `display_manager.py` can be extracted if payload shapes remain stable

### Areas to touch carefully

- `get_today_pokemon_id()` because it combines catalog sync, queue management, and daily caching
- `display_payload()` because its timing behavior defines the visible runtime
- `system_state` semantics because several categories share one singleton row
- orientation logic in `display_manager.py` because the current transform stack is hardware-tuned

## Primary Source Of Truth

For this repository, the real source of truth is the Python code plus the runtime database behavior described above.

Secondary repo docs are currently minimal:

- `README.md` only contains the project title
- `ARCHITECTURE.md` is empty
- `CONTRIBUTING.md` is empty

Use this file and the implementation as the authoritative developer reference.
