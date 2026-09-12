# Status — updated 2026-09-12

## Next step

A single `/api/status` read, replacing the four the page makes to draw itself.
The 2026-09-12 decision record settled that the page pulls rather than
subscribes, which makes this the shape the API is heading for rather than a
nicety. It costs about seven paced device transactions in a row, so it needs
timing rather than assuming — and the page has to say it is working rather than
appear hung.

Behind it, a transport control: `play`, `pause` and `stop`. Q16 and Q19 settled
that the command is always honoured and the medium decides what pause means — a
disc pauses and keeps its track, a stream cannot be held and is stopped instead
— so all three verbs can ship with a hint explaining the difference.

## In flight

Nothing. Working tree clean, `main` even with `origin/main`. The 2026-09-12
sweep closed ten questions and emptied the register.

## To do

Roughly in value order.

- `/api/status` and the transport control, above.
- A sleep-timer control. Unblocked 2026-09-12: `SLP` works, three digits,
  001-090, `SLPOFF` to cancel. The receiver holds the state, so nothing has to
  survive a server restart.
- Housekeeping: `check_power_on_off.py`, `check_volume.py` and `get_power_on.py`
  in the repository root are superseded by `client.py` — move anything still
  useful into `tools/` and delete the rest, likewise `_scratch.txt`. Add `~$*`
  to `.gitignore` (Word lock files).

## Done (recent)

- `transport.py` — the only place that opens a socket. Short-lived connections
  on both ports, 23 and 1255 alike, with a shared lock and pacing clock so the
  two never overlap or fire back to back, retry with logging to `logs/`, and
  config read from `config/device.yaml` through a small flat-YAML parser (no
  dependency). Reads past a HEOS `command under process` acknowledgement to the
  answer behind it, which is what made the favourites listing possible.
- `client.py` — power (`get`/`set`/`toggle`), volume (`get`/`set`/`step`),
  mute (`get` via volume, `set`/`toggle`), source (`get`/`set`) over the
  measured `SI` token set, playback (`get`: transport state plus title, artist,
  album, station), and the favourites — listing them and starting one by
  position.
- `server.py` — loopback HTTP API and static page. `GET`/`POST /api/power`,
  `/api/volume` and `/api/source`; `POST /api/volume/step` and `/api/mute`;
  `GET /api/sources` and `/api/playback`; `GET`/`POST /api/favorites`.
  Connection desync, chunked bodies and port collisions are covered by tests.
- `static/index.html` — dependency-free single page, fetches nothing off the
  machine. Two columns of controls under one shared block of readouts, both
  columns starting at the top of the grid so the first button of each lines up;
  a narrow viewport collapses them back to one column. Reads out power, volume,
  source, transport state and track; writes power, volume (absolute and by
  steps), mute and the input. Two rules keep it from lying: the track is shown
  solid only at `play` and `pause`, because the unit keeps reporting the last
  thing it loaded through a stop and through standby, and the power row is
  dimmed after a source write, because an input write wakes a sleeping unit
  (Q14). The input picker is filled from `/api/sources` rather than from a copy
  of the names in the page, and behaves as the volume slider does — the control
  is a request, the row above is the device's answer. The picker opens on a
  prompt rather than on the first input, and `set source` stays disabled until
  something is chosen. It holds one entry that is not an input — `favorite 1`,
  which starts a stored station over HEOS and routes to `/api/favorites`
  instead. `list favorites` renders the receiver's stored stations beneath it.
- `cli.py` — `serve`, `power`, `volume`, `mute`, `source`, `playback`.
- Tests: 149 passed, 31 subtests, all against fakes with the receiver powered
  off (run 2026-09-12).
- `tools/probe_device.py` and `tools/probe_ports.py`.

## Corrections worth remembering

Things this repository asserted and that measurement overturned. Kept because
each one was believed for days.

- **`net` is not a writable input** (2026-09-08). `SINET` is ignored; the
  network input is reached only by starting HEOS playback.
- **`cd/nodisc` means the drive has not read the disc, not that the tray is
  empty** (2026-09-11). Read off a sleeping unit it says `nodisc` with a disc
  sitting in it. This repo said "no disc" twice and was wrong both times.
- **There is no `PW` heartbeat** (2026-09-12). Three code comments and the
  reference described one, carried from third party notes; 75 s of an idle
  socket produced nothing.
- **The HEOS socket was never held open** (2026-09-12). This file claimed it
  was; `transport.py` has always connected per command on both ports.
- **`WAKE_SETTLE_S` was 4.0 s for a unit that answers in under 0.5** — now 1.0.
- **HEOS `level` and AVR `MV` are the same number** (2026-09-12), so the
  standing warning against ever converting between them was moot.
- **The unit sleeps after about five minutes idle** (2026-09-12), whatever the
  input, and neither polling nor the `play` that AUX reports holds it awake — so
  any readout older than that is probably wrong about power.
- **The volume level does not drift on its own** (2026-09-12). One sighting on
  2026-09-08 could not be reproduced in two designed attempts, and the command
  that looked like its cause was cleared by direct test.

## Deliberately deferred

- **MariaDB persistence.** Decided 2026-09-05: no driver in the env, no code
  talks to it. Revisit only when there is history worth keeping.
- **Streamlit dashboard.** Dropped in `cc9b624` in favour of the one-page app.
- **Pushed events / `/api/events`.** Decided 2026-09-12: the page pulls. See
  `docs/decisions/2026-09-12-staying-current.md`.
- **The HTTP `goform` endpoint.** Not a choice any more — measured 2026-09-12,
  the web server answers 403 to everything, so there is nothing to defer to.
- **Wake-on-LAN and any network recovery from deep standby.** Ruled out on
  evidence — see the "Ruled out" table in `docs/reference/web-interface.md`.
  The page should say so rather than retry.
