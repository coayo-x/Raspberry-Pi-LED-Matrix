# BUGS.md

## Scope

This document is a code-and-state audit of the repository as inspected on `2026-03-15`.

Reviewed artifacts:

- `main.py`
- `rotation_engine.py`
- `db_manager.py`
- `display_manager.py`
- `apis/pokemon.py`
- `apis/weather.py`
- `apis/jokes.py`
- `apis/science.py`
- `AGENT.md`
- `.github/workflows/pylint.yml`
- `Notes/systemd.md`
- checked-in `content.db` schema and live contents

Observed runtime constraints during audit:

- the local environment does not currently have `numpy`
- the local environment does not currently have Pillow (`PIL`)
- because `display_manager.py` imports those at module import time, the full app could not be executed locally even in `--simulate` mode

## Highest-Risk Findings

These are the most consequential problems in the current codebase:

1. The app cannot start without `numpy` and Pillow, even in `--simulate`.
2. Slot timing is not enforced; long animations can overrun slot boundaries and delay later categories.
3. A transient PokeAPI catalog failure can rewrite `pokemon_rotation` to the fallback catalog and reset daily Pokemon state.
4. The repository has no real migration system; `schema_version` is already stale in the checked-in DB.
5. `display_manager.py` mixes rendering, network I/O, preview output, animation timing, and hardware writes in one class.
6. The GitHub Actions workflow targets unsupported Python versions and does not install runtime dependencies.
7. The checked-in `content.db` is live mutable state, so clones do not start from a clean baseline.

## Runtime Bugs

### 1. Simulation mode still hard-depends on `numpy` and Pillow

- Location: `display_manager.py` module import, `main.py:main()`
- Problem: `display_manager.py` imports `numpy` and `PIL` at module import time. `main.py` imports `DisplayManager` before CLI flags are interpreted.
- Why it matters: `--simulate` suggests the app can run without hardware dependencies, but it still crashes if `numpy` or Pillow is missing.
- Impact: local development, CI, preview generation, and debugging are blocked unless full rendering dependencies are installed.
- Suggestion: move optional rendering and hardware imports behind execution paths, or split hardware output from software rendering.

### 2. Any uncaught exception kills the process

- Location: `main.py:run_once()`, `main.py:run_forever()`
- Problem: the main loop has no top-level exception handling, retry policy, or degraded mode behavior.
- Why it matters: a single unexpected DB error, render failure, font failure, or adapter regression takes down the whole process.
- Impact: display stops updating until the process is restarted externally.
- Suggestion: wrap payload build and display calls in structured error handling with logging and fallback behavior.

### 3. Slot boundaries are advisory, not enforced

- Location: `main.py:run_forever()`, `display_manager.py:_animate_pokemon()`, `display_manager.py:_animate_joke()`, `display_manager.py:_animate_weather_ticker()`, `display_manager.py:display_payload()`
- Problem: the loop calculates `duration_seconds` once, but animation routines sleep internally and do not strictly clamp every transition to the remaining slot time.
- Why it matters: the scheduler says content rotates every 5 minutes, but the display path can run past that boundary.
- Impact: category changes happen late, slot cadence drifts, and the effective schedule on the matrix diverges from the nominal schedule.
- Suggestion: switch to deadline-based timing and clamp every phase against an absolute slot end time.

### 4. Pokemon intro alone can overrun a nearly-finished slot

- Location: `display_manager.py:_animate_pokemon()`
- Problem: the Pokemon intro is forced to remain visible for about 3 seconds, even if the caller passed only 1 second remaining in the current slot.
- Why it matters: starting the app near a slot boundary guarantees schedule drift on the first Pokemon slot.
- Impact: the first category after startup is late, and subsequent slot timing is already off.
- Suggestion: bound intro time by remaining slot budget.

### 5. Wall-clock logic is DST-unsafe

- Location: `rotation_engine.py:get_current_slot_number()`, `rotation_engine.py:get_current_slot_key()`, `rotation_engine.py:get_current_category()`, `rotation_engine.py:seconds_until_next_slot()`
- Problem: slot math uses naive local `datetime.now()` and assumes a normal 24-hour day with 288 unique slots.
- Why it matters: daylight saving transitions create skipped or repeated wall-clock times.
- Impact: repeated slot keys on fall-back can incorrectly reuse cached joke/science content; spring-forward skips entire slot ranges.
- Suggestion: use timezone-aware datetimes and decide explicitly how DST transitions should map to slot identity.

