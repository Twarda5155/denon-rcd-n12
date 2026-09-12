---
source: HEOS CLI session against the local unit, Denon RCD-N12 web manual, third-party reverse engineering
date: 2026-08-30
status: partial
verified_against: live device throughout. HEOS CLI 1255 on 2026-08-30, 09-07 (in standby), 09-08, 09-11 and 09-12; AVR telnet 23 on 2026-09-06 to 09-08 and 09-12; HTTP 80/443 and a port scan on 2026-09-12
untested: nothing outstanding in the command set; see OPEN-QUESTIONS.md for what is still unknown about behaviour
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

**A slow HEOS command is answered twice, and the first answer is a lie.**
Measured 2026-09-11 on `browse/browse?sid=1028`:

```
<- {"heos":{…,"result":"success","message":"command under process&sid=1028"},"payload":[]}
<- {"heos":{…,"result":"success","message":"sid=1028&returned=2&count=2"},"payload":[ … ]}
```

The acknowledgement carries `result: success` and an **empty payload**, so a
reader that returns the first matching reply reports an empty source rather
than an error — the failure mode that hides. `transport.py` now reads past any
message containing `command under process` and waits for the one behind it.
This is why the 2026-09-06 note about `browse?sid=1027` should be treated with
suspicion: that reading was taken with the old behaviour.

**Favorites listing works**, `browse/browse?sid=1028`, measured the same day:

| `name` | `mid` | `type` | `playable` | `container` |
|---|---|---|---|---|
| 1.FM Gaia | `s214674` | `station` | `yes` | `no` |
| Klassik Radio | `s25028` | `station` | `yes` | `no` |

The reply also carries `options: [{"browse": [{"id": 20, "name": "Remove from
HEOS Favorites"}]}]`. The `mid` values are TuneIn station ids — `s25028` is the
same one that appeared as `album_id` in the Klassik Radio now-playing payload on
2026-09-07, which ties a favourite to what the unit reports while playing it.
Whether a `mid` can be *started* is untested; that is open question 17.

**`browse/play_preset` starts a favourite.** Measured 2026-09-11 with the unit
awake, on the network input, 1.FM Gaia playing at level 10:

```
-> browse/play_preset?pid=…&preset=2   <- success, message "pid=…&preset=2"
   +2 s  station='Klassik Radio'  mid='https://stream.klassikradio.de/national/aac-128/tunein'
-> browse/play_preset?pid=…&preset=1   <- success
   +2 s  state=unknown, station='1.FM Gaia'
   +4 s  state=play,    song='Aurora'
```

`preset` is HEOS's own 1-based numbering over the favourites list, so it lines
up with the order `browse/browse?sid=1028` returns. Three things follow.

- **The readback trails the command by about a second.** Reading playback
  straight after the write names the *previous* station — measured through the
  HTTP API before a settle was added, where asking for preset 2 answered
  "1.FM Gaia" and asking for 1 answered "Klassik Radio". `FAVORITE_SETTLE_S`
  is 2.0 s for that reason and was sufficient every time.
- **The title lags further than the station.** For a second or two `song`
  carries the stream's bitrate — `128 kbps aac`, `192 kbps mp3` — before the
  track on air arrives. This retires the earlier puzzle over a stopped TuneIn
  stream reporting `192 kbps mp3`: that is what this field says when the unit
  has no track to name, not junk.
- **`state` passes through `unknown`** on the way, as it does at every other
  transition.

**And it selects the network input.** Measured 2026-09-11 from a standing
start on another input:

```
source=cd, state=stop        -> browse/play_preset?preset=1
+2 s  source=net, state=play, sid=3, station='1.FM Gaia'
```

**Open question 17 is answered.** The network input is reachable after all —
not over the AVR protocol, which ignores `SINET`, but by starting something on
it over HEOS. The input follows the playback rather than the other way round,
which is the same relationship that makes `SINET` ambiguous between a streaming
service and a DLNA server: it is a report of what HEOS is doing, not a
destination.

**`player/set_play_state` works, and `pause` is not a pause.** Measured
2026-09-11 against a favourite playing on the network input — the first stand
this test ever had, earlier attempts having had nothing to pause:

```
state=play, song='Duduk Dreams'
-> set_play_state=pause   <- success, echoes state=pause
   +1.5 s through +6 s    state=stop, song='192 kbps mp3'   (stable, four polls)
-> set_play_state=play    <- success
   +4 s                   state=play, song='Duduk Dreams'
```

**Open question 16 is answered**, in two parts that matter separately.

- **The command is not a no-op.** It moved a live stream and moved it back. The
  three earlier runs that showed "success and nothing happened" were all cases
  with nothing to act on — standby, an idle CD input, and an AUX passthrough.
