# Open questions

Working register of what is not known. Numbering follows the list that used to
live in `docs/reference/web-interface.md`, so references to "open question 4"
elsewhere still resolve.

**Rule:** a question that gets answered leaves this file. Measured facts go to
`docs/reference/web-interface.md`; choices go to `docs/decisions/`. Closed
entries stay below only as one-line pointers.

---

## Q1 — Which ports are open, powered on *and* in standby?

- **Why it matters:** the standby answer decides which control paths the page
  can rely on while the unit sleeps, and therefore whether "wake" is a normal
  action or a special case in the UI.
- **How to settle:** scan 23, 80, 8080, 1255, 10443 twice — once powered on,
  once in standby. `tools/probe_device.py` covers the powered-on half.
- **Status:** open. Not blocking; power control works from the AVR side today.

## Q3 — Is `SLP` accepted, and in which digit format?

- **Why it matters:** it is the difference between a real sleep timer and a
  server-side fallback timer whose state dies with the process — a consequence
  already written into the 2026-08-30 decision record.
- **How to settle:** send `SLP?`, then `SLP060`, then `SLPOFF` on port 23 and
  read the echoes. Syntax is carried over from the sibling DRA-N4 and unverified
  here.
- **Status:** open, blocks the sleep timer.

## Q5 — Does the `PW` heartbeat appear on a passive port-23 connection?

- **Why it matters:** if it does, the page could learn about power changes made
  at the front panel without polling. If not, every status read costs a paced
  transaction.
- **How to settle:** hold a port-23 socket open for a minute, log every frame.
  Note that holding the socket blocks all other consumers, so this is a
  deliberate one-off measurement, not a design the server can adopt casually.
- **Status:** open.

## Q6 — Does the HTTP `goform` endpoint exist on this firmware, and on which port?

- **Why it matters:** only as a fallback if telnet or HEOS turn out unreliable.
  Some 2023-era Denons redirect to `https://<ip>:10443` and refuse plain HTTP.
- **How to settle:** `GET /goform/formMainZone_MainZoneXmlStatusLite.xml` on 80,
  then 8080.
- **Status:** open, deliberately deferred — see STATUS.md.

## Q8 — What is the mapping between HEOS `level` (0–100) and AVR `MV` (two digits)?

- **Why it matters:** without it a single slider cannot drive both protocols
  coherently. The 2026-08-30 decision record already forbids silently converting
  one into the other, so today the page is honest but partial.
- **How to settle:** set volume over HEOS at 10, 25, 50, 75 and read `MV?` after
  each, with the unit powered on and unmuted. Watch for a Volume Limit clamp set
  in the device menu.
- **Status:** open. Not blocking while the UI exposes only the HEOS scale.

## Q10 — What is the *minimum* settle time after `PWON`?

- **Why it matters:** `WAKE_SETTLE_S = 4.0` is known sufficient, not known
  necessary. It is charged to every wake the page performs.
- **How to settle:** after `PWON`, poll `PW?` at 0.5 s intervals and record the
  first success; repeat a few times from cold standby.
- **Status:** open, low value — 4 s is tolerable.

## Q11 — How does the page stay current: paced polling, or pushed events?

- **Why it matters:** this is a design choice, not a measurement, and it decides
  whether `/api/events` (SSE, in the 2026-08-30 record) is ever built. HEOS
  `register_for_change_events` pushes on a held socket, which the transport
  already maintains; the AVR side has no equivalent unless Q5 says otherwise.
- **How to settle:** decide once the source control lands and the page's real
  read pattern is visible. Outcome belongs in `docs/decisions/`.
- **Status:** open.

## Q13 — Can the metadata lag make `get_source()` report `server` for a stream?

- **Why it matters:** `get_source()` calls `SINET` a DLNA server when
  `get_now_playing_media` reports `sid` 1024. The 2026-09-07 sweep showed the
  metadata trailing an input change by about one poll — `SIANALOG1` was read
  while the payload still held the CD's `sid` 1024 — and the CD transport uses
  that same 1024. So a read taken a second after switching from CD to a
  streaming service could satisfy both halves of the test and name the input
  `server` when TuneIn is on it. Never observed; derived from two measurements
  that were each observed.
- **How to settle:** switch from CD straight to TuneIn and read `get_source()`
  immediately, repeatedly. If it misreports, the fix is either a settle delay in
  `get_source()` or a second read for confirmation — a choice for
  `docs/decisions/`, since both cost a device transaction.
- **Status:** open. Affects one label on one input; nothing else depends on it.

## Q15 — How long is the idle timeout before the unit puts itself in standby?

- **Why it matters:** every readout the page shows can go stale without anyone
  touching anything. It bounds how long a "check power" answer stays true, and
  it is the strongest argument for a single `/api/status` read over four
  separate ones taken minutes apart.
