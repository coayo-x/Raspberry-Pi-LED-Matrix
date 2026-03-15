# Systemd Setup

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

**Start the service**

```bash
sudo systemctl start led-matrix.service
```

**Restart the service**

```bash
sudo systemctl restart led-matrix.service
```

**Stop the service**

```bash
sudo systemctl stop led-matrix.service
```

**Check if it’s running**

```bash
sudo systemctl status led-matrix.service
```

---

## Dashboard Service

**Start the service**

```bash
sudo systemctl start led-matrix-dashboard.service
```

**Restart the service**

```bash
sudo systemctl restart led-matrix-dashboard.service
```

**Stop the service**

```bash
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
