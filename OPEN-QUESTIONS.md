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

## Q7 — How does HEOS 1255 behave in standby?

- **Why it matters:** determines whether the page can show volume and now-playing
  while the unit sleeps, or has to grey them out. Connection refused, an empty
  player list and an error reply each imply different UI handling.
- **How to settle:** connect and issue `player/get_players` with the unit in
  standby.
- **Status:** open.

## Q8 — What is the mapping between HEOS `level` (0–100) and AVR `MV` (two digits)?

- **Why it matters:** without it a single slider cannot drive both protocols
  coherently. The 2026-08-30 decision record already forbids silently converting
  one into the other, so today the page is honest but partial.
- **How to settle:** set volume over HEOS at 10, 25, 50, 75 and read `MV?` after
  each, with the unit powered on and unmuted. Watch for a Volume Limit clamp set
  in the device menu.
- **Status:** open. Not blocking while the UI exposes only the HEOS scale.

## Q9 — Does writing `SI<TOKEN>` actually switch the input?

- **Why it matters:** reading sources is measured and shipped; writing is
  implemented but has never touched the hardware. This is the last unverified
  write path in the client.
- **How to settle:** `denon source cd` with the unit powered on, then confirm at
  the front panel. Start on a harmless input, not Phono.
- **Status:** open, blocks the source control on the page (it can ship read-only
  first).

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

---

## Closed

- **Q2 — full `SI?` token set.** Closed 2026-09-06: all seven inputs measured,
  `SINET` shared by TuneIn and a DLNA server. Facts in
  `docs/reference/web-interface.md`; naming choice in
  `docs/decisions/2026-09-06-source-naming.md`. The *write* half became Q9.
- **Q4 — does `PWON` wake the unit over the network?** Closed 2026-09-06: it
  does, with a 4 s settle. The minimum settle time became Q10.