- **How to settle:** wake the unit, leave it alone on an input with nothing
  playing, and poll `PW?` at a one-minute cadence until it reports standby.
  Repeat with something playing to see whether playback holds it awake.
- **Status:** open. Bounded so far at 5.5 minutes or less, from a single
  unpolled gap on 2026-09-08.

## Q17 — How is the network input selected, if not with `SI`?

- **Why it matters:** it is the only input the page cannot offer. `SINET` is
  ignored (measured 2026-09-08), so TuneIn and the DLNA server are reachable
  from the remote and the HEOS app but not from this project. It also blocks
  Q16, because HEOS-transported media is the only place a pause has a defined
  meaning.
- **How to settle:** try HEOS playback as the selector rather than the AVR
  protocol — `browse/play_stream` on a favourite, or `browse/play_input`, whose
  syntax is documented but unverified here. Watch `SI?` afterwards to see
  whether the input follows the playback.
- **Status:** open. Blocks Q16 and the network entry in the source picker.

## Q18 — What moved the reported volume level with nothing sent?

- **Why it matters:** if the level can change on its own, the page's volume
  readout decays like the power one, and a step control could be fighting
  something invisible. It may also be benign — a ramp after an input change, or
  simply another person with the remote.
- **How to settle:** poll `player/get_volume` once a minute for a quarter of an
  hour with nobody near the receiver, on a stable input, and see whether it
  moves. Repeat on AUX, where it was seen, and on a network input.
- **Status:** open. One observation: 30 to 40 in 72 seconds on 2026-09-08, and
  0/muted to 25/unmuted across a later run whose power state was not read.

## Q16 — Does `player/set_play_state` actually control playback?

- **Why it matters:** it is the last capability standing between the page and a
  play/pause control. The command is *accepted* — `result: success`, the state
  echoed back — in standby and awake alike, while the readback stays `stop`.
  That is consistent with two very different worlds: it works and there was
  simply nothing to pause, or it is a no-op on this model.
- **How to settle:** start playback at the unit (a disc, or a station), confirm
  `get_play_state` reads `play`, then send `set_play_state?state=pause` and read
  it again. It needs media the unit itself transports.
- **Status:** open, blocks the transport control on the page. Partly advanced
  2026-09-08: on the AUX *passthrough* input, playing, `pause` did move the
  state — to `stop`, not `pause` — so the command is not a no-op. That is not
  the answer, because AUX is not media HEOS transports and nobody was at the
  unit to say whether the sound stopped. Reaching real HEOS media is blocked on
  Q17.

---

## Closed

- **Q2 — full `SI?` token set.** Closed 2026-09-06: all seven inputs measured,
  `SINET` shared by TuneIn and a DLNA server. Facts in
  `docs/reference/web-interface.md`; naming choice in
  `docs/decisions/2026-09-06-source-naming.md`. The *write* half became Q9.
- **Q4 — does `PWON` wake the unit over the network?** Closed 2026-09-06: it
  does, with a 4 s settle. The minimum settle time became Q10.
- **Q7 — how does HEOS 1255 behave in standby?** Closed 2026-09-07: it behaves
  normally. Full player list, and volume, mute, play state and now-playing all
  answer as they do when the unit is awake — so nothing on the page has to be
  greyed out for standby. Facts in `docs/reference/web-interface.md`. The
  measurement raised Q12 instead, about the metadata being stale rather than
  absent.
- **Q9 — does writing `SI<TOKEN>` actually switch the input?** Closed
  2026-09-07: it does. `SIOPTICAL1` sent with a CD playing moved the unit to
  Optical — confirmed at the front panel and by the disc going silent, not by
  the echo alone — and `SICD` moved it back. The last unverified write path in
  the client is now verified. Facts in `docs/reference/web-interface.md`; the
  naming record `docs/decisions/2026-09-06-source-naming.md` no longer says
  "writes not".
- **Q14 — does an `SI` write work while the unit is in standby?** Closed
  2026-09-08: it works *and wakes the unit*, without a `PWON` and without
  echoing anything back. Selecting an input therefore powers the receiver on,
  which the page states in the control's hint and reflects by dimming the power
  row after a source write. Facts in `docs/reference/web-interface.md`.
- **Q12 — on the non-network inputs, is the now-playing metadata empty or
  stale?** Closed 2026-09-07: neither. HEOS reports live metadata for every
  input, each with its own `sid` and title — the CD's track, the AUX input's own
  name — so the page's track readout is honest everywhere, not just on the
  network inputs. The sweep also turned up an undocumented fourth transport
  state (`unknown`) and confirmed `pause` exists on this unit. Facts in
  `docs/reference/web-interface.md`. The one-poll lag it exposed became Q13.
