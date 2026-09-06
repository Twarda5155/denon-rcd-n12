---
source: HEOS CLI session against the local unit, Denon RCD-N12 web manual, third-party reverse engineering
date: 2026-08-30
status: partial
verified_against: HEOS CLI 1255, live device, 2026-08-30; AVR telnet 23, live device, 2026-09-06
untested: standby, sleep, source *selection* (reading sources is measured), HTTP goform
---

# RCD-N12 Control Protocols - Reference

Protocol reference for controlling a Denon RCD-N12 network CD receiver over the
local network. Facts are graded by evidence level below. The control server and
web UI design live in `docs/decisions/`.

## Device facts

Identity and addressing live in `config/device.yaml` (gitignored; see
`config/device.example.yaml` for shape). This unit reports as `Denon CEOL`,
connects over wi-fi, and returns `lineout: 0`.

## Confirmed — observed on this device

Responses below were returned by the physical unit.

- HEOS CLI accepts TCP connections on port **1255**.
- Commands are plain strings terminated with CRLF; responses are single-line JSON.
- Round-trip latency under 500 ms; 300 ms proved sufficient for every query issued.
- `system/register_for_change_events?enable=on` → `result: success`.
- `player/get_players` → payload array containing the identity recorded in
  `config/device.yaml`
- `player/get_volume` → `0`. `player/get_mute` → `off`.
- `player/set_volume?level=1` **changed device state**. Write access is confirmed,
  not merely read access.

Measured 2026-09-06 from `notebooks/01-stan-odtwarzacza.ipynb`, unit starting in standby:

- `PW?` → `PWSTANDBY`; `PWON` **woke the unit from standby over the network**, and
  `PW?` 4 s later returned `PWON`. Open question 4 is answered: network wake works
  and `WAKE_SETTLE_S = 4.0` was sufficient.
- `SI?` → `['SINET']`, the first source token read off this unit. The reply carried
  the token alone — no `PW` heartbeat frame interleaved in a 2.5 s listen window.
  (The rest of the set was measured the same day; see the sweep table below.)
- `player/set_volume?level=8` then `player/get_volume` → `8`. No Volume Limit clamp
  at this level on this unit.
- `player/get_now_playing_media` → `type: station`, `sid: 3`, with `station`,
  `artist`, `image_url`, `album_id: s25028` and an `mid` pointing at a TuneIn stream
  URL. So `sid` 3 is a streaming service (TuneIn), reported while `SI` reads `NET`:
  the two answer different questions and neither replaces the other.

Source-token sweep, 2026-09-06, `notebooks/02-zrodla-si.ipynb` — the operator cycled
inputs at the unit while `SI?` was polled every 2 s:

| Display | `SI` token | Evidence |
|---|---|---|
| Phono | `SIANALOGPHONO` | read back after switching to it |
| AUX | `SIANALOG1` | read back after switching to it |
| No disc (CD) | `SICD` | read back after switching to it |
| Optical | `SIOPTICAL1` | read back after switching to it (second sweep) |
| DAB | `SITUNER` | read back after switching to it (second sweep) |
| HDMI | `SIHDMIARC` | read back after switching to it (second sweep) |
| TuneIn | `SINET` | read back at rest, three times |
| Music Servers (DLNA) | `SINET` | caught mid-sweep switching to it, 20:03:36 |

**All seven inputs on this unit are now known.** Two consequences:

- `SINET` is **ambiguous**: TuneIn and a DLNA server (foobar2000) both report it.
  Which one is playing can only be told from HEOS `get_now_playing_media`, whose
  `sid` distinguishes the service. A UI that shows "source" needs both reads.
  Measured while foobar2000 served files off a LAN share: `type: song`, `sid: 1024`,
  `image_url` pointing at the serving host — and `1024` appears in
  `browse/get_music_sources` as `heos_server` / "Local Music". So the DLNA server
  reports the generic Local Music `sid`, **not** a per-server id, and `heos_server`
  versus `music_service` in that listing is the durable way to tell the two apart.
  TuneIn for comparison: `type: station`, `sid: 3`, `music_service`.
- Token names are not predictable from other Denon models and every guess made here
  was wrong: `SIANALOG1` not `SIAUX`, `SIOPTICAL1` not `SIOPT`, `SIHDMIARC` not
  `SIHDMI` — while the DAB tuner answers to a plain `SITUNER`. The trailing `1` on
  `SIANALOG1` and `SIOPTICAL1` suggests a second input of either kind would be `…2`,
  but this unit has none to check that against.

- The token shape is **not** the one guessed from other models: this unit says
  `SIANALOG1` for AUX and `SIANALOGPHONO` for Phono, not `SIAUX` / `SIPHONO`.
  Nothing here should be extrapolated to the three unknown inputs.
- Music Servers (a foobar2000 DLNA share, playback working) is *indicated* to also
  report `SINET` — the unit read `SINET` at the end of a sweep that finished on that
  input — but it was never caught mid-sweep, so it is not confirmed. If it holds,
  `SI` cannot distinguish TuneIn from a DLNA server and only HEOS
  `get_now_playing_media` can.
