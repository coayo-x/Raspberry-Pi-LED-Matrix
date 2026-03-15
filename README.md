# Raspberry-Pi-LED-Matrix

All detailed documentation is maintained in the [project Wiki](https://github.com/coayo-x/Raspberry-Pi-LED-Matrix/wiki).

Key pages:

- [Getting Started](https://github.com/coayo-x/Raspberry-Pi-LED-Matrix/wiki/Getting-Started)
- [Architecture](https://github.com/coayo-x/Raspberry-Pi-LED-Matrix/wiki/Architecture)
- [Runtime Model](https://github.com/coayo-x/Raspberry-Pi-LED-Matrix/wiki/Runtime-Model)
- [Configuration and Database](https://github.com/coayo-x/Raspberry-Pi-LED-Matrix/wiki/Configuration-and-Database)
- [Content Categories and APIs](https://github.com/coayo-x/Raspberry-Pi-LED-Matrix/wiki/Content-Categories-and-APIs)
- [Developer Guide](https://github.com/coayo-x/Raspberry-Pi-LED-Matrix/wiki/Developer-Guide)
- [Deployment on Raspberry Pi](https://github.com/coayo-x/Raspberry-Pi-LED-Matrix/wiki/Deployment-on-Raspberry-Pi)
- [Troubleshooting](https://github.com/coayo-x/Raspberry-Pi-LED-Matrix/wiki/Troubleshooting)

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
