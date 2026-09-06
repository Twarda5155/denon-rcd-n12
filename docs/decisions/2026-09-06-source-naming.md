# Input-source naming

Status: implemented in `client.py`; reads verified on the device, writes not

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
accepting it would promise a choice the command cannot make. The write is also
skipped when the unit already holds the target token, which is why asking for
`net` while a server plays changes nothing and reports back `server`.

## Consequences

- The API is asymmetric on purpose: `set_source` takes seven names, `get_source`
  returns eight. The docstring and the CLI help both say so.
- Comparing against a hardcoded `sid` is simpler than deriving server-ness from
  `browse/get_music_sources` at runtime, at the cost of missing a hypothetical
  second local-media source id. The measurement showed a DLNA server reports the
  generic 1024 rather than a per-server id, which is what makes this safe.
- Selecting a *specific* server or service still has no API. If that is wanted,
  it belongs in a playback command built on HEOS `browse`, not in input
  selection.
- Writing `SI` remains unverified against the hardware. Reading is measured;
  the first live `set_source` should be done on a harmless input.
