"""Command layer over :mod:`transport`.

Routes each capability to the protocol that actually implements it: power and
input source to the AVR protocol on port 23, volume, mute and playback to HEOS
on 1255.
Holding the two transports side by side is what makes that routing explicit at
the call site. Source is the one capability that needs both -- the AVR protocol
names the input, and only HEOS can say whether the network input is carrying a
streaming service or a server on the LAN.

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

#: Bounds of the relative step HEOS accepts for ``volume_up``/``volume_down``.
VOLUME_STEP_MIN = 1
VOLUME_STEP_MAX = 10

#: The input names this project uses, mapped to the ``SI`` tokens this unit
#: actually answers with. Measured 2026-09-06 by cycling every input at the
#: receiver; see ``docs/reference/web-interface.md``. The tokens are specific to
#: this model -- ``SIANALOG1`` rather than ``SIAUX``, ``SIHDMIARC`` rather than
#: ``SIHDMI`` -- so nothing here should be carried to another Denon.
SOURCES = {
    "phono": "SIANALOGPHONO",
    "aux": "SIANALOG1",
    "cd": "SICD",
    "optical": "SIOPTICAL1",
    "tuner": "SITUNER",
    "hdmi": "SIHDMIARC",
    "net": "SINET",
}

#: The transport states this unit reports. All four are measured
#: (``notebooks/03-odtwarzanie.ipynb``, 2026-09-07): ``stop`` is also what a
#: sleeping unit answers, and ``unknown`` -- which the HEOS command reference
#: does not document -- appears for a moment at every transition, including
#: while an input change settles. Treat it as "ask again", not as an error.
PLAY_STATES = ("play", "pause", "stop", "unknown")

#: The transport states this unit accepts as a command. ``unknown`` is missing
#: on purpose: the receiver reports it while a change settles but there is no
#: such thing to ask for.
SETTABLE_PLAY_STATES = ("play", "pause", "stop")

#: Seconds to let a transport command settle before reading it back. Measured
#: 2026-09-11: a pause had settled by 1.5 s, and a resume usually by 2 s though
#: it can pass through ``unknown`` for longer. The readback is therefore not a
#: guarantee -- it is what the unit says at that moment.
PLAYBACK_SETTLE_S = 1.5

#: Bounds of the sleep timer, in minutes. Measured 2026-09-12: 001 and 090 are
#: accepted, 091 and everything above it is refused in silence. The sibling
#: DRA-N4 documents 001-120; that part did not carry over. Zero is not a timer
#: value -- it is how this client spells ``SLPOFF``.
SLEEP_MIN = 1
SLEEP_MAX = 90

#: The network input, as :meth:`DenonClient.get_source` reports it when a
#: streaming service is playing. Readable, not selectable -- see
#: :data:`SELECTABLE_SOURCES`.
SOURCE_NET = "net"

#: A streaming service and a DLNA server on the LAN are one input to the AVR
#: protocol: both read back as ``SINET``. :meth:`DenonClient.get_source`
#: separates them through HEOS and reports this name for the server. It is a
#: read-only state -- see :meth:`DenonClient.set_source`.
SOURCE_SERVER = "server"

#: The inputs an ``SI`` write can actually select on this unit. Measured
#: 2026-09-08: ``SICD`` and ``SIANALOG1`` switch the input within a second,
#: while ``SINET`` is accepted by the socket, echoed by nothing, and ignored --
#: the input stayed put across twelve seconds of polling with the unit awake,
#: and again from standby. The network input appears to be a *consequence* of
#: HEOS playing something rather than a destination ``SI`` can drive, which is
#: the same reason :data:`SOURCE_SERVER` was read-only from the start.
SELECTABLE_SOURCES = tuple(name for name in SOURCES if name != SOURCE_NET)

#: HEOS source id of the favourites list, from ``browse/get_music_sources``.
FAVORITES_SID = 1028

#: Seconds to let a favourite start before reading back what is playing.
#: Measured 2026-09-11: without it the readback names the *previous* station,
#: because the metadata trails the command. Two seconds was enough for the
#: station name every time; the track title takes longer still and arrives as
#: the stream's bitrate first, which no delay short enough to be worth paying
#: would fix.
FAVORITE_SETTLE_S = 2.0

#: HEOS source id of the local-media service. A foobar2000 share on the LAN was
#: measured reporting this generic id rather than one of its own, so comparing
#: against it is enough to tell a local server from a streaming service.
LOCAL_MEDIA_SID = 1024

#: Seconds to let an input change settle before reading it back. Known
#: sufficient, not known necessary: every ``SI`` write measured from 2026-09-07
#: on read back correctly after it, including from standby, where the write
#: draws no echo at all. Note the write itself is slow -- an echo took 1.07 s
#: against 23 ms for a query -- so this is charged on top of that.
SOURCE_SETTLE_S = 1.0

_PW_FRAME = re.compile(r"PW(ON|STANDBY)")
_SI_FRAME = re.compile(r"SI[A-Z0-9/]+")
_SLP_FRAME = re.compile(r"SLP(OFF|\d{3})")

#: Reverse of :data:`SOURCES`. Unambiguous because ``SINET`` appears once there;
#: the server sense of that token is resolved separately, through HEOS.
_NAMES = {token: name for name, token in SOURCES.items()}

#: Seconds to let the unit boot after ``PWON`` before reading state back.
#: Measured 2026-09-12: ``PW?`` confirmed ``PWON`` at the first poll every time,
#: three cold starts at 0.52, 0.53 and 0.52 s -- and those are the transport's
#: own pacing floor, so the unit answered faster than this project can ask. The
#: 4.0 s carried over from a third party estimate was eight times what the AVR
#: protocol needs. Kept at double the measured bound rather than at the bound:
#: answering ``PW?`` is not proof that every other command is ready, and a
#: readback failure here surfaces as an error on the page.
WAKE_SETTLE_S = 1.0

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

    def step_volume(self, direction: str, step: int = 1) -> dict[str, Any]:
        """Nudge the volume up or down over HEOS.

        Relative, unlike :meth:`set_volume`: the unit applies the step to
        whatever level it currently holds, so no read is needed first. That
        makes it the one command in this client a retry could compound -- see
        the note in :meth:`~denon_rcd_n12.transport._PacedTransport._with_retry`
        -- at a cost bounded by one extra step.

        Measured on the device 2026-09-08, awake and in standby: 15 to 16 and
        back, 0 to 1 and back.

        Args:
            direction: ``"up"`` or ``"down"``.
            step: Size of the step, 1-10 on the HEOS absolute scale.

        Returns:
            Mapping with ``volume`` (int, 0-100) and ``mute`` (bool), as
            :meth:`get_volume` reports them after the step.

        Raises:
            ValueError: If ``direction`` is not a direction, or ``step`` falls
                outside the range HEOS accepts.
            DeviceError: If the receiver rejected the command or could not be
                read back.
        """
        if direction not in ("up", "down"):
            raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")
        if not isinstance(step, int) or not VOLUME_STEP_MIN <= step <= VOLUME_STEP_MAX:
            raise ValueError(
                f"step must be an integer {VOLUME_STEP_MIN}-{VOLUME_STEP_MAX}, "
                f"got {step!r}"
            )
        self.heos.query(
            f"heos://player/volume_{direction}?pid={self.heos.pid}&step={step}"
        )
        return self.get_volume()

    def set_mute(self, state: bool) -> dict[str, Any]:
        """Mute or unmute over HEOS and read back what the unit settled on.

        Measured on the device 2026-09-08. Unlike an ``SI`` write, this does
        not wake a sleeping unit.

        Args:
            state: ``True`` to mute, ``False`` to unmute.

        Returns:
            Mapping with ``volume`` (int, 0-100) and ``mute`` (bool), as
            :meth:`get_volume` reports them after the write.

        Raises:
            DeviceError: If the receiver rejected the command or could not be
                read back.
        """
        self.heos.query(
            f"heos://player/set_mute?pid={self.heos.pid}"
            f"&state={'on' if state else 'off'}"
        )
        return self.get_volume()

    def toggle_mute(self) -> dict[str, Any]:
        """Flip the unit between muted and unmuted.

        Returns:
            Mapping with ``volume`` (int, 0-100) and ``mute`` (bool), as
            :meth:`get_volume` reports them after the write.

        Raises:
            DeviceError: If the receiver could not be reached or read back.
        """
        return self.set_mute(not self.get_volume()["mute"])

    def get_source(self) -> str:
        """Read which input the receiver is on.

        Costs one AVR round trip, plus one HEOS round trip in the single case
        that needs it: ``SINET`` covers both a streaming service and a DLNA
        server on the LAN, so that token alone cannot say which is playing.
        Every other input is decided by the ``SI`` reply and asks HEOS nothing.

        Returns:
            A name from :data:`SOURCES`, or :data:`SOURCE_SERVER` when the
            network input is carrying local media.

        Raises:
            DeviceError: If no ``SI`` frame arrived, or it carried a token this
                unit was never measured returning.
        """
        frames = self.telnet.send("SI?", expect=_SI_FRAME.pattern)
        token = self._token_from(frames)
        name = _NAMES.get(token)
        if name is None:
            raise DeviceError(f"unknown source token {token!r} in reply: {frames!r}")
        if name != "net":
            return name
        return SOURCE_SERVER if self._playing_sid() == LOCAL_MEDIA_SID else name

    def set_source(self, name: str) -> str:
        """Switch the receiver to an input and read back what it settled on.

        Sending a token the unit already holds is skipped, as in
        :meth:`set_power`: switching inputs is audible, so a redundant write is
        worth one query to avoid. The comparison is by token, which is why
        asking for ``"net"`` while a server is playing changes nothing and
        reports back ``"server"`` -- the input is already correct, and the
        readback says what is actually on it.

        Both network names are rejected rather than written. ``"server"`` was
        always a read-only state -- whether a server or a streaming service
        plays is decided by HEOS, not by ``SI`` -- and ``"net"`` joined it on
        2026-09-08, when the unit was measured ignoring ``SINET`` outright. The
        alternative is a call that reports the input it failed to leave, which
        reads as a broken control rather than an unsupported one.

        Args:
            name: An input name from :data:`SELECTABLE_SOURCES`.

        Returns:
            The input read back after the command, as :meth:`get_source`
            reports it.

        Raises:
            ValueError: If ``name`` is a network state, or is not a known input
                name.
            DeviceError: If the receiver could not be reached or read back.
        """
        if name in (SOURCE_SERVER, SOURCE_NET):
            raise ValueError(
                f"{name!r} is a read-only state: this unit ignores SINET as a "
                "write, and shows the network input when HEOS plays something. "
                "Start playback in HEOS instead."
            )
        if name not in SOURCES:
            raise ValueError(
                f"source must be one of {sorted(SELECTABLE_SOURCES)}, got {name!r}"
            )
        token = SOURCES[name]
        current = self.get_source()
        if self._token_of(current) == token:
            return current
        self.telnet.send(token, expect=token, listen=1.5)
        time.sleep(SOURCE_SETTLE_S)
        return self.get_source()

    def get_playback(self) -> dict[str, Any]:
        """Read the transport state and what is loaded in it, over HEOS.

        Costs two HEOS round trips: the state and the metadata are separate
        commands. The title is whichever field the unit filled in -- ``song``
        for a track, ``station`` for a stream that names no track -- so a
        caller gets one field instead of having to know which kind of media is
        playing. A TuneIn stream fills in *both*, ``song`` being the track on
        air and ``station`` the station carrying it, so the station is reported
        separately rather than folded into the title.

        The metadata is not evidence that anything is playing. With the unit in
        standby it still reports the last track of the previous session
        alongside a ``stop`` state (measured 2026-09-07), so only ``state``
        says whether there is sound. A caller showing the title is expected to
        show the state next to it.

        Both fields are read for whichever input is selected, not just the
        network ones: a CD reports its track, and the AUX input reports itself.
        They can lag an input change by a second or so, so a read taken
        immediately after switching inputs may still describe the previous one.

        Returns:
            Mapping with ``state`` (one of :data:`PLAY_STATES`) and ``title``,
            ``artist``, ``album``, ``station`` and ``media_type``, each a
            string or ``None`` when the current input carries no such metadata.

        Raises:
            DeviceError: If either HEOS query failed.
        """
        reply = self.heos.query(f"heos://player/get_play_state?pid={self.heos.pid}")
        media = self._now_playing()
        return {
            "state": heos_message(reply).get("state"),
            "title": media.get("song") or media.get("station") or None,
            "artist": media.get("artist") or None,
            "album": media.get("album") or None,
            "station": media.get("station") or None,
            "media_type": media.get("type") or None,
        }

    def set_play_state(self, state: str) -> dict[str, Any]:
        """Drive the transport: play, pause or stop.

        What ``pause`` does depends on the medium, and the receiver decides
        rather than this client. Measured 2026-09-11: a disc pauses and keeps
        its track, while a live stream cannot be held and is stopped instead,
        the state settling on ``stop`` and the title falling back to the
        stream's bitrate. Both are the unit honouring the command; neither is
        it ignoring one.

        Args:
            state: One of :data:`SETTABLE_PLAY_STATES`.

        Returns:
            Playback as :meth:`get_playback` reports it after the command. It
            may still read ``unknown``: a resume can take several seconds to
            settle, and the readback is what the unit says at that moment
            rather than a promise about where it lands.

        Raises:
            ValueError: If ``state`` is not a state that can be asked for.
            DeviceError: If the receiver rejected the command or could not be
                read back.
        """
        if state not in SETTABLE_PLAY_STATES:
            raise ValueError(
                f"play state must be one of {list(SETTABLE_PLAY_STATES)}, got {state!r}"
            )
        self.heos.query(
            f"heos://player/set_play_state?pid={self.heos.pid}&state={state}"
        )
        time.sleep(PLAYBACK_SETTLE_S)
        return self.get_playback()

    def get_sleep(self) -> int:
        """Read the sleep timer, in minutes.

        Returns:
            Minutes remaining, or ``0`` when no timer is set. The receiver
            spells that ``SLPOFF``; zero is this client's name for it, so a
            caller can treat the value as a number throughout.

        Raises:
            DeviceError: If no ``SLP`` frame arrived within the listen window.
        """
        return self._sleep_from(self.telnet.send("SLP?", expect=_SLP_FRAME.pattern))

    def set_sleep(self, minutes: int) -> int:
        """Arm or cancel the sleep timer, and read back what it settled on.

        The range is the unit's own, measured rather than carried over: 1 to 90
        minutes, where the sibling model documents 120. A value outside it is
        refused **silently** by the receiver -- no echo, timer unchanged -- so
        the bound is enforced here, where it can be explained, rather than left
        to a command that fails without saying so.

        A sleeping unit refuses the write the same silent way, measured
        2026-09-12. The readback is therefore compared against what was asked
        for, and a mismatch is raised rather than returned: reporting the timer
        the receiver kept would be a control that appears to work.

        Args:
            minutes: 1 to 90 to arm the timer, or 0 to cancel it.

        Returns:
            The timer as :meth:`get_sleep` reports it after the write.

        Raises:
            ValueError: If ``minutes`` is not 0 or within the accepted range.
            DeviceError: If the receiver could not be reached, could not be read
                back, or ignored the write.
        """
        if not isinstance(minutes, int) or minutes < 0 or minutes > SLEEP_MAX:
            raise ValueError(
                f"sleep must be 0 to cancel, or {SLEEP_MIN}-{SLEEP_MAX} minutes, "
                f"got {minutes!r}"
            )
        command = "SLPOFF" if minutes == 0 else f"SLP{minutes:03d}"
        self.telnet.send(command, expect=_SLP_FRAME.pattern, listen=1.5)
        settled = self.get_sleep()
        if settled != minutes:
            raise DeviceError(
                f"the receiver ignored {command}: asked for {minutes}, reads "
                f"{settled}. It refuses the sleep timer while in standby; wake "
                "it first."
            )
        return settled

    def get_status(self) -> dict[str, Any]:
        """Read everything the page shows, in one call.

        Costs seven or eight paced device transactions -- power, the sleep
        timer and the input from the AVR side, volume, mute and playback from
        HEOS -- so it takes several seconds. That is the point: it is one wait
        instead of four, and the 2026-09-12 decision record settles that the
        page pulls rather than subscribes.

        Returns:
            The union of :meth:`get_power`, :meth:`get_volume`,
            :meth:`get_source`, :meth:`get_playback` and :meth:`get_sleep`,
            with ``power``, ``source`` and ``sleep`` as their own keys.

        Raises:
            DeviceError: If any of the underlying reads failed. The whole call
                fails rather than returning a half-built picture.
        """
        return {
            "power": self.get_power(),
            **self.get_volume(),
            "source": self.get_source(),
            **self.get_playback(),
            "sleep": self.get_sleep(),
        }

    def list_favorites(self) -> list[dict[str, Any]]:
        """List the favourites stored on the receiver, over HEOS.

        One HEOS round trip, though a slow one: browsing a source is answered
        in two messages, an acknowledgement and then the listing, which
        :class:`~denon_rcd_n12.transport.HeosTransport` waits out.

        Reading only. Each entry carries the ``mid`` that would start it
        playing, but nothing here plays anything -- whether a favourite can be
        started, and whether doing so is what finally selects the network
        input, is open question 17.

        Returns:
            One mapping per favourite, with ``name``, ``mid``, ``media_type``
            and ``playable``. Empty when the receiver holds no favourites.

        Raises:
            DeviceError: If the HEOS query failed.
        """
        reply = self.heos.query(f"heos://browse/browse?sid={FAVORITES_SID}")
        return [
            {
                "name": entry.get("name"),
                "mid": entry.get("mid"),
                "media_type": entry.get("type"),
                "playable": entry.get("playable") == "yes",
            }
            for entry in reply.get("payload") or []
        ]

    def play_favorite(self, position: int) -> dict[str, Any]:
        """Start one of the receiver's favourites, by its position in the list.

        Measured 2026-09-11: asking for position 2 while position 1 played
        switched the station within two seconds, and asking for 1 switched it
        back. The position is HEOS's own 1-based ``preset`` numbering, which is
        the order :meth:`list_favorites` reports.

        The upper bound is left to the receiver. Checking it here would cost a
        listing on every call to guard against a number the device rejects
        perfectly well on its own.

        Note:
            Whether this also *selects* the network input from another input is
            not established -- every measurement so far started with the unit
            already on it. Open question 17.

        Args:
            position: 1-based position in the favourites list.

        Returns:
            Playback as :meth:`get_playback` reports it once the change has
            settled. The station name is reliable; the title often is not yet,
            naming the stream's bitrate until the unit learns what is on air.

        Raises:
            ValueError: If ``position`` is not a positive integer.
            DeviceError: If the receiver rejected the command, which is what an
                out-of-range position looks like.
        """
        if not isinstance(position, int) or position < 1:
            raise ValueError(f"favourite position must be 1 or more, got {position!r}")
        self.heos.query(
            f"heos://browse/play_preset?pid={self.heos.pid}&preset={position}"
        )
        time.sleep(FAVORITE_SETTLE_S)
        return self.get_playback()

    def _now_playing(self) -> dict[str, Any]:
        """Read the HEOS metadata for whatever is loaded in the player.

        Returns:
            The ``player/get_now_playing_media`` payload, empty when the reply
            carried none -- a player that has never played anything, for
            instance.

        Raises:
            DeviceError: If the HEOS query failed.
        """
        reply = self.heos.query(
            f"heos://player/get_now_playing_media?pid={self.heos.pid}"
        )
        return reply.get("payload") or {}

    def _playing_sid(self) -> int | None:
        """Read the HEOS source id of whatever is currently playing.

        Returns:
            The ``sid`` from ``player/get_now_playing_media``, or ``None`` when
            the reply carried no payload -- an idle player, for instance.

        Raises:
            DeviceError: If the HEOS query failed.
        """
        sid = self._now_playing().get("sid")
        return None if sid is None else int(sid)

    @staticmethod
    def _token_of(name: str) -> str:
        """Return the ``SI`` token an input name maps to.

        Args:
            name: A name from :data:`SOURCES` or :data:`SOURCE_SERVER`.

        Returns:
            The matching token; the server name resolves to ``SINET``, which is
            what the receiver reports for it.
        """
        return SOURCES["net"] if name == SOURCE_SERVER else SOURCES[name]

    @staticmethod
    def _token_from(frames: list[str]) -> str:
        """Pick the source token out of a batch of AVR frames.

        Args:
            frames: Frames as returned by :meth:`TelnetTransport.send`.

        Returns:
            The most recent ``SI`` token seen. Taking the last rather than
            the first costs nothing and survives an unsolicited ``PW`` frame
            arriving alongside the reply, which third party notes describe and
            this unit has never been seen to do.

        Raises:
            DeviceError: If no frame carried a source token.
        """
        matches = [f.strip() for f in frames if _SI_FRAME.fullmatch(f.strip())]
        if not matches:
            raise DeviceError(f"no SI frame in reply: {frames!r}")
        return matches[-1]

    @staticmethod
    def _sleep_from(frames: list[str]) -> int:
        """Pick the sleep timer out of a batch of AVR frames.

        Args:
            frames: Frames as returned by :meth:`TelnetTransport.send`.

        Returns:
            Minutes, or ``0`` for ``SLPOFF``.

        Raises:
            DeviceError: If no frame carried a sleep value.
        """
        matches = [m.group(1) for f in frames if (m := _SLP_FRAME.search(f))]
        if not matches:
            raise DeviceError(f"no SLP frame in reply: {frames!r}")
        return 0 if matches[-1] == "OFF" else int(matches[-1])

    @staticmethod
    def _power_from(frames: list[str]) -> str:
        """Pick the power state out of a batch of AVR frames.

        A status report and a query reply carry the same token, so the most
        recent match is authoritative whichever it was.

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
