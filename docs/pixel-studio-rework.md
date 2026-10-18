# Pixel Studio and Dashboard Rework

> Historical implementation notes. The deployment paths and test counts below
> describe this development stage, not the latest release. See README and CHANGELOG
> for the current version; see Time-Stage and GIF editing for current sleep/playback policy.

## Status and scope

The tested status was transferred from `rework/smooth-led-pipeline` to `main`.
The software version `1227bfa` runs on the Pi
`/home/david/PixelDock32-controls-1227bfa`, including brightness, improved
Login contrast and new clock/Bitcoin representations. Firmware v3 remains unchanged.
Previous project directories and backups are retained. No long-term hardware test.

`pixeldock32.service` and `pixeldock32-healthcheck.timer` are for system boot
activated. The permanent drop-in
`/etc/systemd/system/pixeldock32.service.d/90-rework-test.conf` points to the current one
Project and its own venv/`.env`. Despite the historical file name, this is
a persistent configuration, not a temporary test unit. There was no reboot of the Pi
necessary for this confirmation; a new boot test was not carried out.

New main pages:

- `/`: dark dashboard with live data, playlist and quick text message.
- `/modules`: multiple instances of existing modules, duplicate, activate,
  Settings, drag and drop and up/down buttons. Order will be in one
  Transaction saved. Unsaved form changes are announced.
- `/studio`: GIF/PNG import, 32×8 pixel multi-frame editor, color/eraser,
  Undo, duplicate, sort, frame timing and previous frame as a drawing aid.
- `/advanced`: existing diagnostics, mapping and other tools. These pages
  are preserved, not deleted. The original static dashboard and
  Module files are also retained, but are no longer considered main pages
  delivered.

A sticky header shows the rendered matrix on all logged in pages.
The preview is **not a physical camera image and not a confirmation of a frame**.
It is passively accessed at most about five times per second; Status about everyone
five seconds. No parallel polls and hidden tab pausing. No additional ones
Serial probes, no external fonts, CDN scripts or graphics services.

## Assets and Limits

`ASSET_DIRECTORY=data/assets` (relative to the working directory) is its own
private data storage, not the publicly delivered static directory.
Back up this directory together with the database, mapping and `.env` in the future.
It is excluded in `.gitignore`.

- Pillow **12.3.0**, also available as an ARM64 wheel for Python 3.13.
- GIF and PNG; Nearest neighbor, center fit/crop or stretch.
- Transparency is composited on black. GIF frames are created by Pillow
  including compositing/disposal and then decoded in advance.
- Maximum 4 MB upload, 1024 pixels per page, 262144 pixels per source frame,
  8 million decoded source pixels and 512 frames. Frame timing: 33-2000ms
- Sprite JSON and saved assets: maximum 2 MB, 1-512 frames, exactly 256 RGB integers per frame.
  These extended limits are a locally tested GIF import fix, not yet
  Part of the above mentioned Pi stand `1227bfa`. Previously there were 120 frames and
  512 KB for Sprite JSON; GIFs with more frames were misleadingly reported as too large.
- Library maximum 128 assets including the three examples.
- RAM cache maximum eight assets; the current slot also keeps its current one
  Reference. Rendering does not require repeated file accesses or image decoding.
- Asset IDs are validated; Import, library and changes require login.
  Asset deletion is prevented as long as a module references it.
- Editor saving creates a **new copy**, not a silent change to the current one
  Modules. The copy can be added as a module or an existing asset module
  be assigned.

Our own examples **Rooftop Runner**, **Coin Quest** and **Starship Patrol**
are created once with stable IDs. No third-party game graphics included.

## Playlist and LED displays

Existing DB structure remains intact; new instances have unique keys like
`asset-<id>` or `clock-<id>`. Settings remain in the existing JSON field.
No migration or automatic rewriting of existing user configurations.

- Normal modules: fixed order.
- `shuffle=true`: random insertion after three normal slots, not random
  Changing the normal order. For shuffle modules only
  these randomly selected one after the other; immediate repetition is avoided,
  as long as there is more than one module.
- `priority_every`: again at a slot boundary after this interval at the earliest
  show. Clock default: **45 seconds**, default duration **8 seconds**.
  A normal clock appearance also resets the interval. The actual one
  Display can occur later when content is still running.
