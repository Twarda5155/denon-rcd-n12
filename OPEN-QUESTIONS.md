# Open questions

Working register of what is not known. Numbering follows the list that used to
live in `docs/reference/web-interface.md`, so references to "open question 4"
elsewhere still resolve.

**Rule:** a question that gets answered leaves this file. Measured facts go to
`docs/reference/web-interface.md`; choices go to `docs/decisions/`. Closed
entries stay below only as one-line pointers.

---

## Nothing is open

As of 2026-09-12 this register is empty. Every question raised since 2026-08-30
has been answered by measurement, settled as a decision, or — once — closed as
not reproducible.

That is a statement about the questions asked, not about the device being
understood. New ones belong here the moment they are noticed.

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
- **Q18 — what moved the reported volume level with nothing sent?** Closed
  2026-09-12 as **an incident that could not be reproduced**, which is not the
  same as answered. The sighting was real: `level=30` at 11:18:36 on 2026-09-08
  and `level=40` at 11:19:48, with no volume command anywhere in the device log
  between them. Three things were then established and none of them explains it.
  A five-minute watch on the network input with playback stopped saw no drift.
  A 4.8-minute watch on AUX, reproducing the original conditions with the
  operator confirming they touched neither remote nor app, saw no drift. And
  `set_play_state`, the only command that *did* fall between the two readings,
  was tested directly over three pause/play cycles and moved the level not at
  all — so that correlation was a coincidence, and writing it up as a cause
  would have been a believable falsehood.
  What is certain is only that this project did not send it; the log is complete
  on that point. The most economical remaining explanation is another controller
  acting in that minute, which cannot be confirmed from here. Reopen it if the
  level is ever seen moving again — the instruments are in the scratchpad
  history and the conditions are written down.
- **Q15 — how long is the idle timeout before the unit sleeps?** Closed
  2026-09-12: between 4.2 and 5.3 minutes with nothing playing. Polling once a
  minute does not hold it awake, so reads neither prevent sleep nor risk
  causing it. Facts in `docs/reference/web-interface.md`.
- **Q11 — how does the page stay current: paced polling, or pushed events?**
  Closed 2026-09-12 as a decision, not a measurement: it pulls, user-driven, and
  `/api/events` will not be built. Q5 supplied the deciding fact — the AVR side
  pushes nothing, and HEOS events need a held socket this transport does not
  keep. Reasoning in `docs/decisions/2026-09-12-staying-current.md`.
- **Q13 — can the metadata lag make `get_source()` report `server` for a
  stream?** Closed 2026-09-12: not on any path this project can drive. Three
  forced CD-to-stream transitions never produced it, and Q17 says why — the
  network input is reached only through HEOS playback, so the metadata moves
  first and `SI` follows. The lag is real but points the safe way here.
- **Q8 — what is the mapping between HEOS `level` and AVR `MV`?** Closed
  2026-09-12: they are the same number, measured at ten points from 0 to 75.
  No conversion needed; the 2026-08-30 warning against mixing the scales is
  retired, by measurement rather than by resemblance.
- **Q10 — what is the *minimum* settle time after `PWON`?** Closed 2026-09-12:
  under 0.5 s. Three cold starts all confirmed `PWON` at the first poll, which
  is the transport's own pacing floor. `WAKE_SETTLE_S` dropped from 4.0 to 1.0,
  double the measured bound, since answering `PW?` is not proof that every
  capability is ready.
- **Q5 — does the `PW` heartbeat appear on a passive port-23 connection?**
  Closed 2026-09-12: no. Seventy-five seconds of an idle held socket produced
  zero frames, refuting the third party claim of a report every 10 s. Power
  changes made at the unit can only be learned by polling; any push must come
  from HEOS.
- **Q3 — is `SLP` accepted, and in which digit format?** Closed 2026-09-12:
  three zero-padded digits, range 001-090, `SLPOFF` to cancel, `SLP?` to read.
  Two digits are ignored and anything above 090 is refused silently. The sleep
  timer needs no server-side fallback, and the 2026-08-30 record's consequence
  about a timer dying with the process no longer applies.
- **Q1 — which ports are open, powered on *and* in standby?** Closed
  2026-09-12: 23, 80, 443 and 1255 answer in both states; 8080 and 10443 refuse
  in both. Nothing this project relies on disappears while the unit sleeps.
  `tools/probe_ports.py` runs the scan.
- **Q6 — does the HTTP `goform` endpoint exist, and on which port?** Closed
  2026-09-12: the web server exists, redirects HTTP to 443 rather than to
  10443, and answers 403 Forbidden to every path including the root. Not usable
  as a fallback. Facts in `docs/reference/web-interface.md`.
- **Q19 — does `set_play_state=pause` pause a CD, or stop it too?** Closed
  2026-09-11: a disc pauses properly — `state=pause` held across four polls with
  the track kept — and resumes. With Q16 that gives the rule: the command is
  always honoured and the medium decides what pause means. `pause` is honest for
  a disc, misleading for a stream.
- **Q16 — does `player/set_play_state` actually control playback?** Closed
  2026-09-11: it does. On a favourite playing over the network input it moved
  the stream and moved it back, so the earlier "success and nothing happened"
  results were all cases with nothing to act on. But `pause` collapses to
  `stop` on a stream, so only `play` and `stop` are verbs this unit honours
  there. The disc case became Q19.
- **Q17 — how is the network input selected, if not with `SI`?** Closed
  2026-09-11: by starting something on it over HEOS. `browse/play_preset` from
  a standing start on CD moved the input to `net` within two seconds and played
  the favourite. The input follows the playback; `SI` never selects it. Facts in
  `docs/reference/web-interface.md`.
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
