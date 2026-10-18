# Bitcoin Stage

Bitcoin-Stage uses the existing Bitcoin playlist module, not a second playlist.
Other modules, Time-Stage, and saved content remain unchanged. Settings and
browser/physical previews are available at `/bitcoin`.

## Equal rotation

Seven information types: EUR price, block height, sats/€, age of the last block,
fees in sat/vB, blocks remaining until the next halving, and 24-hour price change.
All are enabled by default, with **at most two per presentation** in fair order.
A presentation never duplicates an item or pads a short selection. Random mode
exhausts a shuffled bag before starting another round; at most one item can be
ahead in the rotation.

Each module has independent in-memory rotation state. A restart begins with the
configured order. Browser and physical previews do not consume regular slots.
Configuration changes apply to the next visit; an active visit retains its
snapshot of values and settings.

Each presentation uses one scene, selected independently in order or randomly
without immediate repeats when multiple styles are available. Ten motifs: forge,
blockchain train, mining shaft, nonce search, orbit, transaction rain, terminal,
mechanical counter, Tetris, and gold vein. Every information type works in every
style. These artistic motifs do not represent measured mining/mempool activity.
Motion can be calm, normal, or lively.

Sequence: short introduction, then label → motif → transition → quiet reading
phase for each item, followed by an ending. Reading time defaults to four seconds
(adjustable from 2–15); two items take approximately 17.4 seconds in total.
**Total duration is automatic**, based on item count, reading time, and choreography.
Long numbers extend the visit until scrolling completes. The old playlist duration
is retained for classic mode but is not used by stage mode. The playlist and
Bitcoin page use the same server-side calculation; displayed estimates may grow
for long values or block ceremonies. After reading, only the artistic transition
remains: no repeated label or extra stale/missing panel. Status markers stay
visible while reading. **Sleep can interrupt the presentation immediately.**

## Data and honesty

- Price source continues to be `BTC_API_URL`; CoinGecko call added
  `include_24hr_change=true`. 24h change is **not** the trend since last query.
- Sats/€ = 100 million / EUR price. display rounded; Price K/M compressed.
- Block height still `BTC_BLOCK_HEIGHT_API_URL`. Halving is the next multiple
  of 210,000 blocks, no estimated date. At the end of the subsidy era “END”.
- Optional `BTC_NETWORK_API_URL`, default `https://mempool.space/api`: fee
  recommendations and the timestamp of the exact queried block. Block ID, height,
  and timestamp are validated; concurrent height changes cannot publish a timestamp
  for a different block.
- Fee profiles: economy, approximately one hour, half an hour, or fastest.
  No guaranteed confirmation time and no absolute transaction fee.
- Age is the time since block timestamp, not a prediction of the next block.
- Values are frozen per presentation. Fetch errors or data older than five minutes
  produce a stale marker in orange-red; missing/invalid values show `--` and a
  missing marker. No values are invented and failures do not block rotation.
  Requests run outside the renderer with timeouts and at least sixty seconds
  between fee/block-metadata queries.

## Events and Previews

Three six-second new-block ceremonies: docking, forging, and counter change.
They precede the next Bitcoin visit, outside its regular information limit.
Only a newly observed height increment of exactly one, with fresh consecutive
fetches, qualifies. No celebration on initialization, reorg, large height jump,
long pause, or sleep. Maximum delay is 120 seconds; only the latest event is
retained. Events do not change fair rotation or abruptly interrupt other content.

Browser preview (a value or a complete sample preview) off-thread,
serialized with a maximum of four requests/second, paused when the page is hidden.
Live data is standard; Sample data and simulated block events are clear
marked. A simulation uses invented heights and **may never** start on LEDs.
Real LED preview starts directly without a confirmation dialog and also uses
unsaved options, only real data. In sleep mode HTTP 409,
no silent awakening; first explicitly select “Awake”.

Bitcoin, Weather, and Time-Stage share one physical preview slot: a new preview
replaces the previous one, without a queue. Regular playback resumes with adjusted
timestamps, without consuming another rotation slot. Previews never save settings.
The header collapses to a status line; the choice persists per browser. Details
are collapsible and scene rows have direct LED preview buttons. The save bar is
shown only for unsaved changes.

Offline gallery: `python scripts/preview-bitcoin.py --output OUTPUT_DIRECTORY`.
Ten stories, three events, pause/reduced-motion, highlighted sample data only.
Generated GIFs are deployment artifacts, not stored in the source repository.

New settings complement old BTC settings at runtime without DB migration
or overwriting old colors/name/order/enabled/duration. `bitcoin_stage=false`
continues to use the previous representation. Own color palettes apply to new ones
scenes; The previous color controllers remain for the old display.

Tests: data validation, fair ordering/random, selection, frozen visits,
Event/Sleep/Preview security, all 70 style×info combinations, display
Time limits, API authentication, persistent settings and mobile browser.
No long-term stability test; physical scene effect must be checked on site.