- `browse/get_music_sources` → 10 entries: TuneIn (`sid` 3), Deezer (5), SoundCloud
  (9), Tidal (10), Amazon (13), Local Music (1024, `heos_server`), Playlists (1025),
  History (1026), AUX Input (1027), Favorites (1028).
- `browse?sid=1027` **succeeds but does not enumerate physical inputs**: it returns a
  single `heos_service` entry named `Denon` whose `sid` is this player's pid. The
  documented assumption below is therefore half wrong — the call works, the meaning
  does not. Whether browsing that pid lists the inputs is untested.

## Confirmed — external documentation, not tested on this unit

- The RCD-N12 exposes the classic Denon AVR control protocol over **telnet, TCP 23**.
  `PWON`, `PWSTANDBY`, and `PW?` are reported working on this exact model.
- The unit emits an unsolicited `PW` status report approximately every 10 seconds
  on an open port-23 connection.
- There is no true power-off state, only standby. In standby the unit draws ~2 W
  and wi-fi remains active.
- Menu setting **Settings → Network → Network Control** governs whether the network
  stack survives standby. `On` (factory default) keeps the unit reachable and
  controllable while in standby; `Off` suspends network function in standby.
- A Denon receiver accepts only **one** telnet connection on port 23 and refuses
  others while it is held open.
- Sending control commands in rapid succession has been reported to soft-lock
  Denon units.
- Sleep timer exists as a device feature (auto-switch to standby after a set delay).
- On the sibling CEOL model DRA-N4, sleep is controlled by `SLPOFF` and
  `SLP001`–`SLP120` (three digits, minutes).
- Deep standby (3-second power-button hold, or extended network loss) removes the
  device from the network entirely; it can only be woken by a physical button press.

## Inferred or assumed — no evidence either way

- `SLP` sleep-timer syntax is assumed to carry over from DRA-N4 to RCD-N12. Untested.
- `SI?` returns this unit's current input-source token. The full token set for this
  unit was measured 2026-09-06 and now lives in the confirmed section above, so this
  is no longer an assumption.
- The HTTP `goform` endpoint may or may not exist on this firmware. Some 2023-era
  Denons redirect to `https://<ip>:10443` and reject plain HTTP.
- HEOS `browse` with `sid=1027` was assumed to enumerate physical inputs. Measured
  2026-09-06: it does not — it returns one entry pointing back at this player (see
  above). `browse/play_input` for selecting an input remains unverified.
- Assumed the unit needs 2–5 s after `PWON` before it accepts further commands.
- Assumed HEOS port 1255 remains open in standby but returns errors or an empty
  player list. Not measured.
- HEOS CLI concurrent-connection ceiling assumed to be roughly 4–8. Not measured.

---

## Endpoints

### A. HEOS CLI — TCP 1255, CRLF-terminated

All responses are single-line JSON of shape
`{"heos": {"command": …, "result": "success"|"fail", "message": …}, "payload": …}`.

| Path | Method | Params | Response shape |
|---|---|---|---|
| `heos://system/register_for_change_events` | TCP write | `enable=on\|off` | `message: "enable=on"`; enables async push on this socket |
| `heos://player/get_players` | TCP write | — | `payload`: array of player objects |
| `heos://player/get_volume` | TCP write | `pid` | `message: "pid=…&level=0-100"` |
| `heos://player/set_volume` | TCP write | `pid`, `level=0-100` | echo in `message` |
| `heos://player/volume_up` | TCP write | `pid`, `step=1-10` | echo in `message` |
| `heos://player/volume_down` | TCP write | `pid`, `step=1-10` | echo in `message` |
| `heos://player/get_mute` | TCP write | `pid` | `message: "pid=…&state=on\|off"` |
| `heos://player/set_mute` | TCP write | `pid`, `state=on\|off` | echo in `message` |
| `heos://player/get_play_state` | TCP write | `pid` | `message: "pid=…&state=play\|pause\|stop"` |
| `heos://player/set_play_state` | TCP write | `pid`, `state=play\|pause\|stop` | echo in `message` |
| `heos://player/play_next` | TCP write | `pid` | echo in `message` |
| `heos://player/play_previous` | TCP write | `pid` | echo in `message` |
| `heos://player/get_now_playing_media` | TCP write | `pid` | `payload`: object with `song`, `artist`, `album`, `image_url`, `sid` |
| `heos://player/get_play_mode` | TCP write | `pid` | `message` with `repeat`, `shuffle` |
| `heos://browse/browse` | TCP write | `sid` (1027 = AUX/inputs) | `payload`: array of source entries — **assumed** |
| `heos://browse/play_input` | TCP write | `pid`, `input=inputs/…` | echo — **assumed** |

`level` is an absolute 0–100 scale, **not** dB.

### B. Denon AVR protocol — telnet TCP 23, CR-terminated (`\r`, no LF)

