# Systemd Setup

This repository now ships both systemd units:

- [`systemd/led-matrix.service`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/systemd/led-matrix.service)
- [`systemd/led-matrix-dashboard.service`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/systemd/led-matrix-dashboard.service)

## Install

Copy the units into `/etc/systemd/system/` and reload systemd:

```bash
sudo cp systemd/led-matrix.service /etc/systemd/system/
sudo cp systemd/led-matrix-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
```

These checked-in unit files assume the deployment path is `/home/human/Raspberry-Pi-LED-Matrix` and run as the `human` user/group. Adjust them before install if your Raspberry Pi uses a different user or repository path.

## Enable Auto-Run

```bash
sudo systemctl enable --now led-matrix.service
sudo systemctl enable --now led-matrix-dashboard.service
```

## Day-To-Day Commands

```bash
sudo systemctl start led-matrix.service
sudo systemctl restart led-matrix.service
sudo systemctl stop led-matrix.service
sudo systemctl status led-matrix.service

sudo systemctl start led-matrix-dashboard.service
sudo systemctl restart led-matrix-dashboard.service
sudo systemctl stop led-matrix-dashboard.service
sudo systemctl status led-matrix-dashboard.service
```

## Dashboard Service-Control Permissions

The admin dashboard calls `systemctl` for stop/restart actions.

One of these must be true on the Raspberry Pi:

1. the dashboard service runs with permission to control both units
2. passwordless sudo is configured for the exact `systemctl stop/restart` commands and `SYSTEMCTL_USE_SUDO=1` is set in `.env`

If neither is true, admin service actions will fail even though login and the rest of the dashboard still work.
