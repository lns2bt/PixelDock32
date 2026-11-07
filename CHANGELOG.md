# Changelog

All notable changes to PixelDock32 are documented in this file.

## [0.4.0] - Unreleased

### New

- Perceptual LED output stage on the Pi: gamma correction (`LED_GAMMA`, default
  2.2) that replicates the Uno's brightness scaling exactly, keeps dim pixels
  visible at low brightness and optionally dithers (`LED_TEMPORAL_DITHER`).
  No firmware change; `LED_GAMMA=1.0` restores the previous output.
- Shared effects toolkit (`fx.py`): linear-light float canvas, anti-aliased
  sub-pixel drawing, OKLab gradients, easing and deterministic noise.
- Nine eased module transitions: fade and dissolve (reworked), sub-pixel slide,
  push left/right, soft wipe, iris, pixel morph and glitch.
- Eight new animations: Aurora, Water Ripple, Fireflies, Sine Ribbons,
  Synthwave, Embers, Game of Life and Starfield; new palettes and `auto`.
- Time-Stage clocks: odometer-style digit roll at each minute and a softly
  breathing colon.
- Weather-Stage redesign: full-width weather scene, then a clear card with an
  animated icon and a colour-coded value (temperature scale, comfort and
  humidity colours), trend arrow and amber stale marker.
- `scripts/preview-animations.py` renders offline GIFs and contact sheets.

### Improved

- All seven existing animations reworked for smooth sub-pixel motion and
  softer edges.
- Cross-fades mix in linear light; dissolve uses an even Bayer order instead of
  visible diagonals; the slide no longer jumps in eight hard steps.

### Compatibility

- Saved modules, schedules, assets and mapping are unchanged. Existing palettes
  and transition names remain valid; new animation modules default to `auto`.
- Uno firmware unchanged.

## [0.3.0] - 2026-10-18

### Fixed

- Daily sleep settings and temporary overrides now have separate persistence.
  Saving or importing settings cannot revive, cancel, or replace a manual exception.
- Expired overrides resolve to automatic mode consistently in the API and renderer.
  Legacy exceptions without a deadline are ignored rather than renewed after reload.
- Sleep sliders update only their own time field. Adjusting the other slider cannot
  round an exact-minute entry. Sliders use five-minute steps with visible values.
- Saves verify the server acknowledgement and read back the stored sleep times.
  Mismatches are reported as errors; stale browser tabs are rejected with HTTP 409.
- Sleep status shows the effective policy, deadline, and timezone. Long daily sleep
  periods show their duration and require confirmation before saving.
- Bounded transition history and journal entries make policy changes traceable.

### Added

- Running server version in the shared navigation and passive `GET /api/version`.
- Sleep regression tests for save/reload, stale tabs, exact-minute inputs,
  acknowledgement mismatches, restarts, DST, and immediate brightness restoration.
- English documentation, interface, comments, and release conventions. Existing
  saved user names/content, schedules, modules, assets, and mapping are preserved.

### Deployment

- Separate Raspberry Pi deployment with a private data backup and rollback path.
- Uno firmware unchanged. No system reboot required.

## [0.2.1] - 2026-10-15

### New

- Five normal time stage views: Orbital Station, Pixel Greenhouse,
  Neon subway, lighthouse and clockwork factory.
- Second animations follow the actual time instead of the display duration;
  all 60 second states are distinct. Small local accents mark minute boundaries.
- Fixed, high-contrast HH:MM number field without overlap or flashing.
- Time stage with a total of 25 normal views, browser/LED previews and
  updated static gallery with 35 examples.

### Preservation and testing

- Existing scene selection, profiles, events, sleep mode, modules and assets
  remain unchanged. New views can be specifically added to the rotation.
- 243 local tests (optional weather metrics test skipped), 242 Pi tests as well
  Mobile browser and gallery checks successful.
- Current Pi status set up as a permanent systemd autostart; no
  Firmware change and no reboot required for release.

## [0.2.0] - 2026-10-14

### New

- Pixel Studio with GIF/PNG import, animation editor, variants and playlist management.
- Shorten GIFs by frame number or time range before import or in the editor;
  Thin frames in time, check selections in advance and undo changes.
- Import preparation for up to 4096 source frames; finished assets up to 512 frames.
- Three GIF playback modes: maximum duration, one full playthrough and
  Time limit with subsequent loop completion; Speed taken into account in the duration calculation.
- Time stage with 20 clock views, events, independent scheduling,
  Sleep mode and offline calculated sun/moon ceremonies.
- Bitcoin stage with ten styles, seven fair rotating info and block ceremonies.
- Weather Stage with four styles for Outdoor, Indoor, Humidity and Current Weather;
  Sun/moon/clouds/rain/snow/fog and muted thunderstorm motifs.
- Open Meteo weather code, day/night, precipitation and wind from a common query;
  Separate updates for external and sensor data as well as trends from real measured values.
- Compact mobile settings, collapsible persistent header and direct
  LED previews with unsaved options, no overlay dialog.
- Shared preview slot with replacement instead of queue and continuation
  paused performances without using up regular rotation slots.

### Corrected

- GIF display duration defaults to a true maximum duration instead of silent
  Extension to the next loop boundary; also applies to “Now”.
- Bitcoin and weather ideas use a unified automatic
  Duration calculation, without additional playlist minimum duration.
- No new old information labeling between reading phases.
- Fresh indoor measurements can no longer mark outdated outdoor data as fresh.
- Sleep protection also applies to previews; simulated data remains exclusively in the browser.

### Operation and testing

- Reworked data path for around 30 FPS, Uno firmware v3 and persistent brightness.
- Hardware-free API, renderer, controller, data, firmware and browser testing.
- Separate Pi installations with backup; Preserve existing settings and assets.
- Current Pi testing: 236 tests successful, local testing: 237 tests successful.
- Note: Indoor values ​​require valid DHT measurements. The sensor used reports
  currently reading error; missing values ​​appear correctly as `--`. Open-Meteo delivers
  Model-based conditions, no weather observation directly on the device.

## [0.1.0] - 2026-07-09

### Status

- First working version of the project marked as stable.
- Suitable as a return point before the next feature and UI improvements.

### Included

- FastAPI web interface to control the 32x8 pixel display.
- Modular rendering with clock, textbox, bitmap, weather and BTC modules.
- Debug, mapping and preview tools for panel setup and troubleshooting.
- USB serial transport to the Arduino UNO R3 including frame ACK support.
- Raspberry Pi systemd services, health check and autostart help.
- Project documentation for setup, hardware mapping, API, modules and roadmap.

### Note

This release is intentionally intended to be a visible GitHub snapshot. For permanent marking, a Git tag `v0.1.0` should also be set to this status after the merge.
