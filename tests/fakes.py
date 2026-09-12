"""Test doubles. No test in this suite opens a socket or needs the receiver.

One fake per real transport, each replaying the recorded exchanges in
``tests/fixtures/`` rather than inventing wire formats of its own, and each
implementing the matching protocol from :mod:`denon_rcd_n12.transport`.
``test_transport.py`` asserts every fake and its real counterpart stay in step.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from denon_rcd_n12.transport import DeviceError

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Read one fixture file.

    Args:
        name: File name inside ``tests/fixtures``.

    Returns:
        The decoded fixture, with the ``_comment`` key removed.
    """
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    data.pop("_comment", None)
    return data


class FakeTelnetTransport:
    """Replays fixture AVR traffic in place of a real receiver.

    Holds mutable power and source states so writes are observable, records
    every command for assertions, and can prepend a stale ``PW`` frame so the
    filtering in :mod:`denon_rcd_n12.client` is exercised. That interleaving is
    described by third party notes and has never been seen on this unit --
    measured 2026-09-12, it volunteers nothing on an idle socket -- so this
    reproduces a documented shape rather than an observed one.
    """

    def __init__(
        self,
        power: str = "on",
        source: str = "SINET",
        heartbeat: bool = False,
        fail: bool = False,
        host: str = "10.0.0.1",
        sleep: int = 0,
    ) -> None:
        """Configure the fake AVR endpoint.

        Args:
            power: Initial power state, ``"on"`` or ``"standby"``.
            source: Initial ``SI`` token, one of the fixture's recorded tokens.
            heartbeat: Prepend a stale opposite-state ``PW`` frame to replies.
            fail: Raise :class:`DeviceError` on every call.
            host: Address reported by the transport.
            sleep: Initial sleep timer in minutes; 0 is off.
        """
        self.host = host
        self.power = power
        self.heartbeat = heartbeat
        self.fail = fail
        self.sleep = sleep
        self.commands: list[str] = []
        self._fixture = load_fixture("avr.json")
        self.sources: list[str] = self._fixture["sources"]
        if source not in self.sources:
            raise ValueError(f"no recorded SI token {source!r}")
        self.source = source

    def send(self, command: str, expect: str | None = None, listen: float = 2.5) -> list[str]:
        """Record an AVR command, apply it, and replay the recorded frames.

        Args:
            command: The command token sent.
            expect: Ignored; present to match the real signature.
            listen: Ignored; present to match the real signature.

        Returns:
            The frames the fake receiver emits.

        Raises:
            DeviceError: If the fake is failing, or the command has no fixture.
        """
        if self.fail:
            raise DeviceError("unreachable")
        self.commands.append(command)
        if command == "PWON":
            self.power = "on"
        elif command == "PWSTANDBY":
            self.power = "standby"
        elif command in self.sources:
            self.source = command
        if command.startswith("SLP") and command != "SLP?":
            # Refused in silence on the real unit -- no echo, timer unchanged --
            # both for values outside 001-090 and for any write at all while
            # the unit is in standby. Reproduced here because the client's
            # readback check is the only thing standing in for it.
            digits = command[3:]
            if self.power == "standby":
                return []
            if digits == "OFF":
                self.sleep = 0
            elif digits.isdigit() and 1 <= int(digits) <= 90 and len(digits) == 3:
                self.sleep = int(digits)
            else:
                return []
        if command == "SI?" or command in self.sources:
            frames = [self.source]
        elif command.startswith("SLP"):
            frames = [f"SLP{self.sleep:03d}" if self.sleep else "SLPOFF"]
        else:
            frames = self._fixture[self.power].get(command)
        if frames is None:
            raise DeviceError(f"no fixture for AVR {command} in state {self.power}")
        if self.heartbeat:
            stale = "PWSTANDBY" if self.power == "on" else "PWON"
            return [stale, *frames]
        return list(frames)


class FakeHeosTransport:
    """Replays fixture HEOS responses in place of a real receiver.

    Holds a mutable volume so writes are observable, the way the AVR fake holds
    a power state: ``player/set_volume`` updates it and the following
    ``player/get_volume`` reports the new level.
    """

    def __init__(
        self,
        volume: int = 20,
        mute: bool = False,
        fail: bool = False,
        pid: str = "1234567890",
        now_playing_sid: int | None = 1024,
        play_state: str = "play",
        favorites: list[dict[str, Any]] | None = None,
    ) -> None:
        """Configure the fake HEOS endpoint.

        Args:
            volume: HEOS level to report.
            mute: Mute state to report.
            fail: Raise :class:`DeviceError` on every call.
            pid: Player id reported by the transport.
            now_playing_sid: Source id ``get_now_playing_media`` reports, which
                selects one of the recorded payloads: 1024 is the DLNA server
                on the LAN, 3 is TuneIn. ``None`` drops the payload entirely,
                as a player that has never played anything does.
            play_state: Transport state to report, one of ``play``, ``pause``,
                ``stop`` or ``unknown`` -- the last being what the unit was
                measured answering while a transition settles.
            favorites: Payload ``browse/browse`` replays. ``None`` keeps the
                two recorded favourites; pass ``[]`` for a receiver holding
                none.

        Raises:
            ValueError: If no payload was ever recorded for ``now_playing_sid``.
        """
        self.pid = pid
        self.volume = volume
        self.mute = mute
        self.fail = fail
        self.play_state = play_state
        self.favorites = favorites
        self.commands: list[str] = []
        self._fixture = load_fixture("heos.json")
        self._payloads: dict[str, Any] = self._fixture["_now_playing"]
        if now_playing_sid is not None and str(now_playing_sid) not in self._payloads:
            raise ValueError(f"no recorded now-playing payload for sid {now_playing_sid}")
        self.now_playing_sid = now_playing_sid

    def query(self, command: str) -> dict[str, Any]:
        """Record a HEOS command and replay its recorded response.

        Args:
            command: The full ``heos://...`` command string.

        Returns:
            A decoded HEOS response object.

        Raises:
            DeviceError: If the fake is failing, or the command has no fixture.
        """
        if self.fail:
            raise DeviceError("unreachable")
        self.commands.append(command)
        name = command.split("heos://", 1)[-1].split("?", 1)[0]
        params = parse_qs(command.split("?", 1)[-1])
        if name == "player/set_volume":
            self.volume = int(params["level"][0])
        elif name == "player/set_mute":
            self.mute = params["state"][0] == "on"
        elif name == "player/set_play_state":
            # The real unit decides what pause means per medium; the fake just
            # holds what was asked for, which is what the readback reports.
            self.play_state = params["state"][0]
        elif name in ("player/volume_up", "player/volume_down"):
            # Relative, and clamped the way the scale is: the device has no
            # level below 0 or above 100 to step onto.
            step = int(params["step"][0])
            level = self.volume + (step if name.endswith("up") else -step)
            self.volume = max(0, min(100, level))
        template = self._fixture.get(name)
        if template is None:
            raise DeviceError(f"no fixture for HEOS {name}")
        response = json.loads(json.dumps(template))
        response["heos"]["message"] = response["heos"]["message"].format(
            pid=self.pid,
            level=self.volume,
            mute="on" if self.mute else "off",
            state=self.play_state,
            step=params.get("step", [""])[0],
            preset=params.get("preset", [""])[0],
        )
        if name == "browse/browse" and self.favorites is not None:
            response["payload"] = json.loads(json.dumps(self.favorites))
        if name == "player/get_now_playing_media":
            sid = self.now_playing_sid
            payload = {} if sid is None else self._payloads[str(sid)]
            response["payload"] = json.loads(json.dumps(payload))
        return response