### 6. Timing precision ignores microseconds

- Location: `rotation_engine.py:seconds_until_next_slot()`
- Problem: the function uses `current.second` but ignores microseconds.
- Why it matters: near slot boundaries the returned duration can be almost a full second too long.
- Impact: additional boundary slop compounds the animation overrun problem.
- Suggestion: compute remaining time from full `datetime` precision.

## Logic Errors And Edge Cases

### 7. `_wrap_text()` is incorrect for long unbroken tokens

- Location: `display_manager.py:_wrap_text()`
- Problem: when a single token exceeds the width, the algorithm repeatedly peels one character off the end and appends `line[:-1]`, which can still be too wide. In an extreme narrow-width case, it can loop forever on a single character.
- Why it matters: the renderer assumes this helper produces valid pages and overlays.
- Impact: malformed line wrapping, oversized text, and a potential infinite loop if width assumptions change.
- Suggestion: replace with a correct greedy wrapper that handles long tokens by slicing to the largest fitting prefix.

### 8. Science payloads are not round-tripped faithfully through the DB cache

- Location: `rotation_engine.py:get_current_science_fact()`
- Problem: only a subset of science fields is persisted, and cached reads reconstruct `category: "element"` regardless of the original payload.
- Why it matters: the runtime data contract changes depending on whether the fact was freshly fetched or loaded from cache.
- Impact: future science categories or additional metadata will disappear after one slot transition or restart.
- Suggestion: persist the full normalized science payload or define an explicit stored schema and adapter contract.

### 9. Fallback joke dedupe is keyed by slot, not by content

- Location: `rotation_engine.py:_fallback_joke()`, `rotation_engine.py:get_current_joke()`
- Problem: fallback jokes use `fallback:<slot_key>` as the key even though the text is constant.
- Why it matters: the dedupe table does not prevent the same fallback joke text from repeating forever.
- Impact: `used_jokes` keeps growing with logically duplicate fallback entries and the display quality degrades under API failures.
- Suggestion: use a stable content hash for fallback joke keys.

### 10. Unknown category rendering is silently tolerated instead of rejected

- Location: `display_manager.py:render_payload()`, `display_manager.py:display_payload()`
- Problem: unknown categories render an `UNKNOWN` image rather than raising.
- Why it matters: payload schema errors can be masked instead of surfaced quickly.
- Impact: bad upstream data can look like a rendering issue rather than a contract failure.
- Suggestion: raise an exception for unknown categories outside explicit debug tooling.

### 11. Silent fallbacks hide real failures

- Location: `main.py:build_content_for_now()`, `apis/pokemon.py:get_valid_pokemon_ids()`, `rotation_engine.py:get_current_joke()`, `rotation_engine.py:get_current_science_fact()`
- Problem: many calls catch broad `Exception` and silently substitute fallback content.
- Why it matters: operators get no signal that the app is degraded.
- Impact: network failures, API schema changes, and parsing bugs can persist unnoticed while the display quietly shows backup content.
- Suggestion: log or persist fallback reasons and distinguish expected API outages from coding errors.

### 12. `render_payload()` is not representative of real on-matrix behavior

- Location: `display_manager.py:render_payload()`
- Problem: for animated categories it returns only a single representative frame: first joke page, weather header without ticker, Pokemon base frame without intro/stat cycle.
- Why it matters: any code that uses `render_payload()` as a preview or validation API will get an incomplete picture.
- Impact: tests, previews, and future tooling can give false confidence.
- Suggestion: separate "static thumbnail" rendering from the full animation API.

## Database Risks

### 13. The default DB path is relative and easy to misdirect

- Location: `db_manager.py:DB_FILE`, all `db_path="content.db"` call sites
- Problem: the DB file is resolved relative to the process working directory, not the repository root.
- Why it matters: launching the app from the wrong directory creates or uses a different database.
- Impact: mysterious state resets, split-brain content state, and deployment confusion.
- Suggestion: resolve the DB path relative to the project root or an explicit config directory.

