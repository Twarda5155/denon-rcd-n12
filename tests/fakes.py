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

    Holds a mutable power state so writes are observable, records every command
    for assertions, and can prepend a stale ``PW`` heartbeat frame to reproduce
    the interleaving seen on the real port-23 stream.
    """

    def __init__(
        self,
        power: str = "on",
        heartbeat: bool = False,
        fail: bool = False,
        host: str = "10.0.0.1",
    ) -> None:
        """Configure the fake AVR endpoint.

        Args:
            power: Initial power state, ``"on"`` or ``"standby"``.
            heartbeat: Prepend a stale opposite-state ``PW`` frame to replies.
            fail: Raise :class:`DeviceError` on every call.
            host: Address reported by the transport.
        """
        self.host = host
        self.power = power
        self.heartbeat = heartbeat
        self.fail = fail
        self.commands: list[str] = []
        self._fixture = load_fixture("avr.json")

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
        frames = self._fixture[self.power].get(command)
        if frames is None:
            raise DeviceError(f"no fixture for AVR {command} in state {self.power}")
        if self.heartbeat:
            stale = "PWSTANDBY" if self.power == "on" else "PWON"
            return [stale, *frames]
        return list(frames)


class FakeHeosTransport:
    """Replays fixture HEOS responses in place of a real receiver."""

    def __init__(
        self,
        volume: int = 20,
        mute: bool = False,
        fail: bool = False,
        pid: str = "1234567890",
    ) -> None:
        """Configure the fake HEOS endpoint.

        Args:
            volume: HEOS level to report.
            mute: Mute state to report.
            fail: Raise :class:`DeviceError` on every call.
            pid: Player id reported by the transport.
        """
        self.pid = pid
        self.volume = volume
        self.mute = mute
        self.fail = fail
        self.commands: list[str] = []
        self._fixture = load_fixture("heos.json")

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
        template = self._fixture.get(name)
        if template is None:
            raise DeviceError(f"no fixture for HEOS {name}")
        response = json.loads(json.dumps(template))
        response["heos"]["message"] = response["heos"]["message"].format(
            pid=self.pid, level=self.volume, mute="on" if self.mute else "off"
        )
        return response
