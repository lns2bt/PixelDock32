# Roadmap

## Next sensible steps

1. **Panel calibration test**: small test script for pixel walk + mapping verification per panel.
2. **Mapping Wizard**: guided calibration for panel order, serpentine and offset.
3. **Better text engine**: Scrolling + larger font selection + UTF-8 glyphs.
4. **API Resilience**: Retry/Backoff + visible status in UI (last update, error state).
5. **Security hardening**: HTTPS via reverse proxy, rate limit, password hash mandatory.

## UI/UX improvements (Sprint A)

- Global **System Status Panel** in the web UI (API online, source, module, FPS, debug status, data updates).
- **Toast feedback** on all UI actions including errors/network issues.
- **Quick Presets** for debug patterns (Wiring/Serpentine/Noise Check).
- New backend status API: `GET /api/debug/status`.

## GIF Support (Roadmap)

Currently the bitmap module renders static files with vertical scrolling. For small GIF animations the next step is:

- Frame decoder (e.g. `Pillow`) for extracting individual GIF frames including frame duration.
- In-memory frame cache (per file + `mtime`) analogous to the bitmap cache.
- Time-based frame selection in the render loop (`now -> frame_index`) with clean looping.
- Optional dithering/color reduction for better readability to 32x8.
- Uniform settings in the module (`playback_speed`, `loop_mode`, optional `fit/crop`).