### 14. There is no real migration system

- Location: `db_manager.py:init_db()`
- Problem: schema upgrades are implemented as "add column if missing". Existing rows and values are never normalized, and `meta.schema_version` is not used to drive migrations.
- Why it matters: schema drift accumulates silently and old DBs are not brought to a known-good shape.
- Impact: long-lived installs can diverge in subtle ways from fresh installs.
- Suggestion: adopt explicit, ordered migrations and make `schema_version` authoritative.

### 15. The checked-in DB already proves migration state is inconsistent

- Location: `content.db`, `db_manager.py:init_db()`
- Problem: the repository DB still has `meta.schema_version = 3` even though `init_db()` inserts `4` when missing.
- Why it matters: the metadata no longer describes the real schema state.
- Impact: future contributors cannot trust schema metadata, and migration logic built on it would be unsafe.
- Suggestion: stop treating schema version as write-once metadata; migrate existing DBs explicitly.

### 16. `system_state` is a fragile singleton with no recovery path

- Location: `rotation_engine.py:_get_system_state()`, all `row[...]` call sites
- Problem: the code assumes the singleton row with `id = 1` always exists because `init_db()` inserts it. There is no defensive handling if the row is missing or corrupted.
- Why it matters: one damaged or manually edited DB can crash all category selection paths.
- Impact: `TypeError` or key access failures during normal runtime.
- Suggestion: validate and recreate the singleton row if absent.

### 17. No concurrency or lock strategy beyond SQLite defaults

- Location: `db_manager.py:connect()`
- Problem: the code sets WAL mode but does not configure timeouts, retries on lock errors, or any single-process guard.
- Why it matters: concurrent runs, overlapping systemd restarts, or manual inspection tools can still produce `database is locked`.
- Impact: intermittent failures in content selection or schema initialization.
- Suggestion: set a connection timeout and document/process-enforce single-writer ownership.

### 18. `used_jokes` is append-only and unbounded

- Location: `db_manager.py:init_db()`, `rotation_engine.py:get_current_joke()`
- Problem: used jokes are never expired, archived, or compacted.
- Why it matters: dedupe gets harder over time and the table grows forever.
- Impact: more API retries, more fallback jokes, larger DB, slower audits and backups.
- Suggestion: define a retention window or periodically prune old entries.

### 19. The repository tracks mutable runtime state

- Location: `content.db`
- Problem: the DB is committed into source control even though it changes during normal operation.
- Why it matters: a fresh clone is not a clean baseline, and routine runs dirty the working tree.
- Impact: confusing diffs, stale cached slot content, accidental commits of operational state.
- Suggestion: stop tracking the live runtime DB or ship a separate seed/migration path.

## State Consistency Problems

### 20. Transient Pokemon catalog failures can reset the rotation

- Location: `rotation_engine.py:_ensure_pokemon_rotation()`, `apis/pokemon.py:get_valid_pokemon_ids()`
- Problem: if catalog fetch fails, `get_valid_pokemon_ids()` silently returns the hardcoded fallback list `1..1025`. `_ensure_pokemon_rotation()` treats that as a real catalog change, rewrites `pokemon_rotation`, updates `meta`, and resets Pokemon state.
- Why it matters: a temporary network outage is interpreted as authoritative catalog shrinkage.
- Impact: daily Pokemon selection changes unexpectedly, queue order is rewritten, and catalog metadata regresses.
- Suggestion: distinguish "live catalog unavailable" from "live catalog changed" and do not rewrite state on fetch failure.

### 21. Pokemon content is only daily-stable at the ID layer

- Location: `main.py:build_content_for_now()`, `apis/pokemon.py:get_pokemon_data()`, `display_manager.py:_render_pokemon_base_canvas()`
- Problem: the selected Pokemon ID is stable for a day, but the app refetches the same Pokemon JSON and the same artwork on every Pokemon slot.
- Why it matters: the user-visible content is conceptually stable, but the implementation keeps re-hitting the network.
- Impact: unnecessary API load, more failure surface, and inconsistent behavior if the upstream record changes mid-day.
- Suggestion: cache normalized Pokemon data and artwork for the current `current_pokemon_id`.

