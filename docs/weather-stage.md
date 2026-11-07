# Weather Stage

Weather remains a regular playlist module with its own scene scheduling, not a
second playlist. `weather_stage=false` retains the classic display, saved options,
and playlist duration.

## Selection and reading time

Four styles: **home**, **station**, **nature**, **neon**. Every style can display
all four information types: outdoor temperature (**outside**), indoor temperature
(**inside**), indoor air humidity (**humidity**) and weather conditions (**conditions**).
By default, a maximum of **two pieces of information per presentation**; the selection rotates fairly.
Browser previews have independent scheduling and do not consume regular rotation slots.

### How a weather presentation reads

Each information runs in three clear steps:

1. **Scene** (≈0.9 s): the whole panel shows what is happening — sun and rays,
   moon and stars, drifting clouds, rain streaks, snowflakes, fog banks, a softly
   glowing (never flashing) storm, a lit house (indoor) or a water level
   (humidity).
2. **Card** (reading time + 0.8 s): an animated 8 × 8 icon on the left and the
   value on the right. The digits roll in once and then **stay still** while
   reading; only the icon moves gently.
3. **Outro** (0.6 s): the card fades back into the scene.

| Icon | Meaning |
|---|---|
| Sun with rays / moon with stars | Clear sky by day / by night |
| Sparkle | Clear sky, day/night unknown |
| Cloud (with sun behind it by day) | Cloudy |
| Cloud with falling drops / flakes | Rain / snow |
| Dark cloud with yellow bolt | Thunderstorm |
| Horizontal bands | Fog |
| House with lit window | Indoor temperature |
| Drop, filled to the measured level | Indoor humidity |
| Thermometer | Outdoor temperature without known conditions |
| Grey cloud with `?` | Conditions unknown |

**Colour of the value** — you can read it without reading the digits:

- Outdoor temperature uses a continuous scale: violet/blue (frost) → ice blue
  (0 °C) → mint (10 °C) → green (18 °C) → yellow (24 °C) → orange (30 °C) → red.
- Indoor temperature: blue = below the comfort range, green = comfortable,
  coral = above it (`weather_comfort_min` / `weather_comfort_max`).
- Humidity: amber = dry (< 30 %), cyan = comfortable, blue = humid (> 60 %).

**Marks**: a small bobbing arrow on the right shows a measured trend (up/down).
A pulsing **amber corner** (top right) plus a faded value means *older than
expected*; a grey `--` means *no value*. Temperatures show one decimal when it
fits (`-5.2°`), otherwise whole degrees (`-12°`).

**Styles** only change the atmosphere, never the layout: *Pixel Home* (house and
warm ground line), *Weather Station* (spinning anemometer, scale ticks with a
needle at the measured value), *Nature World* (trees, swaying grass) and
*Neon Lab* (glowing side bars, travelling light pulse).

Automatic total duration includes introduction, scene, card, reading and outro.
The reading-time setting controls the quiet reading phase; the card adds 0.8 s.
No repeated information or extra stale/missing panels appear after reading.
`POST /api/weather/duration` calculates the same duration from saved and
unsaved options without changing runtime or rotation.

## Sources and freshness

Outdoor temperature and conditions come from **model-based Open-Meteo Current
Conditions for the configured location**, not an observation outside the window.
Day/night and WMO weather codes describe that model data; the animation is not
a locally observed weather event.
Indoor data comes from the configured DHT sensor.

Outdoor data has its own fetch timestamp and becomes stale after **900 seconds**.
Indoor temperature/humidity use only DHT timestamps and become stale after
**300 seconds**. A fresh sensor sample cannot make old outdoor data fresh.
Errors/stale values remain visible; missing values are not invented. Each visit
uses a frozen snapshot.

Trends use at most 24 real samples per metric, at least three spanning five
minutes. Direction requires a change of at least 0.5 °C or three percentage
points. Too few, stale, or invalid samples suppress the trend indicator.
Weather code, day/night, precipitation and wind are retrieved in the same request.
Unknown codes lead to neutral motif, not invented sunshine.

## Preview and security

All `/api/weather` endpoints require login. `GET /api/weather` delivers
Catalog, live information, source information and sleep status. Browser previews and
Duration calculations are passive and do not save any settings.

`POST /api/weather/preview` honors unsaved options and defaults to live data.
Only explicitly marked browser demos may simulate weather codes and day/night.
Sample values are 12 °C outdoors, 22 °C indoors, 48% humidity, and clear daytime
conditions by default. Simulations are not real weather events and must never
reach the hardware.

A direct LED preview only uses live data and the shared one
Preview slot: a new preview replaces the previous one. Regular performances
are paused and then resumed without using up regular rotation.
This preview never saves settings or uses normal `play_once` playback.
In sleep mode it returns HTTP 409: explicitly select **Awake** first;
the preview must neither bypass sleep nor wake up silently.
