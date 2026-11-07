# Modules and features

## Module Settings (UI)

Module-specific settings can be edited and saved directly in the module management:

- **Clock**: `timezone`, seconds display on/off, adjustable `char_spacing`
- **BTC**: compact k-format display (e.g. `56.8k`), adjustable `char_spacing`
- **Weather**: Temperature in Celsius (city name hidden), optional postal code info, adjustable `char_spacing`
- **Text Box**: Line/ticker text with adjustable `char_spacing`

The values are saved via `PUT /api/modules/{id}`.

## Color logic of the modules

- **BTC**: Leading `B` is orange. Price in `k` format turns green if the price is rising, red if the price is falling, yellow if the price is unchanged.
- **Weather**: Temperature is displayed color coded from cold (blue) to warm (red).
- **Virtual Preview**: displays these colors live via `GET /api/debug/preview`.

## Multiline & Transition animation

- New module **Text Box** for short multi-line texts (`lines`) with automatic line change (`line_seconds`).
- All text modules support vertical transitions when changing content:
  - `transition_direction=down` (new line from top to bottom)
  - `transition_direction=up` (new line from bottom to top)
- Transition duration adjustable via `transition_ms` (0 = without animation).
- For the **Clock module**, the second-cycle sliding is deactivated by default (`transition_on_content_change=false`) so that the slide is primarily visible when changing modules.

## Clock seconds edge

The Clock module optionally supports a dynamic 1px border as a seconds visualization:

- `seconds_border_mode=off`: disabled
- `seconds_border_mode=linear`: linear progress over the minute
- `seconds_border_mode=two_forward_one_back`: animated "2 forward, 1 back" progression
- `seconds_border_mode=dual_edge`: additional mode with growth from two starting points
- `seconds_border_color`: Color of the second edge

The border is empty for `0s` and completely filled for `59s`.

## Bitmap module (32px wide, vertical scrolling)

- Module **Bitmap** loads bitmap files from `app/bitmaps/` (Monochrome **and RGB**).
- Supported formats:
  - Plaintext bitmaps (`0/1`, `#`, `X`, `@`)
  - Plaintext color tokens per pixel (e.g. `#RRGGBB`, `r:g:b`, `0xRRGGBB`, `off`)
  - `P1`-PBM (Monochrome)
  - `P3`-PPM (RGB)
- Expected width: **32 pixels**. Height can be greater than 8.
- At height `> 8` an 8-line window is scrolled vertically:
  - `scroll_direction=top_to_bottom`
  - `scroll_direction=bottom_to_top`
- Scroll speed above `scroll_speed` (recommended 0.25 to 20).

Example files: `app/bitmaps/sample_arrow.txt` (mono) and `app/bitmaps/sample_gradient.ppm` (RGB)

## Smooth motion pipeline

All effects share `app/services/fx.py`: a linear-light float canvas with
sub-pixel (anti-aliased) dots, lines, glows and sprites, OKLab gradients (no
muddy midpoints), easing curves and deterministic noise. Rendering stays a pure
function of time, so browser previews and LEDs match.

The **output stage** (`app/services/output_stage.py`) runs on the Pi just before
the serial transfer and needs **no firmware change**. It replicates the Uno's
brightness scaling (`(v × (b + 1)) >> 8`), applies `LED_GAMMA` and quantises
once. Lit pixels always keep at least one output step on their dominant channel,
so dim night art never disappears at low brightness. Optional
`LED_TEMPORAL_DITHER=true` adds sigma-delta dithering for even smoother dark
fades (it may shimmer slightly at very low brightness). `LED_GAMMA=1.0` restores
the previous output byte-for-byte. The browser preview always shows the authored
colours; with gamma enabled the LEDs now look much closer to it.

## Transitions between modules

`transition_effect` per playlist entry, `transition_ms` sets the duration:

| Effect | Look |
|---|---|
| `fade` | Gentle cross-fade in linear light |
| `dissolve` | Pixels fade over in an even, Bayer-ordered pattern |
| `slide` | Eased, sub-pixel vertical slide (`transition_direction` up/down) |
| `push_left` / `push_right` | The new screen pushes the old one sideways |
| `wipe` | Soft-edged wipe with a short highlight on lit pixels |
| `iris` | Elliptical opening from the centre |
| `morph` | Lit pixels fly in small arcs to their new positions |
| `glitch` | Short digital row shift with colour split (no full flash) |
| `none` | Hard cut |

## Animations module

Fifteen presets. `palette=auto` (default for new modules) uses each preset's
signature colours; `neon`, `rainbow`, `fire`, `ocean`, `matrix`, `aurora`,
`sunset`, `ice` and `forest` override them. `mirror_mode` is `none`,
`horizontal`, `vertical` or `quad`.

- **New**: Aurora, Water Ripple, Fireflies, Sine Ribbons, Synthwave, Embers,
  Game of Life (cells fade in/out, reseeds when stagnant) and Starfield (parallax
  with periodic warp bursts).
- **Reworked**: Plasma (depth layer), Rainbow Tunnel (continuous brightness),
  Bit Invaders (gliding, two-frame legs, starfield), Neon Equalizer (fractional
  bar tops, falling peak markers), Matrix Rain (sub-pixel heads, long afterglow),
  Lava Lamp (soft edges, four blobs), Pixel Snake (smooth Lissajous path).

`scripts/preview-animations.py --output <dir>` renders GIFs and contact sheets of
all presets and transitions without hardware.
