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
- `Alien Dance` / `Stop Alien Dance`

Backend enforcement now applies to both actions:

- cooldown/rate limiting on accepted requests
- admin lock/unlock support for public access
- clear API responses for locked and rate-limited requests

Admin-only controls:

- lock/unlock public skip access
- lock/unlock public switch access

## Alien Dance Mode

The dashboard includes an Alien Dance override card beneath the Pokemon artwork card.

- `Alien Dance` pauses the normal slot rotation and starts a looping animation plus looping `assets/Alien.mp3` audio.
- `Stop Alien Dance` stops the override and returns the runtime to the normal slot-based schedule.

The runtime looks for its media under `assets/alien.gif` and `assets/Alien.mp3`. For audio playback on the Raspberry Pi, install at least one supported player such as `ffplay`, `mpg123`, `mpv`, or `cvlc`.

When the current category is `pokemon`, the dashboard shows the normalized Pokemon artwork from the existing payload when available.

## Systemd

Checked-in units live in [`systemd/led-matrix.service`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/systemd/led-matrix.service) and [`systemd/led-matrix-dashboard.service`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/systemd/led-matrix-dashboard.service).

Install and enable them with the steps in [`Notes/systemd.md`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/Notes/systemd.md).
