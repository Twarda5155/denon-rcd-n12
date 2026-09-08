# Status — updated 2026-09-08

## Next step

**Q17** — find how the network input is selected, since `SI` cannot do it.
It now blocks two things at once: the `net` entry in the source picker, and Q16,
because HEOS-transported media is the only place a pause means anything. The
lead is HEOS playback — `browse/play_stream` on a favourite, or the unverified
`browse/play_input` — with `SI?` watched afterwards to see whether the input
follows the playback.

## In flight

Everything from 2026-09-08 — the source selector, mute, volume steps, and the
measurements behind them. Tests and docs done, tree dirty pending a commit.

## To do

Roughly in value order.

- Q17 above, then Q16 and the transport control it unlocks.
- Q18 — the volume level that moved with nothing sent. If a readout can drift
  on its own, a step control may be fighting something invisible.
- Q15 — the idle timeout before the unit sleeps by itself. It bounds how long
  any readout on the page stays true.
- Q13 — whether the one-poll metadata lag can make `get_source()` call a stream
  `server`. Cheap to test while the unit is on and someone is switching inputs
  anyway.
- A single `/api/status` read (power + volume + source + playback). The page now
  needs four round trips to draw itself, and each one costs a paced device
  transaction. This has grown from a nicety into the obvious next shape of the
  API — but note it would cost about seven device transactions in a row, so it
  needs measuring rather than assuming it is faster.
- Sleep timer — blocked on Q3 (syntax unverified on this model).
- Housekeeping: `check_power_on_off.py`, `check_volume.py` and `get_power_on.py`
  in the repository root are superseded by `client.py` — move anything still
  useful into `tools/` and delete the rest, likewise `_scratch.txt`. Add `~$*`
  to `.gitignore` (Word lock files).

## Done (recent)

- `transport.py` — the only place that opens a socket. Short-lived AVR telnet
  connections on 23, a held HEOS socket on 1255, a shared lock and pacing clock
  so the two never overlap or fire back to back, retry with logging to `logs/`,
  and config read from `config/device.yaml` through a small flat-YAML parser
  (no dependency).
- `client.py` — power (`get`/`set`/`toggle`), volume (`get`/`set`/`step`),
  mute (`get` via volume, `set`/`toggle`), source (`get`/`set`) over the
  measured `SI` token set, and playback (`get`: transport state plus title,
  artist, album, station).
- `server.py` — loopback HTTP API and static page. `GET`/`POST /api/power`,
  `/api/volume` and `/api/source`; `POST /api/volume/step` and `/api/mute`;
  `GET /api/sources` and `/api/playback`.
  Connection desync, chunked bodies and port collisions are covered by tests.
- `static/index.html` — dependency-free single page, fetches nothing off the
  machine. Reads out power, volume, source, transport state and track; the
  track is shown solid only at `play` and `pause`, because the unit keeps
  reporting the last thing it loaded through a stop and through standby.
  Writes power, volume (absolute and by steps), mute and the input. The input
  picker is filled from `/api/sources` rather than from a copy of the names in
  the page, and it
  behaves as the volume slider does — the control is a request, the row above
  is the device's answer. After a source write the power row is dimmed rather
  than re-read, because an input write wakes a sleeping unit (Q14) and the row
  can no longer be trusted.
- `cli.py` — `serve`, `power`, `volume`, `mute`, `source`, `playback`.
- Corrected 2026-09-08: `net` is not a writable input on this unit. `SINET` is
  ignored, so `set_source` refuses both network names, `/api/sources` and the
  page's picker list six inputs rather than seven, and the CLI's choices match.
  Yesterday's selector would have offered an input that silently did nothing.
- Tests: 131 passed, 29 subtests, all against fakes with the receiver powered
  off (run 2026-09-08). The HEOS fixture now carries real recorded now-playing
  payloads for both a DLNA track and a TuneIn station.
- `docs/reference/web-interface.md` — protocol facts graded by evidence level;
  all seven input tokens measured, plus the 2026-09-07 standby and playback
  measurements that closed Q7 and Q12. The playback sweep turned up an
  undocumented fourth transport state, `unknown`, at every transition — it is
  in `PLAY_STATES` and the page treats it as "not playing". 2026-09-08 added
  the three HEOS writes, the `SINET` write refusal, and the observations behind
  Q15, Q17 and Q18.
- `docs/decisions/2026-08-30-local-control-server.md` — amended 2026-09-07 with
  a "What exists" table, so it no longer claims nothing is implemented, and it
  now records that holding port 23 open was overruled by the hardware.
- `notebooks/03-odtwarzanie.ipynb` — prototype for the playback reads, run
  through on the device 2026-09-07; its closing section carries the results that
  closed Q12 and corrected `PLAY_STATES`.
- `tools/probe_device.py`.

## Deliberately deferred

- **MariaDB persistence.** Decided 2026-09-05: no driver in the env, no code
  talks to it. Revisit only when there is history worth keeping.
- **Streamlit dashboard.** Dropped in `cc9b624` in favour of the one-page app.
- **Playback transport control** (play/pause/next from the page). No longer a
  choice — it is blocked on Q16. The command is accepted by this unit and has
  never been seen to change anything, so the control cannot ship until real
  playback proves it works.
- **HTTP `goform` endpoint** (Q6). Telnet plus HEOS cover every capability the
  page needs; a third protocol earns its place only if one of them fails.
- **Wake-on-LAN and any network recovery from deep standby.** Ruled out on
  evidence — see the "Ruled out" table in `docs/reference/web-interface.md`.
  The page should say so rather than retry.
