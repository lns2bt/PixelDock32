# Raspberry Pi: Autostart + recovery in case of hangs

This guide sets up PixelDock32 to:

- the service starts automatically when booting,
- Crashes are automatically restarted by `systemd`,
- a regular health check restarts the service in the event of hangs/no HTTP response,
- Autostart can be switched on/off via script.

## 1) One-time setup (copy & paste)

> Default path in the example: `/home/pi/PixelDock32`

```bash
cd /home/pi/PixelDock32
chmod +x scripts/manage-autostart.sh scripts/pixeldock32-healthcheck.sh
sudo ./scripts/manage-autostart.sh enable --repo-dir /home/pi/PixelDock32 --user pi --group pi
```

What happens:

- `/etc/systemd/system/pixeldock32.service` is created from the template,
- `pixeldock32` is activated and started,
- `pixeldock32-healthcheck.timer` is activated,
- Healthcheck runs every minute and checks `http://127.0.0.1:8000/`.

## 2) Check status

```bash
./scripts/manage-autostart.sh status
systemctl list-timers --all | rg pixeldock32-healthcheck
```

## 3) Check logs

```bash
./scripts/manage-autostart.sh logs
journalctl -u pixeldock32-healthcheck.service -n 50 --no-pager
```

## 4) Disable autostart

```bash
sudo ./scripts/manage-autostart.sh disable
```

This will stop Service + Healthcheck timers and remove them from the boot autostart.

## 5) Optional: Adjust health check URL/timeout

By default the script checks the root URL with an 8 second timeout.

Test example manually:

```bash
HEALTH_URL="http://127.0.0.1:8000/" TIMEOUT_SECONDS=8 ./scripts/pixeldock32-healthcheck.sh
```

If you later have a dedicated health route (e.g. `/health`), then set the URL accordingly and store it in the script.