- GIF/Sprite loops and full text scrolling sequences finish running. The
  The set slot duration is rounded up to a full loop length.
  If the assets are long or the playback is very slow, the clock will also wait longer.
- “Now” plays a module once and then returns with a new slot
  Playlist back. If necessary, the library becomes a deactivated module
  created; This does not automatically expand the normal playlist.
- Please deactivate existing standard modules; their additional instances can
  be deleted. Maximum 128 modules.
- Transitions: smooth crossfade, pixel dissolve, vertical slide or none.
  Transitions are only triggered on module/view changes, never per
  Animation frame restarted. API/UI allow 0-2000ms.

Clock views: classic numbers, arcade figure with second coin, seconds bar,
Binary Accents, Neon Orbit, Neon Digits/Star Flight and Pixel Flip. **Exactly one view
per clock appearance**; the activated views only rotate the next time they appear
(regular, prioritized or “Now”). The former `variant_seconds` is no longer available
used. The animation within the selected view continues. Weather/room climate
have sun, house and drops as temperature/humidity related symbols – the sun
is **not a weather forecast**. Bitcoin has a vibrant coin symbol and
Trend colors. `visual_style=legacy` receives the previous text representations if necessary.

## Validation

```sh
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -v
node --check app/static/shell.js
node --check app/static/arcade.js
```

Hardware-free testing covers import, RGB/timing, limits, path security, authentication,
CRUD, order, shuffle, priority, full loops, play once,
Clock variants and transitions. Additionally local Chromium browser test on desktop
and 390 pixel mobile view: sticky preview, forms, order, draw,
Frame duplication, library and one-time playback. No real hardware included
addressed in these tests.

Current local status: **100 tests successful**, browser smoke also successful.
Additionally, `ITEM0024_32x8.gif` (267 frames, 18.72 s) was local in all three
Scaling modes as well as imported, loaded and as an editor copy via the mobile browser
saved. The original file is not part of the repository.

## Brightness and contrast

- Sun symbol in the header of all logged in pages, without searching in diagnostic tools.
- Exponential controller characteristic `round(exp(log(256) * position / 1000) - 1)`.
  The low values 0-10 occupy around 43% of the path; Integer, ±1 keys and
  Quick values 0/1/3/6/12 enable exact settings. Draggen changes first
  the UI value; is applied when letting go. Numbers and keys work immediately.
- Brightness is stored in the additional table `display_preferences`;
  Existing tables/modules are not rewritten. If a stored value is missing,
  `LED_BRIGHTNESS` from `.env` still applies. **0** is also restored correctly.
- Hardware access remains off-thread and serialized. If the Uno is not reachable,
  The target value remains saved and is applied upon reconnection.
- The login now explicitly has dark backgrounds, light labels/placeholders
  and visible focus frames. Browser smoke checks at least **4.5:1** text contrast.
- Bitcoin: more recognizable ₿ with B loops and double dashes, own pulsating
  Icon color, separated trend colors and directional arrow. Prices from one million euros
  use `M` instead of a truncated representation with `k`.

Reproducible browser smoke test (locally, never against the running Pi):

```sh
# Terminal 1: own temporary data and mock hardware only
TMPDIR=/tmp/opencode .venv/bin/python scripts/ui-test-server.py
# Terminal 2: Install Playwright outside the project directory
npm install --prefix /tmp/opencode/pixeldock-browser playwright@1.64.0
NODE_PATH=/tmp/opencode/pixeldock-browser/node_modules node scripts/ui-smoke.cjs
```

The test uses `/usr/bin/chromium` if available, otherwise the Playwright browser;
if necessary set `CHROMIUM_PATH`.
`PIXELDOCK_UI_ARTIFACTS` enables optional screenshots. Check before making changes
the test that the application really uses the mock backend.

## Later Pi installation

Only create another separate test bench after approval; current rework DB,
`.env`, backup/copy mapping and assets immediately beforehand. The current application
do not overwrite in place. Install new dependency only in the new venv.
Change the existing service drop-in in a targeted manner, pause Healthcheck briefly and
keep previous status for change back. There is **no firmware flash** for this rework
necessary. Existing clock/animation settings (e.g. `transition_ms=0`) remain
effective and can be adjusted in the new form.
