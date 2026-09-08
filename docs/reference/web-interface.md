---
source: HEOS CLI session against the local unit, Denon RCD-N12 web manual, third-party reverse engineering
date: 2026-08-30
status: partial
verified_against: HEOS CLI 1255, live device, 2026-08-30 and 2026-09-07 (in standby); AVR telnet 23, live device, 2026-09-06
untested: sleep, HTTP goform
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
Measured 2026-09-07, unit in **standby** throughout, over `transport.py`:

- **HEOS on 1255 answers normally while the unit sleeps.** Not a refused
  connection, not an empty player list, not an error reply: `player/get_players`
  returned the full player object (`Denon CEOL`, wifi, serial), `get_volume` →
  `level=0`, `get_mute` → `off`, `get_play_state` → `state=stop`, and
  `get_now_playing_media` returned a complete payload. **Open question 7 is
  answered:** the page can read playback state in standby without special
  handling. Whether `level=0` is standby forcing the level down or the level
  genuinely being 0 was not established — the unit was not woken to compare.
- `player/get_play_state` → `message: "pid=…&state=stop"`. The state is in
  `message`, not in `payload`, unlike the media metadata.
- **The metadata outlives what produced it.** In standby the unit still reported
  the last track of the previous session (`type: song`, `sid: 1024`, song, album
  and artist from the foobar2000 share) alongside `state=stop`. So
  `get_now_playing_media` says *what is loaded*, never *whether it is playing*;
  only `get_play_state` says that. A UI showing a title must show the state
  beside it or it will claim music is playing to an empty room.
- `player/get_play_mode` → `repeat=off&shuffle=off`.
- **A station fills in `song` *and* `station` at once.** From the recorded TuneIn
  reply: `type: station`, `sid: 3`, `song: "Deutschland national"` (the track on
  air), `station: "Klassik Radio"`, `artist` repeating the station name, `album`
  an empty string. A "track name" should therefore prefer `song` and carry
  `station` as its own field; collapsing the two loses whichever the caller
  wanted. A DLNA track by contrast has `song`, `album`, `artist` and no
  `station`.

Measured 2026-09-07 from `notebooks/03-odtwarzanie.ipynb`, unit powered on, the
operator cycling inputs and working the transport from the remote:

- **HEOS reports a fourth transport state, `unknown`,** which the HEOS command
  reference does not document. It appears for a poll or two at every transition
  — starting playback, and switching inputs — and then resolves. It is a
  settling state, not an error, and any consumer that validates `state` against
  `play`/`pause`/`stop` will reject a perfectly normal reply.
- **`pause` is real on this unit** — observed on CD at 22:28:24 and 22:31:12,
  distinct from `stop`. The full measured set is `play`, `pause`, `stop`,
  `unknown`.
- **HEOS knows the metadata for every input, not just the network ones.** This
  contradicts the expectation that a network protocol would be blind to CD and
  the analogue inputs. Each input reports its own `sid` and its own title:

  | Input (`SI`) | `sid` | `type` | `song` observed |
  |---|---|---|---|
  | `SICD` | 1024 | `station` | `Denon - CD`, then `Track 1` |
  | `SIANALOG1` (AUX) | 1027 | `station` | `Denon - AUX` |
  | `SINET`, TuneIn playing | 3 | `station` | `Drift`, station `1.FM Gaia` |
  | `SINET`, TuneIn stopped | 3 | `station` | `192 kbps mp3` |
  | `SINET`, DLNA server | 1024 | `song` | the track (2026-09-06) |

  Three consequences. **`type` does not discriminate**: everything above came
  back as `station` except the DLNA track, so it cannot be used to tell a stream
  from a disc. **`sid` 1024 is not proof of a DLNA server** — the CD transport
  reports it too, so the `SINET`-plus-1024 test in `get_source()` is only sound
  because it is asked exclusively for the `SINET` token. And **`song` is
  whatever the input has to say**, not necessarily a track: a stopped TuneIn
  stream puts its bitrate there, and the AUX input its own name.
- **The metadata lags an input change by about one poll.** At 22:28:36 the unit
  reported `SIANALOG1` while still carrying the CD's `sid` 1024 and `Track 1`;
  the AUX values landed on the next read four seconds later. A playback read
  taken immediately after an input change can therefore describe the previous
  input.
- **`state=play` on AUX does not mean audio.** The AUX input reported `play` for
  the whole time it was selected and then fell to `stop`, with no relationship
  to what the attached device was doing. The state is meaningful for media the
  unit itself transports; on a passthrough input it reports the input, not the
  sound.

**`SI` writes work.** First ever exercised on this unit 2026-09-07, 23:11, with a
CD playing and the operator watching the front panel:

```
-> SI?          <- SICD          the starting input
-> SIOPTICAL1   <- SIOPTICAL1    echo, 1.07 s later
-> SI?          <- SIOPTICAL1    readback after a 1.0 s settle
```

The display read `Optical` and the disc went silent, so the unit acted on the
command rather than merely echoing it. The reverse write (`SICD`) succeeded the
same way. **Open question 9 is answered.** Three details worth keeping:

- **A write echo is slow relative to a query.** 1.07 s against 23 ms for `SI?`.
  The unit acts before it answers, so a `listen` window sized for queries would
  time out on a write. `SOURCE_SETTLE_S = 1.0` is applied *after* that echo and
  is known sufficient, not known necessary — the same gap in the evidence that
  open question 10 records for `PWON`.
- **Switching inputs stops the disc, and switching back does not resume it.**
  The transport read `stop` on return, with the metadata degraded from
  `Track 5` to `Denon - CD`, the input's own name. Playback has to be started
  again at the unit; no `SI` write can do it.
