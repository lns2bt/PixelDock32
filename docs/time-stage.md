# Time-Stage – scene studio and independent clock scheduling

## Sleep scheduling in v0.3.0

- The daily plan uses the configured IANA timezone, independently of the Pi's
  system timezone or the browser timezone. Start is inclusive; end is exclusive.
  Overnight intervals are supported. Daylight-saving gaps roll forward; repeated
  times use the first start and last end, so the display does not wake twice.
- Enter exact `HH:MM` values directly, or use the optional five-minute sliders.
  Each slider changes only its own field. Moving the other slider cannot round
  an exact-minute entry. The selected times, duration, and timezone are visible.
- Saving sends literal local time strings, not converted UTC times. The UI checks
  the acknowledgement and reads the stored configuration back before reporting
  success. Unexpected times produce an error instead of a success message.
- Saves from the current UI include an `If-Match` revision. If another tab has
  changed the settings, HTTP 409 preserves the newer plan and leaves local edits
  visible. Reload explicitly before reconciling changes. Legacy API clients may
  omit the revision for compatibility; they do not receive stale-write protection.
- Temporary exceptions live in a separate `sleep_override` preference, not in the
  daily settings. `POST /api/time-stage/sleep` is the only way to change them.
  Settings saves/imports cannot revive or cancel an exception. Exports omit them.
- **Sleep now** and **Awake** persist an absolute deadline at the next plan boundary;
  **Sleep for 2 hours** persists an exact two-hour deadline. At expiry, the daily
  plan takes over, which may still require sleep. **Automatic** cancels an exception.
  Expired or legacy unbounded exceptions never receive a new deadline on reload.
- Sleep remains authoritative over previews, manual text, diagnostics, and modules.
  At wake-up, the saved daytime brightness and normal playback resume immediately.
  Deployment does not reset user schedules or silently select a new default.
- Sleep status explains the effective policy and next transition. Periods longer
  than twelve hours are highlighted and require confirmation before saving.
  The API exposes the last twenty process-local policy transitions; systemd's
  journal also records transitions. History starts afresh after a service restart.

Mock-only browser regression: `node scripts/sleep-smoke.cjs` with the local fixture
from `scripts/ui-test-server.py`. Never run mutating tests against the physical Pi.

## Five additional second worlds

Now 25 normal clock views: **Orbital Station**, **Pixel Greenhouse**,
**Neon Subway**, **Lighthouse** and **Clockwork Manufactory** complement the previous ones
20 scenes. Satellite orbit, plant growth, train travel, coastal light and gears
follow the actual second including fractions of a second, not the duration
the display. Minute changes trigger small local accents, not full-screen flashes.
At each new minute the changed digits roll like an odometer (right-most digit
first, eased, anti-aliased); unchanged digits never move. The colon breathes
softly with the seconds instead of blinking. Disabling the *minute change effect*
turns the roll off.

HH:MM remains high contrast, without blinking, masking or shifting. The entire thing
19×5 numeric rectangle including spaces is reserved for the clock;
Animations use the sides, top row and the two bottom rows.
Every 60 seconds can be distinguished per scene. sleep mode, events,
Scheduling and existing profiles do not change.

Existing saved scene selections will **not be automatically expanded**.
Select and save new scenes in the time stage or directly with browser/
Check LED preview. New configurations offer all 25 normal ones by default
Views. The static gallery contains 35 examples (25 clocks and 10 events).

## Scope and limit of this step

Step 1 provided 20 normal clock views and 10 special event animations as
pure, stateless 32×8 renderers. Step 2 supplements independent clock control,
Migration, sleep mode, settings and local sky calculation. The contents
other modules remain unchanged.

The library is located in `app/services/time_stage/`. `core.py` defines the common
canvas/metadata interface; six independent style groups deliver the scenes.
`render_scene(key, now, elapsed)` delivers the usual `ModulePayload` without file,
Database, network or hardware access. Rendering time is limited and checked;
Pixels are cropped to the panel and RGB values are limited to 0-255.

Normal second effects refer to `now.second` and microseconds, not
on the time that has passed since the playlist appearance. `elapsed` controls additional
Movement and transitions. Events are finite, 6-10 second choreographies;
the final phase shows the **current** time. Event metadata suggests categories
but do not trigger anything automatically.

## Generate previews

```sh
.venv/bin/python scripts/preview-time-stage.py --output /tmp/opencode/time-stage-preview-v1
```

The output includes a responsive static HTML gallery, GIF/PNG previews,
`catalog.json` and a comparison panel `contact-sheet.png`. Show normal scenes
a real minute in 6× time-lapse; Events happen in real time. All files will be
generated offline – the browser plays pre-calculated images; in the LED render path
no GIF decoding takes place. The gallery does not change the playlist or LEDs and respects
`prefers-reduced-motion`. Original files from downloads will not be published.

Previews simulate logical RGB pixels, not camera capture. Especially with very
If the brightness is low, a later check on the actual display is necessary.

## Implemented step 2

