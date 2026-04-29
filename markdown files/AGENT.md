# AGENT.md

## Purpose

This repository drives a Raspberry Pi LED matrix and a local web dashboard.
The runtime rotates external content on a 192x32 RGB matrix, supports DB-backed
operator controls, supports temporary custom text, and includes an admin-only
Snake game mode.

Treat the current code as the source of truth. Runtime state is stored in a
local SQLite database at `DB_PATH` from `.env` or `content.db` by default.
Database files, preview frames, local moderation lists, caches, and other
runtime artifacts are intentionally ignored by git.

## Main Entry Points

| Path | Role |
| --- | --- |
| `main.py` | Runtime CLI, rotation loop, one-shot simulation, and display handoff. |
| `display_manager.py` | PIL/numpy rendering and optional hardware matrix output. |
| `dashboard_server.py` | Threaded HTTP dashboard server and JSON API routes. |
| `db_manager.py` | SQLite schema creation, connections, metadata helpers, and state tables. |
| `runtime_control.py` | DB-backed skip, switch, locks, cooldowns, and custom-text force controls. |
| `rotation_engine.py` | Slot-based category selection and per-slot content selection. |
| `custom_text.py` | Public/admin custom text validation, moderation, style normalization, and storage. |
| `current_display_state.py` | Normalized dashboard snapshot table for what the runtime is showing. |
| `admin_auth.py` | Admin password verification, login throttling, and DB-backed sessions. |
| `snake_control.py` | Admin API helpers and DB state for Snake mode/input. |
| `snake_game.py` | Snake game loop, levels, rendering payloads, controls, and score state. |
| `apis/` | Weather, Pokemon, joke, and science API clients with fallbacks. |
| `dashboard_assets/` | Dashboard HTML, CSS, JavaScript, and icon. |
| `systemd/` | Example runtime and dashboard unit files. Review before installing. |
| `tests/` | Pytest coverage for runtime controls, dashboard APIs, display behavior, custom text, auth, snapshots, and Snake. |

## Runtime Flow

`main.py` parses CLI flags and constructs `DisplayManager` before running either
`run_once` or `run_forever`.

`python main.py --simulate --once` initializes the DB, builds one payload, saves
the dashboard snapshot, prints the payload, and renders for one second. If Snake
mode is already enabled, the one-shot path renders a Snake waiting screen
instead of normal content.

The long-running loop uses this priority order:

1. Snake mode, if enabled in the DB.
2. Forced custom text, if admin force is enabled and an override exists.
3. Active timed custom text.
4. Normal slot rotation.

Normal rotation is slot-based. `rotation_engine.DISPLAY_SEQUENCE` is:

```text
pokemon -> weather -> joke -> science
```

The slot index is derived from local seconds since midnight divided by
`ROTATION_INTERVAL`. Slot keys use `YYYY-MM-DD:<slot>`. Content selection is
stable inside a slot where the code stores state in SQLite.

Skip and switch controls are consumed from the DB while a normal slot is active.
If both are pending, the runtime checks switch first, then skip. Skip advances
from the currently active category to the next item in `DISPLAY_SEQUENCE`.
Switch requests target an explicit category.

The dashboard snapshot is saved before display rendering begins. A render or
hardware failure after that point can leave the dashboard showing the intended
payload rather than a confirmed visible frame.

## Database And Runtime Control

`db_manager.connect()` enables foreign keys, uses WAL mode, and initializes the
schema once per normalized DB path in the current process. Core runtime data is
stored in these tables:

- `meta`: general key/value state for controls, Snake mode, custom text, and
  counters.
- `current_display_state`: normalized dashboard snapshot.
- `pokemon_rotation`: stable daily Pokemon order.
- `used_jokes`: per-slot joke tracking.
- `admin_sessions`: hashed admin session tokens.
- `admin_login_attempts`: schema exists, but current throttling is in memory.
- `system_state`, `category_rotation`, and `jokes_rotation`: legacy or lightly
  used state kept by the schema.

`runtime_control.py` stores skip/switch counters, requested categories, locks,
cooldowns, and the custom-text force flag in `meta`. Public controls are blocked
while Snake mode is active, while custom text is active or forced, or while an
admin lock/cooldown applies. Admin override bypasses public locks and cooldowns,
but it does not bypass Snake/custom-text blocking.

`config.py` reads environment values at import time. Later `.env` changes do
not affect already-imported modules.

## Custom Text

Custom text is stored as JSON in the `meta` key `custom_text_override`.
Validation and normalization are handled in `custom_text.py`.

Current behavior:

- Text is required, trimmed, length-limited, and checked against
  `badwordslist.txt` when that local ignored file exists.
- Public custom text is blocked when admin locks it, when Snake mode is active,
  or during its short cooldown.
