# Roadmap

## Nächste sinnvolle Schritte

1. **Panel-Kalibrierungstest**: kleines Testscript für Pixel-Walk + Mapping-Verifikation je Panel.
2. **Mapping-Wizard**: geführte Kalibrierung für Panel-Reihenfolge, Serpentine und Offset.
3. **Bessere Text-Engine**: Scrolling + größere Font-Auswahl + UTF-8 Glyphen.
4. **API-Resilience**: Retry/Backoff + sichtbarer Status in UI (letztes Update, Fehlerzustand).
5. **Sicherheits-Hardening**: HTTPS via Reverse Proxy, rate limit, Passwort-Hash verpflichtend.

## UI/UX Verbesserungen (Sprint A)

- Globales **System-Status Panel** in der Web-UI (API online, Quelle, Modul, FPS, Debug-Status, Daten-Updates).
- **Toast-Feedback** bei allen UI-Aktionen inklusive Fehlern/Netzwerkproblemen.
- **Quick Presets** für Debug-Pattern (Wiring/Serpentine/Noise Check).
- Neues Backend-Status-API: `GET /api/debug/status`.

## GIF-Support (Roadmap)

Aktuell rendert das Bitmap-Modul statische Dateien mit vertikalem Scrolling. Für kleine GIF-Animationen sind als nächster Schritt nötig:

- Frame-Decoder (z. B. `Pillow`) zum Extrahieren einzelner GIF-Frames inkl. Frame-Dauer.
- In-Memory-Framecache (pro Datei + `mtime`) analog zum Bitmap-Cache.
- Zeitbasierte Frame-Auswahl im Renderloop (`now -> frame_index`) mit sauberem Looping.
- Optionales Dithering/Farbreduktion für bessere Lesbarkeit auf 32x8.
- Einheitliche Einstellungen im Modul (`playback_speed`, `loop_mode`, optional `fit/crop`).
