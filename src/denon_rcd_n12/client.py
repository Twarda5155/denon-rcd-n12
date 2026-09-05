"""Command layer over :mod:`transport`.

Routes each capability to the protocol that actually implements it: power to
the AVR protocol on port 23, volume and mute to HEOS on 1255. Holding the two
transports side by side is what makes that routing explicit at the call site.

Opens no sockets of its own -- everything goes through the injected transports,
which is what lets the tests run against fakes with the receiver powered off.
"""

from __future__ import annotations

import re
import time
from typing import Any

from .transport import (
    DeviceError,
    SupportsHeos,
    SupportsTelnet,
    heos_message,
    transports_from_config,
)

POWER_ON = "on"
POWER_STANDBY = "standby"

#: Bounds of the HEOS absolute volume scale. Not the AVR ``MV`` scale, not dB.
VOLUME_MIN = 0
VOLUME_MAX = 100

_PW_FRAME = re.compile(r"PW(ON|STANDBY)")

#: Seconds to let the unit boot after ``PWON`` before reading state back. The
#: protocol reference estimates 2-5 s before it accepts a follow-up command.
WAKE_SETTLE_S = 4.0

#: Seconds to let the unit settle after ``PWSTANDBY``.
SLEEP_SETTLE_S = 1.5


class DenonClient:
    """High-level commands for one RCD-N12."""

    def __init__(self, telnet: SupportsTelnet, heos: SupportsHeos) -> None:
        """Wrap the two device transports.

        Args:
            telnet: AVR-protocol channel, used for power.
            heos: HEOS channel, used for volume and mute.
        """
        self.telnet = telnet
        self.heos = heos

    @classmethod
    def from_config(cls, **kwargs: Any) -> DenonClient:
        """Build a client against the receiver in ``config/device.yaml``.

        Args:
            **kwargs: Overrides forwarded to :func:`transports_from_config`.

        Returns:
            A client bound to the configured receiver.
        """
        return cls(*transports_from_config(**kwargs))

    @property
    def host(self) -> str:
        """The receiver's address."""
        return self.telnet.host

    def get_power(self) -> str:
        """Read the current power state.

        Returns:
            ``"on"`` or ``"standby"``.

        Raises:
            DeviceError: If no ``PW`` frame arrived within the listen window.
        """
        return self._power_from(self.telnet.send("PW?", expect=r"PW(ON|STANDBY)"))

    def set_power(self, state: str) -> str:
        """Drive the unit to a power state and read back what it settled on.

        Sending ``PWON`` to a unit already on, or ``PWSTANDBY`` to one already
        in standby, is skipped -- there is nothing to change and the write is
        avoided.

        Args:
            state: ``"on"`` or ``"standby"``.

        Returns:
            The power state read back after the command.

        Raises:
            ValueError: If ``state`` is not a recognised power state.
            DeviceError: If the receiver could not be reached or read back.
        """
        if state not in (POWER_ON, POWER_STANDBY):
            raise ValueError(f"power state must be 'on' or 'standby', got {state!r}")
        if self.get_power() == state:
            return state
        if state == POWER_ON:
            self.telnet.send("PWON", expect=r"PWON", listen=1.5)
            time.sleep(WAKE_SETTLE_S)
        else:
            self.telnet.send("PWSTANDBY", expect=r"PWSTANDBY", listen=1.5)
            time.sleep(SLEEP_SETTLE_S)
        return self.get_power()

    def toggle_power(self) -> str:
        """Flip the unit between on and standby.

        Returns:
            The power state read back after the command.

        Raises:
            DeviceError: If the receiver could not be reached or read back.
        """
        target = POWER_STANDBY if self.get_power() == POWER_ON else POWER_ON
        return self.set_power(target)

    def get_volume(self) -> dict[str, Any]:
        """Read playback volume and mute over HEOS.

        The level is HEOS's absolute 0-100 scale, which is not the AVR ``MV``
        scale and not decibels.

        Returns:
            Mapping with ``volume`` (int, 0-100) and ``mute`` (bool).

        Raises:
            DeviceError: If either HEOS query failed.
        """
        pid = self.heos.pid
        level = heos_message(self.heos.query(f"heos://player/get_volume?pid={pid}"))
        state = heos_message(self.heos.query(f"heos://player/get_mute?pid={pid}"))
        return {"volume": int(level["level"]), "mute": state.get("state") == "on"}

    def set_volume(self, level: int) -> dict[str, Any]:
        """Set playback volume over HEOS and read back what the unit settled on.

        Unlike :meth:`set_power` this does not first query the current level to
        skip a redundant write: the pre-read would cost two HEOS round trips
        before every step of a slider, and re-sending a level the unit already
        holds costs it nothing.

        Args:
            level: Target level on the HEOS absolute scale, 0-100.

        Returns:
            Mapping with ``volume`` (int, 0-100) and ``mute`` (bool), as
            :meth:`get_volume` reports them after the write.

        Raises:
            ValueError: If ``level`` is not an integer within the HEOS scale.
            DeviceError: If the receiver rejected the command or could not be
                read back.
        """
        if not isinstance(level, int) or not VOLUME_MIN <= level <= VOLUME_MAX:
            raise ValueError(
                f"volume must be an integer {VOLUME_MIN}-{VOLUME_MAX}, got {level!r}"
            )
        self.heos.query(f"heos://player/set_volume?pid={self.heos.pid}&level={level}")
        return self.get_volume()

    @staticmethod
    def _power_from(frames: list[str]) -> str:
        """Pick the power state out of a batch of AVR frames.

        The heartbeat and the query reply are the same token, so the most
        recent match is authoritative.

        Args:
            frames: Frames as returned by :meth:`TelnetTransport.send`.

        Returns:
            ``"on"`` or ``"standby"``.

        Raises:
            DeviceError: If no frame carried a power state.
        """
        matches = [m.group(1) for f in frames if (m := _PW_FRAME.search(f))]
        if not matches:
            raise DeviceError(f"no PW frame in reply: {frames!r}")
        return POWER_ON if matches[-1] == "ON" else POWER_STANDBY
