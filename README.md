# Raspberry-Pi-LED-Matrix

All detailed architecture notes remain in the [project Wiki](https://github.com/coayo-x/Raspberry-Pi-LED-Matrix/wiki). This repository now also includes a lightweight dashboard with public runtime visibility plus an authenticated admin control panel.

## Local Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the matrix runtime:

```bash
python main.py --simulate
```

Run the dashboard in another terminal:

```bash
python dashboard_server.py
```

Open `http://127.0.0.1:8080`.

## Admin Credentials

Real admin credentials must stay out of Git.

- Put admin settings in your local `.env` or `.env.local`. Both are ignored by Git.
- Only placeholders belong in `.env.example`.
- Generate `ADMIN_PASSWORD_HASH` locally instead of storing a plaintext password:

```bash
python -m admin_auth --hash-password
```

Minimum admin configuration:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=pbkdf2_sha256$...
```

Optional security tuning:

- `ADMIN_LOGIN_MAX_ATTEMPTS` defaults to `5`
- `ADMIN_LOGIN_LOCKOUT_SECONDS` defaults to `900`
- `ADMIN_SESSION_TTL_SECONDS` defaults to `43200`
- `ADMIN_SESSION_COOKIE_SECURE=1` is recommended when the dashboard is served behind HTTPS

This dashboard is designed for local or trusted-LAN use. If you expose it beyond that, put it behind proper TLS and network controls.

## Dashboard Controls

Public controls:

- `Skip Category`
- `Switch Category`

Backend enforcement now applies to both actions:

- cooldown/rate limiting on accepted requests
- admin lock/unlock support for public access
- clear API responses for locked and rate-limited requests

Admin-only controls:

- lock/unlock public skip access
- lock/unlock public switch access
- stop/restart `main.py` systemd service
- stop/restart `dashboard_server.py` systemd service

When the current category is `pokemon`, the dashboard shows the normalized Pokemon artwork from the existing payload when available.

## Systemd

Checked-in units live in [`systemd/led-matrix.service`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/systemd/led-matrix.service) and [`systemd/led-matrix-dashboard.service`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/systemd/led-matrix-dashboard.service).

Install and enable them with the steps in [`Notes/systemd.md`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/Notes/systemd.md).
Please review the Wiki before modifying any core components.

## Local Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

## Phase 1 Dashboard

Phase 1 adds a lightweight, read-only dashboard without changing the core slot loop into a web service.

High-level flow:

1. `main.py` determines the active slot and builds the payload for that slot.
2. The runtime writes a normalized `current_display_state` snapshot into SQLite.
3. `dashboard_server.py` reads that snapshot and exposes it at `/api/current-display-state`.
4. The dashboard page polls that endpoint and refreshes the visible fields automatically.

Current dashboard fields:

- `time`
- `slot`
- `category`
- `setup`
- `punchline`

Non-joke categories are normalized into the same `setup` and `punchline` fields, and the full raw category payload is also returned by the API for future UI expansion.

### Run the dashboard

Start the matrix runtime as usual in one terminal:

```bash
python main.py --simulate
```

Start the dashboard server in another terminal:

```bash
python dashboard_server.py
```

Open `http://127.0.0.1:8080` in a browser.

Optional environment variables:

- `DASHBOARD_HOST`
- `DASHBOARD_PORT`
- `DASHBOARD_POLL_INTERVAL_MS`

No new third-party runtime dependency was added for the dashboard. It uses Python's standard-library HTTP server plus simple static assets in `dashboard_assets/`.