- Independent area **Time Stage**, outside the module playlist.
- Request clock after N regular playlist entries and/or after X seconds;
  Running GIF loops/scrolling texts may end. The time limit is not a hard break.
- Exactly one normal scene per appearance; selectable order, randomness and weighting.
- Special events for `:00`, `:15`, `:30`, `:45`, can be activated separately. After one
  Execute content limit once and replace normal clock display if necessary; none
  outdated event queues, always display the current time.
- Sleep time default 02:00-08:00: only static red-orange HH:MM,
  without seconds/flashes/transitions, own brightness by default 1.
- Global sleep switch: automatic / force sleep / force awake. Manual
  Exception ends at the next schedule switch point. Daylight brightness is retained.
- Dedicated mobile settings page and precise time fields in addition to the 24h timeline.
- Back up data/settings before migration; do not change other module contents.

### Operation

`/time-stage` is a separate mobile site with shared live header. The moon symbol
in the header switches sleep/wake until the next plan change; on the site there is
additionally automatic and “sleep for 2 hours”. Daily sleep time is with time fields
and two precise 24-hour controls. The schedule is only changed when saved.

Regular playlist slots count towards the N-entry rule; Shuffle, priorities and
Not “now”. An event also fulfills the clock requirement. Very short intervals
do not permanently displace the playlist. Without a playlist, the activated clock runs through.
0 deactivates the entry/time rule. Time limits are **soft**; full GIF
Loops, running texts and the Roman treadmill can finish running.

Profiles: All Styles, Retro, Quiet, Favorites or your own selection; up to eight named
Scene profiles can be saved. Weights apply for random selection, immediate repetitions
are avoided. Movement, optional color tone and minute change effect are adjustable.
The browser preview allows freely selected times, real time/time lapse and one
separate button for direct real LED previews. Browser previews
are off-thread and do not change any playlist or hardware; Sky data for simulated
Times are cached separately and to a limited extent.

### Sundial/moon clock

PyEphem 4.2.1 calculates local sunrises and moonsets offline,
civil twilight, golden hour window, peak of the sun, moonlight,
Moon phase, next full/new moons and solstices/equinoxes.
Weather location is standard; Your own coordinates and your own time zone are possible.
The calculation runs off-thread once per minute or after a change of location.

Four primary celestial ceremonies are active by default, 45 seconds each (30-60
adjustable). First a landscape story, then selectable number tables:
Day length/change, twilight, next rise/set, phase/illumination and next
Full moon. Golden hour, solar maximum, full/new moon, solstice and equinox
are additional events that are disabled by default. Missing events in
Polar regions or on individual days remain explicitly unknown; nothing is invented.

Elevation information refers to the calculated horizon at sea level
Standard refraction, not on mountains/buildings/weather. The moon disk is a stylized one
Phase drawing, not a view with location-dependent parallactic angle.
“Moon over the horizon today” sums visible time in the local calendar day.
Night length means today's sunset until the following sunrise;
If there are no horizon changes, the dark part of the local day is used.

### Safety, migration and limitations

- Schema version 1 in `time_stage_preferences`; unknown versions are rejected.
- Legacy clocklines remain archived and disabled instead of being deleted.
  Duration, time zone and priority interval of the first active clock are adopted.
  Old scenes are first mapped to appropriate new scenes; all 20 are available
  and initially activated. Old colors remain in the archive; new art styles use their
  own palettes until a common color is explicitly chosen.
- Other module lines are not changed during migration. Archived clocks appear
  no longer in the playlist; new clocks are not created as a playlist module.
- Night brightness is independent of the saved day brightness. Daily changes
  during the night take effect when you wake up. Also normal “Now” playbacks and
  old diagnostic overrides cannot override sleep mode unnoticed.
- Manual sleep exceptions are persisted with expiration time; no missed events
  after restarts, large jumps in time or waking up. Repeated local hours at
  Daylight saving time resets are not celebrated twice. Non-existent sleep times
  in spring are moved forward by the DST gap.
- Export/Import only contains time-stage settings (location can contain personal information
  be), no access data. Exports reset manual sleep exceptions to automatic.
- In the event of incorrect or empty profiles, the display reverts to a readable clock.
  Status reports rendering/astronomy errors and approximately next clock request.
- No guarantee for a permanently constant 30 FPS; local/Pi tests are not a replacement
  later visual inspection and stability test. Firmware v3 remains unchanged.

## Versioning

GIF import fix, time stage and Bitcoin stage including the compact interface
have been user reviewed on the Pi and approved for publication on `main`.
After a larger step, a separate Pi stand with backup is created.

## Compact operation and shared LED previews

The header matrix is collapsible; Status, brightness and sleep controls remain
reachable. The state is saved per browser. Scenes offer direct
LED previews without overlay warning, even with unsaved colors/options.
Previews save nothing and run in a shared slot with Bitcoin:
new replaces old, then the paused performance runs without rotation consumption
further. Browser previews remain separate and have no hardware effect.
The former `confirm_wake` parameter no longer allows sleep bypass: first
explicitly switch to awake. Also an unsaved sleep configuration
cannot override the actual running sleep policy.
