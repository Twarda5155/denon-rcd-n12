# Local control server

Status: accepted; partly implemented. See "What exists" below, kept current as
of 2026-09-11 — the proposed surface further down is still a proposal and parts
of it may never be built.

## Context

The RCD-N12 exposes two control protocols with disjoint capabilities: HEOS
command `1255` covers volume, mute, and playback, while the AVR interface on
port 23 covers power, source, and sleep. Neither protocol is a superset of the
other, so full control requires talking to both. Port 23 accepts only one
connection at a time, so every consumer that needs power, source, or sleep is
contending for that single socket.

## Decision

Run a single Python process (Flask or `http.server`) bound to localhost,
fronting both device protocols. All JSON. It owns the port 23 connection and
multiplexes callers behind the HTTP API, so nothing else has to serialize
access to the receiver.

Transport routing: volume, mute, and playback go to HEOS 1255 over a held socket;
power, source, and sleep go to port 23 over short-lived connections. `/api/sleep`
falls back to a server-side timer firing `PWSTANDBY` if `SLP` proves unsupported.

## Consequences

- Clients get one uniform HTTP surface instead of two socket protocols with
  different framing and lifecycles.
- The server becomes a single point of failure and the sole owner of the port 23
  connection; if it dies, all power/source/sleep control is lost until restart.
- The sleep fallback timer lives in the server process, so its state does not
  survive a restart.
- `/api/status.volume` reports the HEOS 0-100 scale. If `MV` readback is ever
  surfaced, it must be a separate field, not silently converted.

## What exists

Built on `http.server`, not Flask: the page and the API need no dependency, and
the server runs on a bare interpreter. Port 23 is *not* held open, contrary to
the decision above — the receiver refuses a second connection while one is held,
which would block manual access, so `transport.py` connects per command and
paces instead. That is the one part of this record the implementation overruled.

| Path | Method | Response shape |
|---|---|---|
| `/api/power` | GET, POST `state=on\|standby\|toggle` | `{ok, power}` |
| `/api/volume` | GET, POST `level=0-100` | `{ok, volume, mute}` |
| `/api/volume/step` | POST `direction=up\|down`, `step=1-10` | `{ok, volume, mute}` |
| `/api/mute` | POST `state=on\|off\|toggle` | `{ok, volume, mute}` |
| `/api/source` | GET, POST `name=<input>` | `{ok, source}` |
| `/api/sources` | GET | `{ok, sources: [...]}` |
| `/api/playback` | GET | `{ok, state, title, artist, album, station, media_type}` |
| `/api/favorites` | GET; POST `preset=1-…` | GET `{ok, favorites: [{name, mid, media_type, playable}]}`; POST `{ok, state, title, …}` |

`/api/sources` is the one route that reaches no further than this process: the
input names are a constant, so the page fills its selector on load without
spending a paced device transaction. It replaces the proposed `/api/sources`
shape below — plain names rather than `{id, label}` pairs, because the names
*are* the labels and a second vocabulary would be one more thing to keep in
step.

`/api/mute` and `/api/volume/step` return the whole volume state rather than the
one field they changed, because mute and level are read together anyway and a
caller that has just muted still wants the level on screen.

`/api/favorites` carries both halves of one resource: `GET` lists them, `POST`
starts one by its position. It answers with playback rather than with the
favourite it was given, because what the receiver actually began playing is the
question a caller has next — and for a second after the command the answer is
still the outgoing station, which is why the client waits before reading.

It is also the only way this API reaches the network input. `SINET` is ignored
as a write, but starting a favourite moves the unit there (measured
2026-09-11), so `POST /api/favorites` does what a `net` entry in `/api/sources`
could not.

Playback is a read. `player/set_play_state` was exercised on this unit on
2026-09-08 and *accepted* without changing anything — there was nothing playing
to change — so whether it works is still unknown (open question 16), and this
project does not ship controls that might do nothing.

## API surface

The rest of this table is a proposal from 2026-08-30. The eight rows above are
what actually answers.

| Path | Method | Params | Response shape |
|---|---|---|---|
| `/api/status` | GET | — | `{power, volume, mute, source, sleep_minutes, play_state, now_playing, reachable}` |
| `/api/power` | POST | `state=on\|standby` | `{ok, power}` |
| `/api/volume` | POST | `level=0-100` | `{ok, volume}` |
| `/api/volume/step` | POST | `direction=up\|down`, `step=1-10` | `{ok, volume}` |
| `/api/mute` | POST | `state=on\|off\|toggle` | `{ok, mute}` |
| `/api/sources` | GET | — | `{sources: [{id, label}]}` populated from `SI?` discovery |
| `/api/source` | POST | `id` | `{ok, source}` |
| `/api/transport` | POST | `action=play\|pause\|stop\|next\|prev` | `{ok, play_state}` |
| `/api/sleep` | POST | `minutes=0-120` (0 = off) | `{ok, sleep_minutes}` |
| `/api/events` | GET (SSE) | — | Server-sent events mirroring HEOS change events and `PW` heartbeat |
