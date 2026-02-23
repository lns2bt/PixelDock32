# Raspberry Pi: Autostart + Recovery bei Hängern

Diese Anleitung richtet PixelDock32 so ein, dass:

- der Dienst beim Booten automatisch startet,
- Abstürze automatisch durch `systemd` neu gestartet werden,
- ein regelmäßiger Healthcheck den Dienst bei Hängern/Keine-HTTP-Antwort neu startet,
- Autostart per Script ein-/ausgeschaltet werden kann.

## 1) Einmaliges Setup (Copy & Paste)

> Standardpfad im Beispiel: `/home/pi/PixelDock32`

```bash
cd /home/pi/PixelDock32
chmod +x scripts/manage-autostart.sh scripts/pixeldock32-healthcheck.sh
sudo ./scripts/manage-autostart.sh enable --repo-dir /home/pi/PixelDock32
```

Hinweis zu Benutzer/Gruppe:

- Standardmäßig verwendet das Script den aktuellen Aufrufer (`$SUDO_USER`, sonst `id -un`) und dessen primäre Gruppe.
- Falls dein Projekt unter einem anderen Account läuft, explizit setzen: `--user <dein_user> --group <deine_gruppe>`.

Was dabei passiert:

- `/etc/systemd/system/pixeldock32.service` wird aus dem Template erstellt,
- `pixeldock32` wird aktiviert und gestartet,
- `pixeldock32-healthcheck.timer` wird aktiviert,
- Healthcheck läuft jede Minute und prüft `http://127.0.0.1:8000/`.

## 2) Status prüfen

```bash
./scripts/manage-autostart.sh status
systemctl list-timers --all | rg pixeldock32-healthcheck
```

## 3) Logs prüfen

```bash
./scripts/manage-autostart.sh logs
journalctl -u pixeldock32-healthcheck.service -n 50 --no-pager
```

## 4) Autostart deaktivieren

```bash
sudo ./scripts/manage-autostart.sh disable
```

Dadurch werden Service + Healthcheck-Timer gestoppt und aus dem Boot-Autostart entfernt.

## 5) Optional: Healthcheck URL/Timeout anpassen

Standardmäßig prüft das Script die Root-URL mit 8 Sekunden Timeout.

Beispiel manuell testen:

```bash
HEALTH_URL="http://127.0.0.1:8000/" TIMEOUT_SECONDS=8 ./scripts/pixeldock32-healthcheck.sh
```

Wenn du später eine dedizierte Health-Route hast (z. B. `/health`), dann die URL entsprechend setzen und im Script hinterlegen.