- **`pause` stops rather than pauses, on a stream.** The state settles on `stop`
  and the title falls back to the bitrate, meaning the unit no longer knows what
  is on air — the stream is torn down, not held. This is the same collapse seen
  on AUX on 2026-09-08, now confirmed on media the unit does transport. A UI
  offering "pause" for a stream would be naming something the device does not
  do; `play` and `stop` are the two verbs it honours here.

**A disc pauses properly.** Measured 2026-09-11, minutes later, on the same
unit with a disc loaded:

```
state=play, song='Track 1', mid='cd/cdda'
-> set_play_state=pause   +1.5 s through +6 s   state=pause   (stable, four polls)
                                                song='Track 1' kept
-> set_play_state=play    +2 s                  state=play
```

**Open question 19 is answered**, and together with the stream result it gives
the rule: **the command is always honoured, and the medium decides what pause
means.** A live stream cannot be held, so the receiver stops it and forgets the
track; a disc is held in place with its track intact. Neither is the unit
ignoring the command.

For a UI this means `play` and `stop` are safe words everywhere, while `pause`
is honest for a disc and misleading for a stream — where pressing it yields
`stop`.

**`cd/nodisc` means the drive has not read the disc, not that the tray is
empty.** Both readings of it in the whole device log — 2026-09-08 07:41:07 and
07:41:07.7 — came one second after `PW?` answered `PWSTANDBY`, with `SI?` on
`SICD`. Every one of the 37 `cd/cdda` readings came from an awake unit. The disc
was in the tray throughout: it was found there on 2026-09-11, having been put in
before any of these measurements.

So on a sleeping unit the CD input reports `mid: "cd/nodisc"` and `song: "CD"`
because the transport is not spinning, and the same disc reports `cd/cdda` with
a track name as soon as the unit is awake. A UI must not read `nodisc` as "no
disc" — it means "ask again when the unit is on".

Closing the tray on a loaded disc **starts playback by itself**, observed
2026-09-11.

**Port scan, 2026-09-12, `tools/probe_ports.py`, run in both power states:**

| Port | In standby | Powered on |
|---|---|---|
| 23 (AVR) | open | open |
| 80 (HTTP) | open | open |
| 443 (HTTPS) | open | open |
| 1255 (HEOS) | open | open |
| 8080 | refused | refused |
| 10443 | refused | refused |

**Open question 1 is answered:** the same four ports answer in both states.
Nothing this project depends on goes away while the unit sleeps, which is the
half that mattered — it is consistent with HEOS and the AVR protocol both
having been measured answering in standby.

A note on the instrument: the first runs reported 8080 and 10443 as *timeouts*,
which would have meant "filtered". They are not — a refusal takes 2.2-2.5 s to
come back over wifi on this network, and the tool's 2 s timeout expired first.
It is 6 s now. Two opposite conclusions from the same wire, decided by a
constant.

**The HTTP interface exists and refuses everything.** Measured 2026-09-12:

```
http://<ip>/goform/formMainZone_MainZoneXmlStatusLite.xml  -> 301 https://<ip>/…
https://<ip>/goform/formMainZone_MainZoneXmlStatusLite.xml -> 403 Forbidden
https://<ip>/goform/formiPhoneAppDirect.xml?PW%3F          -> 403 Forbidden
http(s)://<ip>/                                            -> 403 Forbidden
```

**Open question 6 is answered:** `goform` is not a fallback on this firmware.
Port 80 redirects to **443**, not to the 10443 the third-party notes suggested,
and 443 then denies every path tried — the two documented `goform` endpoints,
the root, and `/NetAudio/index.html` — with a browser user agent as well as
without. The certificate does not chain to anything, as expected for a device.

**`SLP` works, in three digits, up to 90 minutes.** Measured 2026-09-12 on a
powered-on unit; a sleep timer makes no sound either way:

```
SLP?      -> SLPOFF          the query works, and OFF is a real answer
SLP060    -> SLP060          three digits accepted, readback agrees
SLP30     -> []              two digits ignored outright, timer unchanged
SLP001    -> SLP001          the floor
SLP090    -> SLP090          the ceiling
SLP091    -> []              refused, and so are 095, 100, 110, 119, 120, 999
SLPOFF    -> SLPOFF          cancels
```

**Open question 3 is answered**, and the sleep timer needs no server-side
fallback. Two details worth carrying:

- **The range is 001-090, not the 001-120 documented for the DRA-N4.** The
  syntax carried over from the sibling model; the range did not. A UI offering
  two hours would be offering something this unit refuses.
- **A refused `SLP` is silent.** No echo, no error — the timer simply stays
  where it was, which is why every probe here reads it back rather than
  trusting the write. This is the same silent-refusal shape as `SINET`.

