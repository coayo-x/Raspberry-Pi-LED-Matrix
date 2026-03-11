# Contributing Guidelines

## Overview

This project follows a structured architecture to keep the system organized and maintainable.
All contributions are welcome, but they should respect the overall design.

---

## Workflow

* Please do not push directly to the `main` branch.
* Create a separate branch for your feature or fix.
* Submit your changes through a Pull Request (PR).
* At least one approval is required before merging.

---

## Branch Naming

Use clear and descriptive names, for example:

* `feature/pokemon-api`
* `feature/weather-api`
* `feature/jokes-rotation`
* `fix/display-issue`

Avoid unclear names like:

* `update`
* `changes`
* `test`

---

## Project Structure

Each file has a defined responsibility:

* `main.py` → Application entry point
* `rotation_engine.py` → Content rotation logic
* `db_manager.py` → Database operations
* `display_manager.py` → LED display handling
* `apis/` → External API communication

To keep the project clean, please try to respect these responsibilities.

---

## Code Guidelines

* The system uses a rotation model (no repetition until a cycle is complete).
* Avoid adding random daily selection logic.
* Avoid mixing database logic inside display code.
* Keep functions focused and readable.

If a larger change is needed, feel free to discuss it before implementation.

---

## Pull Requests

Before submitting a PR:

* Make sure your feature works as expected.
* Keep changes focused on one feature or fix.
* Provide a short explanation of what your PR does.

---

## Final Note

This project is designed to demonstrate structured data rotation and system organization.
The goal is collaboration and learning while keeping the architecture clean.
