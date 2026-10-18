# GIF selection and playback

## Prepare import

In Pixel Studio, open **Prepare import** after choosing a file. This section opens
automatically for more than 512 source frames. Analysis does not save anything.

- **Remove frames:** Enter number at start and end.
- **Keep time range:** start/end in seconds; a blank end means the end of the
  animation. The selection expands outward to complete frames.
- **Keep every … frame:** 2 keeps every other frame. Skipped durations are added
  to the preceding retained frame, preserving the selected running time.
  Holds longer than 2000 ms are split into identical frames, so thinning may not
  reduce the count by exactly the selected factor.
- Summary shows frame count, runtime, seconds removed and real limits.
- “Check selection as animation” only decodes the selection for browser preview;
  neither the library, playlist nor hardware are changed. First and last
  Frames are visible next to each other to check the loop transition.
- Only “Import” creates a new asset. Original file remains unchanged.

Limits: 4 MB upload, maximum 4096 source frames for preparation, 8 million
source pixels across the animation, at most 1024 pixels per side and 262144 per image.
Finished assets: maximum 512 frames, minimum one frame, 33-2000 ms per frame.
Very large source images still need to be reduced externally. analysis and
Decoding takes place outside the render loop without collecting source frames.

## Editor

“Trim Area / Thin Frames” offers the same selection. “Play selection only”
checks the area before applying. Apply to Draft is reversible.
**Save to library** always creates a **new variant**. It neither overwrites the
original asset nor replaces playlist references. Select the variant in the
relevant playlist module's settings when desired.

## Playlist modes

| Mode | behavior |
| --- | --- |
| Maximum duration (default) | Change at the set time limit, even in the middle of the loop. Short loops repeat. |
| One complete cycle | Exactly one asset cycle; duration field hidden. |
| Timeout + End Loop | Change at the first loop boundary at or after the time limit. |

Running time includes every frame duration and playback speed: a twelve-second
source at 2× takes six seconds per cycle. The playlist previews the resulting
duration. **Play now** uses the same rule as regular playback. Time-Stage waits
for this content boundary; **sleep can interrupt immediately**. Bitcoin,
scrolling text, and independent clock scheduling are unchanged.

Existing asset files and saved module times will not be migrated.
Without `settings.playback_mode`, `limit` now applies instead of the previously implied one
Loop extension. `once` and `finish_loop` can be selected per asset module.