Worth noting against the `SI` experience: this is the first carried-over guess
from another Denon model that turned out **right**. Every input token guessed
that way was wrong. The lesson is not "never carry over" but "carry over, then
measure" — the syntax held and the bounds did not.

**There is no `PW` heartbeat on this unit.** Measured 2026-09-12: one socket
held open on port 23 for 75 s, nothing written, **zero frames received**.

**Open question 5 is answered, against the documentation.** The third party note
below — an unsolicited `PW` report roughly every 10 s — does not hold here, and
it never had support from this project's own measurements either: the 2026-09-06
sweep explicitly recorded a bare `SI?` reply with no `PW` interleaved. Two
consequences.

- **Front-panel changes can only be learned by polling**, on the AVR side. The
  page cannot be told that someone pressed a button on the unit; it has to ask.
  Whatever push exists must come from HEOS `register_for_change_events`, which
  is a different socket and covers playback and volume, not power.
- **The frame-filtering in the client stays anyway.** It costs nothing, and
  taking the last matching frame rather than the first is correct whether or not
  anything interleaves. What changed is the justification: it guards a
  documented possibility, not an observed behaviour.

**HEOS `level` and AVR `MV` are the same number.** Measured 2026-09-12 with the
unit awake and nothing playing, so every step was silent:

| HEOS `level` | `MV?` |
|---|---|
| 0 | `MV00` |
| 1 | `MV01` |
| 2 | `MV02` |
| 3 | `MV03` |
| 5 | `MV05` |
| 8 | `MV08` |
| 10 | `MV10` |
| 25 | `MV25` |
| 50 | `MV50` |
| 75 | `MV75` |

**Open question 8 is answered:** identity, across everything tested (0-75). No
conversion is needed and none should be invented. One earlier row read
`level 0 → MV02` and was a stale read taken too soon after waking, not a floor;
repeated cleanly it is `MV00`. No Volume Limit clamp appeared anywhere in the
range.

This retires the 2026-08-30 warning against mixing the two scales in one
control. The warning was right to exist -- they *could* have differed, and
guessing would have been a real error -- but on this unit the answer is that
they do not.

**`PWON` is confirmed in under half a second.** Measured 2026-09-12, three cold
starts from standby, `PW?` polled as fast as the transport's 0.5 s pacing
allows:

```
cycle 1   +0.53 s  PWON
cycle 2   +0.52 s  PWON
cycle 3   +0.52 s  PWON
```

**Open question 10 is answered:** the first poll always succeeded, so the real
figure is below the 0.5 s floor this project can measure at. `WAKE_SETTLE_S`
was 4.0 s, carried over from a third party estimate of 2-5 s; it is now 1.0 s,
double the measured bound. Note the measurement is of the AVR protocol
answering, which is not proof that every capability is ready at that moment.

**The metadata lag points the safe way on the one path that mattered.**
Measured 2026-09-12, three cycles of parking on CD and then starting a favourite
while `get_source()` was read as fast as the pacing allows:

```
cycle 2   sid while parked on cd: 1024
          +1.06 s  source=cd    sid=3      <- metadata already moved, SI has not
          +2.66 s  source=net   sid=3
```

**Open question 13 is answered: it cannot happen on any path this project can
drive.** The feared race needed `SI` to read `SINET` while the payload still
held the CD's `sid` 1024. It never appeared, and open question 17 explains why:
the only way into the network input is HEOS playback, so HEOS moves *first* and
`SI` follows. The metadata leads on this transition rather than trailing.

The lag itself is real and was seen again here in the harmless direction —
parked on CD, the payload still named the previous stream's `sid` 3. It trails
on an `SI`-driven change, which is the 2026-09-07 observation, and leads on a
playback-driven one.

Residual, never observed: someone selecting the network input at the front panel
or from the HEOS app might order the two differently. Nothing this project sends
can.

**The unit puts itself to sleep after about five minutes idle, and polling does
not stop it.** Measured 2026-09-12: woken, playback stopped, then read once a
minute and otherwise left alone.

```
07:44  +0.0m  power=on       level=2
07:48  +4.2m  power=on       level=2
07:49  +5.3m  power=standby  level=0
```

**Open question 15 is answered:** between 4.2 and 5.3 minutes, consistent with
the 5.5 minute bound inferred from an unpolled gap on 2026-09-08. Two things
follow.

- **Reads do not reset the idle timer.** The confound this measurement was
  designed around turned out not to exist: a poll every minute did not hold the
  unit awake. A UI cannot keep the receiver up by watching it, and equally does
  not have to worry about doing so by accident.
- **Any reading older than about five minutes is probably wrong about power.**
  This is the concrete number behind the decision to collapse the page's four
  reads into one, and behind dimming rather than trusting what is on screen.

