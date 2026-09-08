# Input-source naming

Status: implemented in `client.py`; reads and writes both verified on the device
(writes 2026-09-07, CD → Optical → CD, confirmed at the front panel)

## Context

The AVR protocol names inputs with `SI` tokens that were measured on this unit
on 2026-09-06 (`docs/reference/web-interface.md`). They are model-specific and
unguessable: `SIANALOG1` for AUX, `SIOPTICAL1` for Optical, `SIHDMIARC` for
HDMI, but a plain `SITUNER` for a DAB tuner. Every name guessed from other Denon
models before measuring turned out wrong.

One token is ambiguous. `SINET` is reported both when a streaming service plays
(TuneIn, measured `sid` 3) and when a DLNA server on the LAN plays (foobar2000,
measured `sid` 1024, listed as `heos_server` / "Local Music"). The AVR protocol
cannot tell the two apart; HEOS `player/get_now_playing_media` can.

## Decision

Expose our own input names rather than raw tokens, mapped in `SOURCES`:
`phono`, `aux`, `cd`, `optical`, `tuner`, `hdmi`, `net`. The network input's
second meaning gets an eighth name, `server`.

`get_source()` returns one name as a `str`, mirroring `get_power()`. It spends
a HEOS round trip only when the token is `SINET`, comparing the playing `sid`
against `LOCAL_MEDIA_SID = 1024` to choose between `net` and `server`. Every
other input is answered from the `SI` reply alone.

`set_source("server")` raises `ValueError`. Both names would write the same
`SINET`, but what then plays is decided by HEOS playback, not by `SI`, so
accepting it would promise a choice the command cannot make.

**Amended 2026-09-08:** `set_source("net")` now raises too, and `net` is absent
from `SELECTABLE_SOURCES` and from the page's picker. The unit was measured
ignoring `SINET` as a write — no echo, no change, awake or asleep — while
`SICD`, `SIANALOG1` and `SIOPTICAL1` all switch within a second. The old
"skip the write when the unit already holds the token" path is gone with it:
it would have answered `net` as though the write had worked. An unsupported
input reported as an unsupported input beats a control that silently does
nothing.

## Consequences

- The API is asymmetric on purpose, and 2026-09-08 widened the gap:
  `set_source` takes six names, `get_source` returns eight. The docstring and
  the CLI help both say so.
- Comparing against a hardcoded `sid` is simpler than deriving server-ness from
  `browse/get_music_sources` at runtime, at the cost of missing a hypothetical
  second local-media source id. The measurement showed a DLNA server reports the
  generic 1024 rather than a per-server id, which is what makes this safe.
- Selecting a *specific* server or service still has no API. If that is wanted,
  it belongs in a playback command built on HEOS `browse`, not in input
  selection.
- Writing `SI` was verified on the hardware 2026-09-07 (CD to Optical and
  back, confirmed at the front panel) and found selective on 2026-09-08: it
  works for physical inputs and not for the network one.
- The network input is now unreachable from this project. Getting it back means
  driving HEOS playback rather than the AVR protocol — open question 17 — which
  is the same mechanism the third consequence above already pointed at for
  selecting a specific service.
