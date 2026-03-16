# Systemd Setup

This repository now ships both systemd units:

- [`systemd/led-matrix.service`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/systemd/led-matrix.service)
- [`systemd/led-matrix-dashboard.service`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/systemd/led-matrix-dashboard.service)

## Install

Copy the units into `/etc/systemd/system/` and reload systemd:

```bash

- [`systemd/led-matrix.service`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/systemd/led-matrix.service)
- [`systemd/led-matrix-dashboard.service`](/C:/Users/amina/Raspberry-Pi-LED-Matrix/systemd/led-matrix-dashboard.service)

## Install
This project provides two systemd services:

- `led-matrix.service` → runs the LED matrix application  
- `led-matrix-dashboard.service` → runs the dashboard backend

These services allow the app to **start automatically when the Raspberry Pi boots**.

---

# Install the Services

Copy the service files to the systemd directory:

```bash
sudo cp systemd/led-matrix.service /etc/systemd/system/
sudo cp systemd/led-matrix-dashboard.service /etc/systemd/system/
````

Reload systemd:

```bash
sudo systemctl daemon-reload
```

---

# Enable Auto-Run on Boot

```bash
sudo systemctl enable --now led-matrix.service
sudo systemctl enable --now led-matrix-dashboard.service
```

---

# Systemd Commands

## Main LED Matrix Service

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

Adjust the checked-in unit files first if your Raspberry Pi user or repository path is not `/home/pi/Raspberry-Pi-LED-Matrix`.

## Enable Auto-Run

```bash

```bash
sudo systemctl enable --now led-matrix.service
sudo systemctl enable --now led-matrix-dashboard.service
```

## Day-To-Day Commands
**Check if it’s running**

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
```

---

## Dashboard Service

**Start the service**

```bash
sudo systemctl start led-matrix-dashboard.service
```

Copy the units into `/etc/systemd/system/` and reload systemd:

```bash
sudo cp systemd/led-matrix.service /etc/systemd/system/
sudo cp systemd/led-matrix-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart led-matrix-dashboard.service
```

Adjust the checked-in unit files first if your Raspberry Pi user or repository path is not `/home/pi/Raspberry-Pi-LED-Matrix`.

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

sudo systemctl start led-matrix-dashboard.service
sudo systemctl restart led-matrix-dashboard.service
sudo systemctl stop led-matrix-dashboard.service
sudo systemctl status led-matrix-dashboard.service
sudo systemctl stop led-matrix-dashboard.service
```

**Check if it’s running**

```bash
sudo systemctl status led-matrix-dashboard.service
```

---

# View Logs

```bash
journalctl -u led-matrix.service -f
```

```bash
journalctl -u led-matrix-dashboard.service -f
```