The level reading moved in the same run — 2 while awake, 0 once asleep — which
is the standby artefact already recorded above, not a drift. Open question 18,
about a level that moved *while awake*, is untouched by this: nothing changed
across five minutes of idling.

**The idle timeout does not care which input is selected, and `state=play` on
AUX does not count as activity.** Measured 2026-09-12, AUX selected, operator
confirming they touched neither remote nor app:

```
08:02  +4.3m  power=on       level=2   state=play
08:03  +4.8m  power=standby  level=0   state=stop
```

Four point eight minutes, against 4.2-5.3 on the network input with playback
stopped. So the five-minute timeout measured for open question 15 is general,
and the `play` that AUX reports for as long as it is selected is not playback
the receiver counts — consistent with it describing the input rather than any
sound. Whether media the unit actually transports holds it awake is still
untested.

**The volume level did not drift.** Ten polls over those 4.8 minutes, nothing
written after the input was set: the level held at 2 throughout. The only
movement was 2 to 0 at the moment of falling asleep, which is the standby
artefact recorded above. The mute flag read `on` in that standby sample and
`off` in others, so it is no more meaningful there than the level is.

**`SLP` is refused while the unit sleeps.** Measured 2026-09-12, found by
building the control rather than by looking for it:

```
power=standby   -> SLP015   <- []          SLP? -> SLPOFF
power=on        -> SLP015   <- SLP015      SLP? -> SLP015
```

The refusal is the same silence as an out-of-range value and as `SINET`: no
echo, the old setting kept. It makes sense for the feature — a sleep timer on a
sleeping unit has nothing to do — but it means a client cannot treat "the
command was sent" as "the timer is armed". `set_sleep` therefore compares the
readback against what was asked for and raises on a mismatch, naming standby as
the cause. Reporting the timer the receiver kept would be a control that
appears to work, which is the failure this project keeps finding.

**One `/api/status` read takes 3.7-3.9 s**, measured over the HTTP API on
2026-09-12 with eight paced transactions behind it. That is the price the
2026-09-12 decision record accepted for drawing the whole page in one gesture.

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
- The unit was reported to emit an unsolicited `PW` status report approximately
  every 10 seconds on an open port-23 connection. **Refuted on this unit**,
  2026-09-12: 75 s of an idle held socket produced nothing. See the confirmed
  section.
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

- `SLP` sleep-timer syntax was assumed to carry over from the DRA-N4. Measured
  2026-09-12: the syntax does, the range does not (001-090 here, not 001-120).
  No longer an assumption — see the confirmed section.
- `SI?` returns this unit's current input-source token. The full token set for this
  unit was measured 2026-09-06 and now lives in the confirmed section above, so this
  is no longer an assumption.
- The HTTP `goform` endpoint was assumed to maybe exist. Measured 2026-09-12: the
  web server is there, redirects plain HTTP to 443, and answers 403 to every
  path. Not an assumption any more — see the confirmed section.
- HEOS `browse` with `sid=1027` was assumed to enumerate physical inputs. Measured
  2026-09-06: it does not — it returns one entry pointing back at this player (see
  above). `browse/play_input` for selecting an input remains unverified.
- The unit was assumed to need 2-5 s after `PWON` before accepting further
  commands. Measured 2026-09-12: `PW?` answers in under 0.5 s. See above.
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
| `heos://browse/browse` | TCP write | `sid` | `payload`: array of entries; answered in two messages, see the confirmed section. Measured for `sid` 1028 (favorites) and 1027 |
| `heos://browse/play_input` | TCP write | `pid`, `input=inputs/…` | echo — **assumed** |
| `heos://browse/play_preset` | TCP write | `pid`, `preset=1-…` | echo; **measured**, starts the favourite at that position |

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
| `SLP?` | TCP write | — | `SLP<nnn>` or `SLPOFF` — **measured** |
| `SLP<nnn>` | TCP write | 001–090 minutes, three digits | echo, or nothing at all if refused — **measured** |
| `SLPOFF` | TCP write | — | echo — **measured** |
| *(none)* | passive read | — | nothing; **measured**, this unit volunteers no status |

`MV` here is the AVR-protocol volume scale. Measured 2026-09-12 it carries the
**same number** as the HEOS `level`, so the two can be mixed after all — but the
measurement is what licenses that, not the resemblance.

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
| Opening and closing a HEOS socket per command **under rapid polling** | Reported to exhaust the connection ceiling. Qualified 2026-09-12: this project has connected per command on 1255 since the start and has exhausted nothing, because every transaction is paced 0.5 s apart and nothing polls in a loop. The warning stands for a design that polls hard; it is not an argument against connecting per command as such. |
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