### 22. Science facts lose metadata after one cache round-trip

- Location: `apis/science.py:get_science_fact_fallback()`, `rotation_engine.py:get_current_science_fact()`
- Problem: a fallback science fact includes `_fallback`, but the cache layer drops that field.
- Why it matters: downstream code cannot tell whether the current science fact was live or fallback once it comes back from the DB.
- Impact: poor observability and harder debugging of degraded behavior.
- Suggestion: preserve a `source` or `is_fallback` field in persisted state.

### 23. Broad fallback behavior creates state without provenance

- Location: `rotation_engine.py:get_current_joke()`, `rotation_engine.py:get_current_science_fact()`
- Problem: fallback payloads are persisted exactly like live payloads, but no reason or source is stored.
- Why it matters: once cached, there is no record explaining why a fallback was chosen.
- Impact: debugging operational incidents requires inference from current content instead of concrete state.
- Suggestion: persist source metadata and the failure reason when a fallback path is taken.

## API Failure Behavior

### 24. The full Pokemon catalog is fetched every time Pokemon content is built

- Location: `rotation_engine.py:get_today_pokemon_id()`, `rotation_engine.py:_ensure_pokemon_rotation()`, `apis/pokemon.py:get_valid_pokemon_ids()`
- Problem: before returning today's Pokemon, the code fetches the full catalog from PokeAPI every Pokemon slot.
- Why it matters: a daily-stable selection should not require a full remote catalog sync every 20 minutes.
- Impact: unnecessary latency, rate-limit exposure, and more chances to trip the catalog-reset bug.
- Suggestion: sync the catalog on a separate cadence or only when explicitly refreshing.

### 25. Pokemon detail fetches are not cached across the day

- Location: `main.py:build_content_for_now()`, `apis/pokemon.py:get_pokemon_data()`
- Problem: the same Pokemon detail JSON is requested every Pokemon slot even though the selected Pokemon ID stays constant all day.
- Why it matters: repeated requests provide no new information.
- Impact: extra network overhead and more fallback opportunities.
- Suggestion: cache the normalized detail payload for the active `current_pokemon_id`.

### 26. Pokemon artwork downloads have no retry, cache, or validation

- Location: `display_manager.py:_download_image()`
- Problem: artwork is downloaded on the render path with no retry logic, no cache, no content-length limit, and no content-type validation.
- Why it matters: slow or bad image responses directly block rendering.
- Impact: delayed slot start, placeholder `NO IMG`, or excessive memory use if the remote payload is unexpectedly large.
- Suggestion: cache validated images and move downloads out of the frame-render path.

### 27. Science adapter can raise on an empty API response

- Location: `apis/science.py:get_random_element_fact()`, `apis/science.py:_load_elements()`
- Problem: if the API returns an empty list, `_load_elements()` accepts it and `random.choice(elements)` raises `IndexError`.
- Why it matters: the adapter assumes a non-empty dataset without enforcing it.
- Impact: a nominally successful but empty upstream response can crash science selection.
- Suggestion: treat empty lists as invalid and fall back to `FALLBACK_ELEMENTS`.

### 28. Weather requests include unused data

- Location: `apis/weather.py:get_weather_data()`
- Problem: the API query requests `is_day`, but the return value discards it and the renderer ignores it.
- Why it matters: dead fields usually signal incomplete design or drift between adapter and renderer.
- Impact: minor waste and misleading future expectations that day/night-aware rendering exists.
- Suggestion: either use `is_day` in rendering or remove it from the request.

## Rendering Issues

### 29. Preview images do not match the framebuffer data pushed to hardware

- Location: `display_manager.py:_show_frame()`, `display_manager.py:_prepare_image()`, `display_manager.py:_push_prepared()`
- Problem: previews are saved after `_prepare_image()` but before `_push_prepared()` applies `np.flipud(np.fliplr(arr))`.
- Why it matters: the preview image bytes differ from what the matrix actually receives.
- Impact: preview-based debugging can mislead contributors about orientation and final output.
- Suggestion: save the exact framebuffer-oriented image when previews are intended to mirror hardware output.

