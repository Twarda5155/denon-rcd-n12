# Local control server

Status: proposed, not implemented

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

## API surface

Nothing below exists yet.

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
