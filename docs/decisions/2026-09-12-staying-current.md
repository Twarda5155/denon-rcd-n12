# Staying current: pull, not push

Status: accepted 2026-09-12. Closes open question 11.

## Context

The page shows five readouts — power, volume, source, transport state, track —
and each one can go out of date without anyone touching the page. The question
has been open since the API had two routes: does the page ask, or is it told?

Four measurements settled what is actually possible.

- **The AVR protocol tells nothing.** A socket held open on port 23 for 75 s
  received zero frames (open question 5, 2026-09-12). Third party notes
  described a `PW` report every 10 s; this unit sends none. Power, and anything
  else that lives on port 23, can only be asked for.
- **HEOS can tell, but only down a socket somebody holds.**
  `system/register_for_change_events?enable=on` succeeds, and pushes on that
  connection. `transport.py` opens a fresh connection per command on both ports,
  so nothing is holding one, and events sent to a closed socket reach nobody.
- **The receiver puts itself to sleep after about five minutes idle**, measured
  the same day, so even a perfectly fresh reading decays on its own — and a poll
  once a minute does not hold it awake, so watching it is not a way to keep it
  up either.
- **Every read costs a paced device transaction.** The transport enforces a
  0.5 s floor between transactions device-wide, deliberately: Denon units are
  reported to soft-lock when commanded rapidly. Freshness is not free here the
  way it is against a web API.

## Decision

The page pulls. It does not subscribe, and no `/api/events` will be built.

Reads stay user-driven rather than periodic: a page nobody is looking at
generates no traffic to the receiver. The four separate reads the page performs
today collapse into one `/api/status`, so that drawing the whole picture is one
gesture rather than four.

`transport.py` keeps connecting per command. Holding a HEOS socket to receive
change events would be a real re-architecture — the pacing lock, the retry
policy and the single-owner story all assume short-lived connections — bought
for freshness nobody has asked for on a single-user tool running on the same
desk as the receiver.

## Consequences

- **Staleness is visible rather than prevented.** The page already dims a value
  it cannot vouch for: the track when the transport is not playing, the power
  row after an input write. That pattern is now the strategy, not a detail.
- **`/api/status` costs about seven device transactions**, since power and
  source come from the AVR side and volume, mute and playback each cost a HEOS
  query or two. At the 0.5 s floor that is several seconds. It is one wait
  instead of four, but it is not instant, and the page must say so rather than
  appear hung.
- **Front-panel changes are invisible until asked about.** Someone pressing a
  button on the receiver changes state the page will not notice. This is
  accepted; the alternative was polling in a loop, which is the one behaviour
  the protocol reference explicitly warns against.
- **Reversible.** If a future need justifies push, the pieces exist: HEOS events
  are documented and register cleanly. What changes is the transport's
  connection lifetime, not the API the page speaks.