Responses are bare ASCII tokens terminated with CR. Queries and unsolicited status
share the same format, so a reader must tolerate interleaving.

| Path | Method | Params | Response shape |
|---|---|---|---|
| `PW?` | TCP write | — | `PWON` or `PWSTANDBY` |
| `PWON` | TCP write | — | `PWON` |
| `PWSTANDBY` | TCP write | — | `PWSTANDBY` |
| `MV?` | TCP write | — | `MV<nn>` |
| `MV<nn>` | TCP write | two digits | `MV<nn>` |
| `MVUP` / `MVDOWN` | TCP write | — | `MV<nn>` |
| `MU?` | TCP write | — | `MUON` / `MUOFF` |
| `MUON` / `MUOFF` | TCP write | — | echo |
| `SI?` | TCP write | — | `SI<TOKEN>`; full set for this unit measured, see confirmed section |
| `SI<TOKEN>` | TCP write | source token | echo |
| `SLP?` | TCP write | — | `SLP<nnn>` or `SLPOFF` — **assumed** |
| `SLP<nnn>` | TCP write | 001–120 minutes | echo — **assumed** |
| `SLPOFF` | TCP write | — | echo — **assumed** |
| *(none)* | passive read | — | `PW…` heartbeat approx. every 10 s |

`MV` here is the AVR-protocol volume scale and is **not** the same scale as HEOS
`level`. Do not mix the two in one UI control without measuring the mapping.

### C. Denon HTTP control — existence unverified on this model

Try port 80 first, then 8080. Status readback is a separate path.

| Path | Method | Params | Response shape |
|---|---|---|---|
| `/goform/formiPhoneAppDirect.xml?<CMD>` | GET | any table-B command as query string | Empty body or minimal XML; HTTP 200 = accepted |
| `/goform/formMainZone_MainZoneXmlStatusLite.xml` | GET | — | XML with `Power`, `InputFuncSelect`, `Mute`, `MasterVolume` |

---

## Ruled out — do not retry

| Approach | Why it fails |
|---|---|
| `StreamReader.ReadExisting()` in PowerShell | Method belongs to `SerialPort`, not `StreamReader`. Use `stream.DataAvailable` plus `Read()`. |
| HEOS CLI for power, standby, or sleep | The protocol has no such commands. It covers playback, queue, volume, and browse only. Power must come from the AVR protocol on port 23 or HTTP. |
| Treating HEOS `level` as decibels | It is an absolute 0–100 scale. `level=1` sets volume to 1/100, it does not add 1 dB. |
| Opening and closing a HEOS socket per command under polling | Exhausts the connection ceiling. Hold one socket with a lock; use registered change events instead of polling. |
| Hardcoding input-source tokens from other Denon models | Token sets differ across models. Query `SI?` on this unit first. |
| Holding port 23 open permanently | The receiver accepts one telnet connection and refuses all others, blocking manual access and any second consumer. Connect, command, close. |
| Firing commands back to back with no delay | Reported to soft-lock Denon units. Pace at 300–500 ms minimum. |
| Home Assistant `heos` integration for on/off | Exposes no power toggle for this device; there is no OFF state to model. Reference implementations use a separate telnet switch. |
| Wake-on-LAN | Device is on wi-fi. WOL would require a wired connection and is not known to be supported. |
| Any network recovery from deep standby | Device leaves the network entirely. Physical button press is the only wake path. Surface this in the UI rather than debugging it. |

## Prerequisites and hazards

- **Network Control must be `On`** (Settings → Network → Network Control) or nothing
  over IP survives standby. Verify before any power testing.
- Volume Limit may be set in the device menu and will silently cap `set_volume`.
- HEOS `level` and AVR `MV` are independent scales.
- The port-23 reader must tolerate the 10-second `PW` heartbeat interleaving with
  command replies.

## Open questions

Moved to `OPEN-QUESTIONS.md` in the repository root, which is the single
register of what is not yet known. Question numbers were preserved, so
references to "open question 4" elsewhere in this file still resolve.

Facts measured here close questions there.

## Probe

Run `python tools/probe_device.py`. Requires the unit powered on and reachable,
and `config/device.yaml` present.

## References

- Denon RCD-N12 web manual, Network Control — <https://manuals.denon.com/RCDN12/NA/EN/BONDSYannpmscn.php>
- Denon RCD-N12 web manual, index — <https://manuals.denon.com/RCDN12/NA/EN/>
- M. Góral, "Telnet isn't dead" (RCD-N12, port 23, `PWON`/`PWSTANDBY`/`PW?`) — <https://goral.net.pl/post/telnet-isnt-dead/>
- bansieau/DRA-N4-API (CEOL Piccolo `goform` command list, `SLP` syntax) — <https://github.com/bansieau/DRA-N4-API>
- Home Assistant `denonavr` integration (single-telnet-connection limit) — <https://www.home-assistant.io/integrations/denonavr/>
- Denon HEOS power management / deep standby — <https://support-uk.denon.com/app/answers/detail/a_id/4749/~/heos-power-management>