### 30. Rendering depends on a private Pillow attribute

- Location: `display_manager.py:render_scrolling_text()`
- Problem: the helper reads `draw._image`, which is not a public Pillow API.
- Why it matters: private attributes can break across Pillow releases without warning.
- Impact: scrolling text can fail after a dependency upgrade even if the public API remains stable.
- Suggestion: pass the backing image explicitly instead of reaching into `ImageDraw` internals.

### 31. `display_manager.py` is doing too many unrelated jobs

- Location: `display_manager.py` class-wide
- Problem: the class owns text layout, image downloads, animation timing, preview file writing, numpy framebuffer conversion, and hardware output.
- Why it matters: changes in one concern are hard to test without triggering the others.
- Impact: poor maintainability, difficult unit testing, and brittle future refactors.
- Suggestion: split rendering, asset fetching, and output transport into separate components.

### 32. Rendering still sleeps in non-hardware preview mode

- Location: `display_manager.py:_transition_to()`, `_fade_sequence()`, `_animate_*()`
- Problem: even with `use_matrix=False`, the renderer still spends real time sleeping through transitions and animations.
- Why it matters: simulation and preview generation are slow and awkward for development.
- Impact: `--once` is unsuitable as a fast validation tool.
- Suggestion: add a fast preview mode that disables animation sleeps or renders to a frame sequence deterministically.

## Performance Risks

### 33. The render path allocates and copies aggressively

- Location: `display_manager.py:_transition_to()`, `_show_frame()`, `_push_prepared()`, `render_scrolling_text()`
- Problem: the code repeatedly copies full RGBA images, converts them to numpy arrays, and allocates new regions/frames.
- Why it matters: on constrained Pi hardware, that increases CPU usage and garbage pressure.
- Impact: dropped responsiveness, more heat, and slower frame updates.
- Suggestion: reuse buffers where possible and avoid constructing full frame lists unless needed.

### 34. Preview output overwrites the same filenames repeatedly

- Location: `display_manager.py:_animate_weather_ticker()`, `_animate_joke()`, `_animate_pokemon()`, `_save_prepared()`
- Problem: several animations reuse the same preview filename during a slot.
- Why it matters: the preview directory is not a faithful record of what happened.
- Impact: harder debugging and less useful postmortem artifacts.
- Suggestion: either save only named keyframes intentionally or emit indexed frames consistently.

### 35. Joke uniqueness gets slower and worse over time

- Location: `rotation_engine.py:get_current_joke()`
- Problem: the code tries up to 10 random JokeAPI calls and rejects duplicates via `used_jokes`.
- Why it matters: as `used_jokes` grows, the chance of landing a duplicate increases.
- Impact: more wasted API calls and more frequent fallback jokes.
- Suggestion: add pruning, a rotating source pool, or a stronger fetch strategy than blind retry.

## Dependency And Tooling Issues

### 36. There is no dependency manifest

- Location: repository root
- Problem: there is no `requirements.txt`, `pyproject.toml`, `Pipfile`, or equivalent.
- Why it matters: contributors and CI have no authoritative install target.
- Impact: non-reproducible environments, broken local runs, and guesswork during deployment.
- Suggestion: add a real dependency manifest and pin or range runtime dependencies explicitly.

### 37. The CI workflow targets unsupported Python versions

- Location: `.github/workflows/pylint.yml`, `main.py`, `rotation_engine.py`
- Problem: the workflow runs on Python `3.8`, `3.9`, and `3.10`, but the code uses PEP 604 union syntax (`datetime | None`, `str | None`) which requires Python 3.10+.
- Why it matters: the advertised support matrix is false.
- Impact: CI is either already broken on older interpreters or gives misleading compatibility claims.
- Suggestion: declare Python 3.10+ as the minimum version and update the workflow accordingly.

### 38. The CI workflow does not install runtime dependencies

- Location: `.github/workflows/pylint.yml`
- Problem: CI installs only `pylint` and does not install `numpy`, Pillow, or optional hardware dependencies.
- Why it matters: linting import behavior is detached from the actual runtime environment.
- Impact: noisy import errors or incomplete validation of real code paths.
- Suggestion: install runtime dependencies in CI or use a dedicated lint environment with explicit stubs/config.

