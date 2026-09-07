# Status — updated 2026-09-07

## Next step

A source selector on the page, plus `POST /api/source`. Q9 was answered on the
device on 2026-09-07 — `SI` writes work and were confirmed at the front panel —
so nothing blocks it any more. `client.set_source()` already holds the mapping,
the validation and the refusal of the read-only `server` name; the server needs
one route and the page one control.

## In flight

Nothing. Working tree clean, `main` even with `origin/main` at `57df253`.
Source and playback reads landed in three commits — client, server, docs — each
green on its own.

## To do

Roughly in value order.

- The source selector above.
- Q13 — whether the one-poll metadata lag can make `get_source()` call a stream
  `server`. Cheap to test while the unit is on and someone is switching inputs
  anyway.
- Mute as a write. `get_volume()` reports it, nothing sets it; HEOS
  `player/set_mute` is documented and the transport already covers that path.
- A single `/api/status` read (power + volume + source + playback). The page now
  needs four round trips to draw itself, and each one costs a paced device
  transaction. This has grown from a nicety into the obvious next shape of the
  API — but note it would cost about seven device transactions in a row, so it
  needs measuring rather than assuming it is faster.
- Volume step endpoints (`player/volume_up` / `volume_down`), which avoid a
  read-modify-write cycle for the commonest interaction.
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
- `client.py` — power (`get`/`set`/`toggle`), volume (`get`/`set`, mute
  reported), source (`get`/`set`) over the measured `SI` token set, and
  playback (`get`: transport state plus title, artist, album, station).
- `server.py` — loopback HTTP API and static page. `GET`/`POST /api/power` and
  `/api/volume`; `GET /api/source` and `/api/playback`. Connection desync,
  chunked bodies and port collisions are covered by tests.
- `static/index.html` — dependency-free single page, fetches nothing off the
  machine. Reads out power, volume, source, transport state and track; the
  track is shown solid only at `play` and `pause`, because the unit keeps
  reporting the last thing it loaded through a stop and through standby.
- `cli.py` — `serve`, `power`, `volume`, `source`, `playback`.
- Tests: 97 passed, 22 subtests, all against fakes with the receiver powered off
  (run 2026-09-07). The HEOS fixture now carries real recorded now-playing
  payloads for both a DLNA track and a TuneIn station.
- `docs/reference/web-interface.md` — protocol facts graded by evidence level;
  all seven input tokens measured, plus the 2026-09-07 standby and playback
  measurements that closed Q7 and Q12. The playback sweep turned up an
  undocumented fourth transport state, `unknown`, at every transition — it is
  in `PLAY_STATES` and the page treats it as "not playing".
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
- **Playback transport control** (play/pause/next from the page). HEOS
  documents `player/set_play_state`; it was not asked for, and reading the
  state was. Additive whenever it is wanted.
- **HTTP `goform` endpoint** (Q6). Telnet plus HEOS cover every capability the
  page needs; a third protocol earns its place only if one of them fails.
- **Wake-on-LAN and any network recovery from deep standby.** Ruled out on
  evidence — see the "Ruled out" table in `docs/reference/web-interface.md`.
  The page should say so rather than retry.
