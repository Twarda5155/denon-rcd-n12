# Status — updated 2026-09-12

## Next step

None owed. The project does what it was built for: the page reads and drives
power, volume, mute, the input, the transport, the sleep timer and the
favourites, every capability measured on the unit rather than carried from
another model, and the open-questions register is empty.

What could come next, if it is wanted rather than owed:

- **Favourites as a list you can start**, instead of `favorite 1` as a fixed
  entry in the source picker. `list_favorites` already returns each `mid` and
  `browse/play_preset` already takes a position.
- **The page drawing itself on load** from `/api/status`, rather than opening
  on six dashes. It costs one 3.8 s read per visit, which is the trade to think
  about.
- **History**, the one thing MariaDB was ever wanted for. Nothing records what
  the receiver was doing over time; the device log is a command trace, not a
  series.

## In flight

Nothing. Working tree clean, `main` even with `origin/main`.

## To do

Empty.

## Done (recent)

- `transport.py` — the only place that opens a socket. Short-lived connections
  on both ports, 23 and 1255 alike, with a shared lock and pacing clock so the
  two never overlap or fire back to back, retry with logging to `logs/`, and
  config read from `config/device.yaml` through a small flat-YAML parser (no
  dependency). Reads past a HEOS `command under process` acknowledgement to the
  answer behind it, which is what made the favourites listing possible.
- `client.py` — power (`get`/`set`/`toggle`), volume (`get`/`set`/`step`),
  mute (`get` via volume, `set`/`toggle`), source (`get`/`set`) over the
  measured `SI` token set, playback (`get`/`set`: the transport plus title,
  artist, album, station), the sleep timer (`get`/`set`, 1-90 minutes), the
  favourites — listing them and starting one by position — and `get_status`,
  which is all of the above in one call.
- `server.py` — loopback HTTP API and static page. `GET`/`POST /api/power`,
  `/api/volume`, `/api/source`, `/api/playback`, `/api/sleep` and
  `/api/favorites`; `POST /api/volume/step` and `/api/mute`; `GET /api/sources`
  and `/api/status`, the last reading everything in one go, measured at 3.7-3.9 s
  over eight paced transactions. Connection desync, chunked bodies and port
  collisions are covered by tests.
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
  A `check everything` button spans both columns and fills every row from
  `/api/status`; `play`, `pause` and `stop` sit under the playback read with a
  hint saying what pause does to a stream; the sleep timer is a picker with its
  own hint, because the receiver refuses it while asleep.
- `cli.py` — `serve`, `status`, `power`, `volume`, `mute`, `source`,
  `playback`, `sleep`.
- Tests: 179 passed, 50 subtests, all against fakes with the receiver powered
  off (run 2026-09-12).
- Housekeeping, 2026-09-12: the three bring-up scripts in the repository root
  and `_scratch.txt` are gone, superseded by `client.py` since the first week.
  Each hardcoded the receiver's address, which the project's own rules forbid,
  so they were also a standing counterexample sitting at the top of the tree.
  Git history keeps them. `~$*` is ignored now, so Word lock files stop
  appearing in `git status`.
- `tools/probe_device.py`, `tools/probe_ports.py`, and `tools/probe_identity.py`
  — the last prints a ready-to-paste `config/device.yaml` for a receiver at a
  given address, because `device.example.yaml` says its values come "from
  player/get_players" and that is true of three keys, misleading for `model`,
  and impossible for `host`.

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
- **`SLP` is refused in standby** (2026-09-12), silently, like every other
  refusal on this unit. Found by building the control and watching it report
  success while changing nothing.

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