### 39. Hardware output silently disables itself if `piomatter` is missing

- Location: `display_manager.py:__init__()`
- Problem: `self.use_matrix = use_matrix and piomatter is not None` turns a requested hardware mode into simulation without warning.
- Why it matters: missing hardware support can look like a successful launch.
- Impact: operators think the service is running normally while nothing is actually pushed to the matrix.
- Suggestion: log or raise when matrix mode was requested but cannot be activated.

## CLI Design Problems

### 40. CLI parsing is ad hoc and ignores unknown flags

- Location: `main.py:main()`
- Problem: flags are parsed by membership in `set(sys.argv[1:])`.
- Why it matters: there is no help output, no validation, no typed arguments, and no feedback on misspelled flags.
- Impact: operator mistakes fail silently.
- Suggestion: replace with `argparse` and explicit usage/help text.

### 41. `--once` is semantically inconsistent

- Location: `main.py:run_once()`, `display_manager.py:display_payload()`
- Problem: `--once` means roughly 5 minutes for Pokemon/weather/joke, but almost immediate return for science.
- Why it matters: the flag name implies a single cycle, not category-specific duration semantics.
- Impact: scripts and humans cannot predict how long `--once` will take.
- Suggestion: add explicit modes such as `--once`, `--duration`, or `--snapshot`.

### 42. The 10-second boot delay is hardcoded and not configurable

- Location: `main.py:run_forever()`
- Problem: continuous mode always sleeps 10 seconds before doing useful work unless the code is edited.
- Why it matters: that is operational policy baked into the source.
- Impact: slower service recovery and unnecessary startup lag.
- Suggestion: expose boot delay as a CLI flag or config parameter.

## Security Concerns

### 43. Remote image bytes are opened with PIL without size or type checks

- Location: `display_manager.py:_download_image()`
- Problem: the code reads arbitrary bytes from a remote URL and passes them directly into Pillow.
- Why it matters: malformed or oversized images can cause resource exhaustion or decoder issues.
- Impact: denial of service via memory pressure or image parsing failure.
- Suggestion: validate content length, MIME type, and pixel bounds before decoding; consider caching vetted assets only.

### 44. SQL helpers interpolate identifiers directly into SQL strings

- Location: `db_manager.py:_column_exists()`, `db_manager.py:_ensure_column()`
- Problem: table and column names are formatted into SQL using f-strings.
- Why it matters: today the inputs are internal constants, but the pattern is unsafe and unscalable.
- Impact: future callers could accidentally create SQL injection paths around schema management.
- Suggestion: keep identifier inputs closed over internal constants or centralize schema DDL instead of dynamic string formatting.

## Technical Debt And Dead Code

### 45. Legacy tables and columns are still created but unused

- Location: `db_manager.py:init_db()`, `system_state` schema
- Problem: `category_rotation`, `jokes_rotation`, `last_date`, `category_pos`, and `joke_pos` are still provisioned even though the runtime does not read them.
- Why it matters: dead schema makes the storage model harder to understand and maintain.
- Impact: contributors may build new features on abandoned structures.
- Suggestion: remove legacy schema objects through a real migration path or clearly quarantine them.

### 46. Several functions are unused by the running app

- Location: `apis/pokemon.py:get_total_pokemon()`, `apis/science.py:get_element_by_number()`
- Problem: the repository carries helper functions that are not referenced by the application.
- Why it matters: unused code expands the audit surface and can give a false impression of supported behavior.
- Impact: extra maintenance burden and more code drift.
- Suggestion: remove unused helpers or cover/document them as intentional public utilities.

### 47. Some adapter contracts have already drifted from their type hints

- Location: `apis/science.py:_fetch_json()`
- Problem: `_fetch_json()` is annotated to return `dict`, but the science API actually returns a list and the code depends on that list shape.
- Why it matters: inaccurate type hints make static reasoning and future refactoring less reliable.
- Impact: tooling and contributors can make wrong assumptions about returned data.
- Suggestion: correct type hints and normalize API response types explicitly.

## Fragile Coupling Between Modules

### 48. Payload dicts are a manually synchronized contract

