# BUGS.md

## Scope

This file reflects the repository state reviewed on 2026-04-29. It separates
current risks from stale historical issues. The code is the source of truth.

## Highest Priority Current Risks

1. `systemd/led-matrix.service` and `systemd/led-matrix-dashboard.service`
   contain duplicated `User`, `Group`, `WorkingDirectory`, `EnvironmentFile`,
   and `ExecStart` directives for different deployment accounts. A plain install
   may fail or run the wrong command until these units are cleaned for the target
   host.
2. `.github/workflows/pylint.yml` runs ruff, black, and pytest with `|| true`.
   GitHub Actions can show success even when linting, formatting, or tests fail.
3. `main.py` catches any exception while importing `runtime_control` and falls
   back to a partial inline control implementation. A real runtime-control bug
   can be hidden as if the feature were unavailable.
4. `requirements.txt` does not include the exact Pi 5 matrix backend imported by
   `display_manager.py` (`adafruit_blinka_raspberry_pi5_piomatter`). A fresh
   hardware install based only on requirements can miss a required package.
5. Runtime state depends on a mutable SQLite DB outside version control.
   Relative `DB_PATH` values depend on the working directory used by systemd or
   the shell.
6. Several environment/config knobs are parsed but do not drive current behavior:
   `DISPLAY_BRIGHTNESS`, `WEATHER_API_KEY`, `ADMIN_LOGIN_MAX_ATTEMPTS`, and
   `ADMIN_LOGIN_LOCKOUT_SECONDS`.

## Current Known Problems And Limitations

### Runtime And Control Flow

- `main.run_forever()` has no top-level crash containment. An unhandled exception
  in API fetch, DB access, rendering, or game code can terminate the runtime
  unless systemd restarts it.
- The runtime-control import fallback in `main.py` catches broad `Exception`,
  not only missing-module import errors.
- Config is read at module import time. Tests and long-lived processes must
  reload modules to pick up `.env` or environment changes.
- Skip/switch requests are intentionally discarded while Snake or custom text
  blocks category control. This keeps state simple, but a user action can appear
  accepted by the API and then have no visible effect.
- If both switch and skip are pending in the same normal slot, switch wins first.
  That is current behavior and should be kept documented if it remains intended.

### Database And State

- `db_manager` initializes each normalized DB path once per process. If a DB file
  is deleted or replaced while the process stays alive, schema initialization may
  not rerun for that path.
- `schema_version` is inserted as a `meta` value but is not a real migration
  system. Existing DBs are updated through `CREATE TABLE IF NOT EXISTS` and
  best-effort `ALTER TABLE` calls.
- `admin_login_attempts`, `system_state`, `category_rotation`, and
  `jokes_rotation` exist in the schema but are unused or legacy in the current
  runtime path.
- There is no explicit DB busy retry strategy beyond SQLite defaults. The
  dashboard and runtime both write to the same DB.
- The dashboard snapshot is saved before display output is confirmed. A render
  or hardware failure can leave `current_display_state` ahead of the physical
  matrix.

### Rotation And External Content

- Pokemon catalog fetch failure falls back to IDs `1..1025`. If that happens
  during daily rotation setup, the fallback catalog can become the stored
  rotation source for that day/catalog hash.
- Pokemon details and artwork are fetched at runtime. Artwork fetch happens
  inside display rendering, so slow network calls can affect frame timing.
- Joke fallback rows are tracked by slot key, but the fallback text itself is
  static. Extended JokeAPI outages will repeat the same joke across slots.
- `used_jokes` grows over time and has no cleanup policy.
- Science data has an in-memory cache and fallback list, but if the upstream
  request succeeds with an empty element array, `random.choice([])` is still
  possible.
- Weather fetches `is_day` but the current payload/rendering path does not use
  it. `WEATHER_API_KEY` is also unused because Open-Meteo does not need it.

### Display And Rendering

- Hardware preview frames are saved after `_prepare_image()` rotation but before
  the final flips applied in `_push_prepared()`. Saved previews may not exactly
  match the hardware framebuffer orientation.
- `DisplayManager.render_payload()` is useful for tests and simple callers, but
  it does not cover every animated rendering path used by the live runtime.
- `display_manager.py` performs image loading, network artwork fetches, text
  layout, animations, preview saving, and hardware output in one module. Small
  changes can have wider timing or rendering effects than they first appear to.
- The display code uses Pillow internals in places, including `draw._image`.
  Pillow upgrades should be tested on the target runtime.
- `DISPLAY_BRIGHTNESS` is parsed in config but no display code currently applies
  it to matrix output.

### Dashboard And Admin

- Most admin APIs are under `/api/admin/...`, but forced custom text uses
  `/admin/custom-text/force`. The server and frontend agree today, but the
  inconsistency is easy to miss when adding routes or tests.
- Login throttling is in process memory. It resets on server restart and is not
  shared between multiple dashboard processes.
- The `admin_login_attempts` DB table and admin lockout config values are not
  connected to the active throttling implementation.
- Admin cookie `Secure` behavior depends on `ADMIN_COOKIE_SECURE`. The default
  is suitable for local HTTP development, not for a dashboard exposed over an
  untrusted network.

### Deployment And Packaging

- Requirements are unpinned. Dependency updates can change behavior without a
  repository change.
- The imported Pi 5 matrix backend is not listed in `requirements.txt`.
- The service files need per-host cleanup before use. They currently mix `pi`
  and `human` account examples in the same unit files.
- `Notes/systemd.md` contains duplicated/inconsistent deployment notes and
  should be verified against the current code and service files before use.

### Tests And CI

- The test suite is much broader than older docs claimed, but CI does not fail
  on ruff, black, or pytest failures because of `|| true`.
- Tests do not validate systemd unit correctness.
- Tests do not exercise the real Pi matrix backend, real hardware orientation,
  or actual browser rendering of the dashboard.
- Network clients are mostly tested through mocked/fallback paths. Live API
  behavior and latency remain runtime risks.

## Fixed Or Stale Historical Findings

The older bug notes included several findings that no longer match the current
repository:

- A pytest suite now exists under `tests/` and covers runtime controls,
  dashboard APIs, auth, custom text, snapshots, display helpers, and Snake.
- `requirements.txt`, `.env.example`, `.gitignore`, `.pre-commit-config.yaml`,
  GitHub Actions, and `.github/CODEOWNERS` exist.
- Runtime SQLite files and sidecars are ignored by git; a local `content.db` may
  exist, but it is not part of the tracked project state.
- The dashboard, custom text flow, admin controls, and Snake mode are implemented
  rather than only planned.
- `DisplayManager` now raises when hardware mode is requested without the
  required matrix backend.
- `python main.py --simulate --once` is a practical one-shot smoke path and
  renders briefly instead of running a full rotation interval.
- Long-token wrapping has explicit splitting logic in the current display code.
- Pokemon rendering no longer depends on an old documented `NO IMG` placeholder
  path.
- Service files exist, but the current problem is their duplicated/conflicting
  deployment directives, not total absence.

## Before Closing A Related Fix

Run the focused tests for the touched area, then run the broader suite when
practical:

```bash
python -m pytest
python main.py --simulate --once
```

For deployment changes, also validate the final service files with systemd on
the target host before relying on them.
