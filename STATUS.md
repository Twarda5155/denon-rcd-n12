# Status — updated 2026-09-23

## Repository

Public on GitHub since 2026-09-23, under the MIT license (`LICENSE`). Before
publishing, the history was rewritten so every commit carries the identity
`denon-rcd-n12 dev` and a GitHub noreply address; keep that identity in this
repository's local git config.

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
- **A history of sources and streams, written to the database.** The one thing
  MariaDB was ever wanted for, now named concretely: what input the receiver
  was on and what was playing on it, over time. `get_source` and `get_playback`
  already produce exactly those two facts; nothing keeps them. `logs/device.log`
  is a command trace, not a series — it records that a question was asked, not
  what the answer was at a given hour.

  Three things to settle before building it, none of them measurements:

  - **Who does the sampling.** A recorder wants to poll on a schedule, which is
    the opposite of what `docs/decisions/2026-09-12-staying-current.md` decided
    for the page. That decision was about a page nobody is looking at, so a
    recorder does not contradict it — but it is a second consumer with its own
    appetite, and both share one paced device. It needs its own decision record.
  - **What a sample means when the unit is asleep.** It sleeps after about five
    minutes idle, and reports a phantom volume of 0 and stale now-playing
    metadata while it does. Recording those as observations would fill the
    series with fiction. Standby is probably a row saying "asleep", not a row
    of values.
  - **What a row is.** Sampling every minute makes a series mostly repeating
    itself; recording only transitions makes a much smaller table that answers
    "what did I listen to" directly, at the cost of never knowing what happened
    between two samples.

  The driver is not installed and no code touches a database, deliberately
  since 2026-09-05. Nothing about that changes until this is actually wanted.

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
  machine. Laid out for a horizontal screen rather than a vertical one, since
  it is read on a laptop: the readouts are a strip of six cells across the top
  instead of six stacked rows, which is most of the page's former height on its
  own, and the title shares a line with `check everything`. Below that,
  named columns — power, volume, playback, source — that fit themselves to the
  width with `auto-fit` rather than to breakpoints, so a laptop gets four, a
  tablet two and a phone one. It does not centre vertically: that would spend
  the height the layout just saved.

  Reads out power, volume, sleep, source, transport state and track; writes
  power, volume (absolute and by steps), mute, the input, the transport and the
  timer. Three rules keep it from lying: the track shows solid only at `play`
  and `pause`, because the unit keeps reporting the last thing it loaded
  through a stop and through standby; the power row dims after a source write,
  because an input write wakes a sleeping unit (Q14); and every control whose
  behaviour is not obvious from its label carries a hint — pause stops a
  stream, switching inputs stops playback, the sleep timer is refused while the
  unit sleeps. The input picker is filled from `/api/sources` rather than from
  a copy of the names in the page, opens on a prompt rather than on the first
  input, and holds one entry that is not an input: `favorite 1`, which starts a
  stored station over HEOS.
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
  talks to it. Revisit when there is history worth keeping — which now has a
  name, under "Next step": a series of sources and streams over time.
- **Streamlit dashboard.** Dropped in `cc9b624` in favour of the one-page app.
- **Pushed events / `/api/events`.** Decided 2026-09-12: the page pulls. See
  `docs/decisions/2026-09-12-staying-current.md`.
- **The HTTP `goform` endpoint.** Not a choice any more — measured 2026-09-12,
  the web server answers 403 to everything, so there is nothing to defer to.
- **Wake-on-LAN and any network recovery from deep standby.** Ruled out on
  evidence — see the "Ruled out" table in `docs/reference/web-interface.md`.
  The page should say so rather than retry.