- **An input carries its own name as `song` when nothing plays on it.**
  `Denon - CD` here, `Denon - AUX` on AUX. So a title equal to `Denon - …` means
  the input is idle, not that a track by that name exists.

**An `SI` write to a sleeping unit wakes it, and is not echoed.** Measured
2026-09-08, 07:45, unit in standby on `SICD` with no disc loaded:

```
-> PW?          <- PWSTANDBY
-> SI?          <- SICD
-> SIOPTICAL1   <- []            nothing at all, the full 1.5 s window waited out
-> SI?          <- SIOPTICAL1    1.0 s later
-> PW?          <- PWON          the write turned the unit on
```

**Open question 14 is answered**, and with the outcome that costs the most to
get wrong: selecting an input on a sleeping receiver powers it up. Three things
follow.

- **A write is not acknowledged in standby.** Awake, `SIOPTICAL1` echoes after
  1.07 s; asleep, nothing comes back at all. Any code that treats a missing echo
  as failure would report an error for a command that worked. `set_source()`
  survives this only because it ignores the echo and re-reads the input
  afterwards — worth keeping deliberate rather than incidental.
- **No `PWON` was sent.** The unit woke itself on the strength of an input
  command, which is a second, undocumented wake path alongside the one open
  question 4 established.
- **The AVR protocol answers quickly after this kind of wake.** The readback
  landed 1.0 s after the write, against the 4 s `WAKE_SETTLE_S` charged after an
  explicit `PWON`. Whether that generalises is unmeasured; one observation.

**The three remaining HEOS writes, measured 2026-09-08** — each exercised once,
read back and restored, in standby and again awake, with the unit on `SICD` and
no disc loaded:

| Command | In standby | Awake | Verdict |
|---|---|---|---|
| `player/set_mute?state=on` | readback `on` | readback `on` | works |
| `player/volume_up?step=1` | 0 → 1 | 15 → 16 | works |
| `player/volume_down?step=1` | 1 → 0 | 16 → 15 | works |
| `player/set_play_state?state=pause` | `success`, readback `stop` | `success`, readback `stop` | accepted, no effect |

- **Mute and the volume steps do not wake the unit.** `PW?` read `PWSTANDBY`
  after each. This is the opposite of an `SI` write, which does wake it, so
  "any write wakes the receiver" is not a rule that holds.
- **`result: success` is not evidence that anything changed.** `set_play_state`
  returned success and echoed `state=pause` in both phases while the readback
  stayed `stop` — there was nothing to pause. A caller that trusts the result
  field will report a working transport control that does nothing.
- **The standby volume level is a separate value from the awake one.** Standby
  read `0`, and the unit reported `15` immediately after `PWON` — the same 15 it
  held before sleeping, unaffected by the `0 → 1 → 0` stepping done while it
  slept. So a level read in standby predicts nothing about what will be heard on
  waking.
- **The unit puts itself back into standby when idle.** Woken at 07:50:05 and
  left alone after 07:50:20, it read `PWSTANDBY` at 07:55:50: at most 5.5
  minutes with nothing playing. The exact timeout is not measured — see open
  question 15 — but any state a UI has read can go stale on its own.

**`SINET` is not writable, while other `SI` tokens are.** Measured 2026-09-08
with the unit confirmed awake, one run isolating the token from everything else:

| Asked for | `set_source` returned | Re-read | Verdict |
|---|---|---|---|
| `cd` | `cd` | `cd` | switched |
| `net` | `cd` | `cd` | **ignored** |
| `aux` | `aux` | `aux` | switched |

`SINET` drew no echo — `[]` after the full listen window, the same silence a
standby write gives — and the input did not move across twelve seconds of
polling at two-second intervals. Two earlier attempts the same day, one from
standby, behaved identically. `SICD`, `SIANALOG1` and `SIOPTICAL1` all switch
within a second.

The likely reason, unproven: the network input is not a destination but a
*consequence*. The unit shows it when HEOS is playing something, which is also
why a DLNA server and a streaming service are indistinguishable by `SI` alone.
If that holds, the way to reach it is HEOS playback, not the AVR protocol — see
open question 17.

**`set_play_state` moves the state machine, but not the way it is documented.**
On the AUX input, playing, 2026-09-08 11:19:

```
state=play  -> set_play_state=pause  -> success, echoes state=pause
                                     -> readback state=stop     (not pause)
            -> set_play_state=play   -> success
                                     -> readback state=stop, then unknown
                                     -> state=play, 15 s after the command
```

So the command is *not* a no-op — this is the first evidence of that — but on a
passthrough input `pause` collapses to `stop`, and recovery to `play` takes
about fifteen seconds through the `unknown` state. Whether the audio itself was
interrupted is unknown: nobody was at the unit. On media HEOS actually
transports it remains untested, because every attempt to reach the network
input failed for the reason above. Open question 16 stays open.

**The reported volume level moved with no command touching it.** `level=30` at
11:18:36, `level=40` at 11:19:48 — 72 seconds apart, on the AUX input, with
nobody at the receiver and nothing in the log between the two but play-state
reads. Unexplained; see open question 18.

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
- HEOS port 1255 in standby was assumed open but degraded — errors or an empty
  player list. Measured 2026-09-07: it is neither. Every query answered normally,
  so this is no longer an assumption; see the confirmed section above.
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
| `heos://player/get_play_state` | TCP write | `pid` | `message: "pid=…&state=play\|pause\|stop\|unknown"`; `unknown` is measured on this unit at transitions and is not in the HEOS reference |
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