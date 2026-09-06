# Status — updated 2026-09-06

## Next step

Expose the input source over the HTTP API and on the page. `client.py` and the
CLI already read and write it; `server.py` and `static/index.html` still know
only power and volume. Immediately after that, verify the first live
`set_source` against the hardware on a harmless input (CD or Optical) — every
`SI` write is so far untested (Q9).

## In flight

Nothing. Working tree clean, `main` even with `origin/main` at `2686618`.

## To do

Roughly in value order.

- `GET`/`POST /api/source` plus a source control on the page. The mapping,
  validation and the `server` asymmetry already live in `client.py`; the server
  only has to expose them.
- Verify `SI` writes on the device. Record the result in
  `docs/reference/web-interface.md` and update the status line of
  `docs/decisions/2026-09-06-source-naming.md`, which currently says
  "reads verified on the device, writes not".
- Mute as a write. `get_volume()` reports it, nothing sets it; HEOS
  `player/set_mute` is documented and the transport already covers that path.
- A single `/api/status` read (power + volume + mute + source). The page now
  needs two round trips to draw itself, and every round trip costs a paced
  device transaction.
- Volume step endpoints (`player/volume_up` / `volume_down`), which avoid a
  read-modify-write cycle for the commonest interaction.
- Sleep timer — blocked on Q3 (syntax unverified on this model).
- Amend or supersede `docs/decisions/2026-08-30-local-control-server.md`. Its
  status line still says "proposed, not implemented" while a subset of the
  described API is implemented, and its table lists endpoints that may never be
  built. A decision record that misstates what exists is worse than none.
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
  reported), source (`get`/`set`) over the measured `SI` token set.
- `server.py` — loopback HTTP API and static page; `GET`/`POST /api/power` and
  `/api/volume`. Connection desync, chunked bodies and port collisions are
  covered by tests.
- `static/index.html` — dependency-free single page, fetches nothing off the
  machine.
- `cli.py` — `serve`, `power`, `volume`, `source`.
- Tests: 79 passed, 18 subtests, all against fakes with the receiver powered off
  (run 2026-09-06).
- `docs/reference/web-interface.md` — protocol facts graded by evidence level;
  all seven input tokens measured.
- `tools/probe_device.py`.

## Deliberately deferred

- **MariaDB persistence.** Decided 2026-09-05: no driver in the env, no code
  talks to it. Revisit only when there is history worth keeping.
- **Streamlit dashboard.** Dropped in `cc9b624` in favour of the one-page app.
- **HTTP `goform` endpoint** (Q6). Telnet plus HEOS cover every capability the
  page needs; a third protocol earns its place only if one of them fails.
- **Wake-on-LAN and any network recovery from deep standby.** Ruled out on
  evidence — see the "Ruled out" table in `docs/reference/web-interface.md`.
  The page should say so rather than retry.
