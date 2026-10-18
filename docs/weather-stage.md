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

Pixel Home shows landscapes, room lights, and droplets; Weather Station uses
animated scales; Nature World uses trees/houses/waves; Neon Lab uses glowing
measurement chambers. Weather codes select sun, moon, clouds, rain, snow, fog,
or a restrained thunderstorm motif without full-screen flashes or strobing.
The reading phase is calm; compact labels distinguish outdoor, indoor, and humidity.

Automatic total duration includes introduction, label, motif, transition, reading,
and ending. The reading-time setting controls the actual quiet reading phase,
not an extra delay afterward. No repeated information or extra stale/missing
panels appear after reading.
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