- Location: `main.py:build_content_for_now()`, `rotation_engine.py`, `display_manager.py`, all `apis/*.py`
- Problem: every layer passes raw dicts with implicit field names and no validation layer.
- Why it matters: one field rename or missing key breaks runtime behavior across multiple modules.
- Impact: fragile refactors, weak editor/tooling support, and runtime-only failure discovery.
- Suggestion: define explicit typed payload models or at least central schema validators.

### 49. `display_manager.py` couples network behavior to rendering correctness

- Location: `display_manager.py:_render_pokemon_base_canvas()`, `_download_image()`
- Problem: rendering a Pokemon frame requires a live image fetch unless the image already fails and falls back to `NO IMG`.
- Why it matters: render determinism depends on network conditions.
- Impact: the same payload can render differently depending on connectivity and remote latency.
- Suggestion: fetch assets before rendering and pass fully resolved render inputs into the display layer.

### 50. The singleton `system_state` row couples unrelated categories together

- Location: `db_manager.py:init_db()`, `rotation_engine.py`
- Problem: Pokemon, joke, and science state all share one wide row.
- Why it matters: schema changes and corruption in one logical feature area are stored in the same record as the others.
- Impact: fragile migrations and broad blast radius for state bugs.
- Suggestion: split state by feature or persist normalized payload blobs with explicit versioning.

## Missing Tests

### 51. There are no automated tests for the scheduler, persistence, or renderer

- Location: repository-wide
- Problem: the repository has no test suite.
- Why it matters: the most failure-prone code is exactly the code that needs regression coverage: slot math, DB bootstrapping, state transitions, and render helpers.
- Impact: every change is high-risk and behavior regressions are easy to miss.
- Suggestion: add focused tests for slot math, `init_db()`, Pokemon queue behavior, joke dedupe, and render helper contracts.

### 52. There are no tests for edge-case time behavior

- Location: repository-wide
- Problem: no tests cover midnight rollover, DST transitions, near-boundary slot timing, or startup mid-slot.
- Why it matters: those are exactly where schedule bugs emerge.
- Impact: production-only timing bugs remain likely.
- Suggestion: make time injectable everywhere and add deterministic boundary-condition tests.

## Deployment Risks

### 53. The repository documents service commands but does not ship the service definition

- Location: `Notes/systemd.md`
- Problem: the repo references `led-matrix.service` commands, but the actual unit file is missing.
- Why it matters: operations instructions are incomplete.
- Impact: deployments are manual, inconsistent, and hard to reproduce.
- Suggestion: add the real systemd unit file and installation instructions.

### 54. `.gitignore` does not ignore common runtime artifacts

- Location: `.gitignore`
- Problem: the repo does not ignore `preview_frames/`, `content.db-wal`, `content.db-shm`, or other runtime outputs besides `__pycache__` and `*.pyc`.
- Why it matters: normal execution can create noisy untracked or modified files.
- Impact: polluted working trees and accidental artifact commits.
- Suggestion: ignore preview output and SQLite sidecar files explicitly.

### 55. Weather location and other runtime behavior are hardcoded

- Location: `apis/weather.py`, `main.py`, `display_manager.py`
- Problem: core deployment choices such as weather coordinates, location label, preview directory, and boot delay are embedded in source defaults with no config layer.
- Why it matters: operational changes require code edits.
- Impact: brittle deployments and environment-specific forks.
- Suggestion: move operational settings into CLI flags, env vars, or a config file.

## Summary

The repository is small enough to understand quickly, but it is carrying several structural liabilities:

- runtime behavior depends on mutable SQLite state that is checked into source control
- the scheduling contract is weaker than the code suggests because display timing is not hard-bounded
- network failures are often silently transformed into state changes or fallback content
- rendering, networking, and hardware concerns are tightly interwoven
- the toolchain and deployment story are incomplete and partly inconsistent with the code

The highest-value next steps are:

1. add a dependency manifest and fix CI to target the real Python/runtime environment
2. decouple rendering from networking and hardware writes
3. replace ad hoc DB evolution with explicit migrations
4. stop rewriting Pokemon rotation state on catalog fetch failure
5. add focused tests around slot math, DB state transitions, and rendering helpers