- Admin routes can override the public lock.
- Duration is normalized to 5-300 seconds.
- Styles are normalized for bold, italic, underline, font family, font size,
  text/background brightness, text/background color, and alignment.
- Admin force mode keeps the stored override on screen outside the normal timer
  until force is disabled or the override is removed.

## Snake Game Mode

Snake is controlled through admin dashboard APIs and DB `meta` keys. Enabling
Snake resets mode state, score, level, direction, and pending inputs. While
enabled, Snake blocks normal rotation and custom text submission.

The game loop in `snake_game.py` uses a 2-pixel cell grid over the 192x32
matrix. It has waiting, level intro, playing, paused, and game over phases.
The first movement control starts a level intro. Pause toggles during play.
After game over, any control restarts the current level. Score, level, phase,
and active direction are mirrored into DB state for the dashboard.

Levels add obstacles and speed pressure. Food and obstacles avoid the score
notch/reserved HUD area.

## Display And Rendering

`DisplayManager` renders with PIL and converts frames to numpy arrays. Hardware
output uses `adafruit_blinka_raspberry_pi5_piomatter` when `use_matrix=True`;
if that backend is missing, hardware mode raises at initialization. Simulation
mode avoids hardware setup.

Matrix geometry is fixed in code as 192x32: three chained 64x32 panels.
Rendered frames are resized with nearest-neighbor scaling, rotated 180 degrees,
then flipped before `matrix.show()`. Preview images are saved after the rotate
step but before the final hardware framebuffer flips.

Category rendering is animated for Pokemon, weather, jokes, custom text, and
Snake. Science currently renders as a mostly static information panel.
`DisplayManager.render_payload()` is a static helper used by tests and callers;
it does not exercise every animated runtime path.

Pokemon artwork is fetched during rendering. API/content fetch latency can
therefore affect display timing, not just payload construction.

## Dashboard And Admin Flow

`dashboard_server.py` uses `ThreadingHTTPServer` and static assets in
`dashboard_assets/`. The main page polls:

- `/api/current-display-state`
- `/api/control-state`

Public actions include skip, switch, and custom text submission. Protected
actions include admin login/logout, lock toggles, forced custom text stop/force,
and Snake mode controls. The force-custom-text endpoint is currently
`/admin/custom-text/force`, while most other admin endpoints are under
`/api/admin/...`.

`dashboard_assets/dashboard.js` keeps the live UI in sync with the current
snapshot, control state, admin session state, custom-text form state, and Snake
controls. Keyboard Snake input is sent only while the user is admin-authenticated,
Snake mode is enabled, and focus is not in a text input.

`admin_auth.py` supports bcrypt password hashes and a PBKDF2 fallback/legacy
format. Sessions are stored as SHA-256 token hashes in SQLite. Login throttling
is process-local memory. The `admin_login_attempts` table and
`ADMIN_LOGIN_MAX_ATTEMPTS` / `ADMIN_LOGIN_LOCKOUT_SECONDS` config values are not
used by the current throttling implementation.

## External Content

- Weather uses Open-Meteo with a default location of Erie, PA. It requests
  current weather and forecast fields.
- Pokemon uses PokeAPI species/catalog/detail/artwork endpoints with fallback
  IDs `1..1025`.
- Jokes use JokeAPI safe mode with a static fallback joke.
- Science uses a periodic table JSON endpoint, caches the element list in memory,
  and has a local fallback element list.

Network failures generally fall back to local or generic content so the display
can continue.

## Tests And Validation

The test suite is pytest-based and currently covers:

- admin auth and dashboard auth routes
- dashboard server APIs
- runtime control counters, locks, cooldowns, and blocking behavior
- main runtime control integration
- current display state normalization
- custom text validation and rendering behavior
- display-manager initialization, pixels, wrapping, and static rendering helpers
- Snake DB controls and game behavior

`pytest.ini` sets `testpaths = tests` and disables pytest's cache provider.
The GitHub Actions workflow installs requirements and runs ruff, black, and
pytest, but all three commands are currently followed by `|| true`, so CI reports
success even when checks fail.

## Deployment Notes

The `systemd/` directory contains sample units for the matrix runtime and
dashboard. The files currently include duplicated deployment-specific directives
for different users and paths. Review and simplify them for the target host
before installing.

`Notes/systemd.md` exists as additional deployment notes, but it is duplicated
and should not be treated as authoritative without checking the current service
files and code.

## Change Guidance

- Keep runtime behavior coordinated through the DB helpers instead of ad hoc
  writes to SQLite.
- Update tests when changing category payloads, dashboard API contracts, custom
  text behavior, or Snake controls.
- Be careful with import-time config in tests; modules may need reloads when
  environment values change.
- Do not rely on local runtime artifacts such as `content.db`, preview frames,
  or `badwordslist.txt` being present in a fresh checkout.
- Current risks and stale historical findings are tracked in `BUGS.md`.
