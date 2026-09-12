"""Device I/O. The only module in this project that opens a socket.

The RCD-N12 answers on two unrelated protocols, so there are two transports:

* :class:`TelnetTransport` -- AVR control, TCP 23, CR-terminated ASCII. Power,
  source and sleep live here. The receiver accepts exactly one connection on
  this port, so every call connects, sends, drains and closes; the socket is
  never held open between calls.
* :class:`HeosTransport` -- HEOS CLI, TCP 1255, CRLF-terminated, single-line
  JSON. Volume, mute and playback live here.

Both derive from :class:`_PacedTransport`, which owns a *process-wide* lock and
last-contact clock. The pacing is therefore device-wide rather than per
protocol: two commands on different ports still cannot land back to back.
Denon units are reported to soft-lock when they do, so this is a safety
interlock rather than politeness. Each retry attempt is separately paced and so
inherits the same gap.

:class:`SupportsTelnet` and :class:`SupportsHeos` are the interfaces the fakes
in ``tests/fakes.py`` implement; ``tests/test_transport.py`` asserts the real
transports and the fakes stay in step.
"""

from __future__ import annotations

import json
import logging
import re
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "device.yaml"

#: Every command sent and response received is appended here.
LOG_PATH = ROOT / "logs" / "device.log"

#: Minimum seconds between the end of one device transaction and the start of
#: the next. The protocol reference puts the floor at 300-500 ms.
MIN_GAP_S = 0.5

#: Extra attempts after the first before a call is given up on.
RETRIES = 2

#: Base seconds to wait before a retry; multiplied by the attempt number.
RETRY_BACKOFF_S = 1.0

AVR_PORT = 23
HEOS_PORT = 1255

#: Marker HEOS puts in ``message`` when it is acknowledging a command rather
#: than answering it. The answer arrives as a second message on the same
#: socket. Measured 2026-09-11 on ``browse/browse``.
UNDER_PROCESS = "command under process"

T = TypeVar("T")

_logger = logging.getLogger("denon_rcd_n12.device")
_log_lock = threading.Lock()
_handler_path: Path | None = None


class DeviceError(RuntimeError):
    """The receiver was addressable but the exchange did not succeed."""


@runtime_checkable
class SupportsTelnet(Protocol):
    """The AVR-protocol interface shared by the real transport and its fake."""

    host: str

    def send(self, command: str, expect: str | None = ..., listen: float = ...) -> list[str]:
        """Send an AVR command and return the frames received."""


@runtime_checkable
class SupportsHeos(Protocol):
    """The HEOS interface shared by the real transport and its fake."""

    pid: str

    def query(self, command: str) -> dict[str, Any]:
        """Send a HEOS command and return the decoded response."""


def _log(direction: str, text: str) -> None:
    """Append one line to the device log.

    The file handler is attached on first use so merely importing this module
    creates nothing, and is rebuilt if :data:`LOG_PATH` is repointed.

    Args:
        direction: Short tag such as ``"->"``, ``"<-"`` or ``"!!"``.
        text: The command, response, or message to record.
    """
    global _handler_path
    with _log_lock:
        if _handler_path != LOG_PATH:
            for handler in list(_logger.handlers):
                _logger.removeHandler(handler)
                handler.close()
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            _logger.addHandler(handler)
            _logger.setLevel(logging.INFO)
            _logger.propagate = False
            _handler_path = LOG_PATH
    _logger.info("%s %s", direction, text)


def _parse_flat_yaml(text: str) -> dict[str, Any]:
    """Parse the two-level ``key:`` / ``  key: value`` shape of device.yaml.

    A deliberate stand-in for PyYAML so the control server runs on a bare
    interpreter. Used only when PyYAML cannot be imported.

    Args:
        text: Contents of the YAML file.

    Returns:
        Nested mapping of the top-level sections and their scalar members.
    """
    out: dict[str, Any] = {}
    section: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        key, _, value = line.strip().partition(":")
        key, value = key.strip(), value.strip()
        if not value:
            section = {}
            out[key] = section
            continue
        parsed: Any = int(value) if value.isdigit() else value
        if line[:1].isspace() and section is not None:
            section[key] = parsed
        else:
            out[key] = parsed
    return out


def load_config(path: Path | str = CONFIG_PATH) -> dict[str, Any]:
    """Read the device configuration.

    Args:
        path: Location of ``device.yaml``.

    Returns:
        The parsed configuration mapping.

    Raises:
        FileNotFoundError: If the configuration file is absent.
    """
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        import yaml
    except ImportError:
        return _parse_flat_yaml(text)
    return yaml.safe_load(text)


class _PacedTransport:
    """Shared pacing, serialisation and retry policy for both protocols.

    The lock and last-contact clock are class attributes on this base, so a
    :class:`TelnetTransport` and a :class:`HeosTransport` in the same process
    pace against each other rather than each keeping its own schedule.
    """

    _lock = threading.Lock()
    _last_contact = 0.0

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 3.0,
        min_gap: float = MIN_GAP_S,
        retries: int = RETRIES,
        retry_backoff: float = RETRY_BACKOFF_S,
    ) -> None:
        """Bind a transport to one receiver port.

        Args:
            host: Receiver address, from ``config/device.yaml``.
            port: TCP port this transport talks to.
            timeout: Connect and read timeout in seconds.
            min_gap: Minimum quiet period between transactions, in seconds.
            retries: Extra attempts after the first before giving up.
            retry_backoff: Base delay before a retry, scaled by attempt number.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.min_gap = min_gap
        self.retries = retries
        self.retry_backoff = retry_backoff

    @contextmanager
    def _paced(self) -> Iterator[None]:
        """Hold the device lock, waiting out the minimum gap before yielding."""
        with _PacedTransport._lock:
            wait = self.min_gap - (time.monotonic() - _PacedTransport._last_contact)
            if wait > 0:
                time.sleep(wait)
            try:
                yield
            finally:
                _PacedTransport._last_contact = time.monotonic()

    def _with_retry(self, attempt: Callable[[], T], what: str) -> T:
        """Run one transaction, retrying transient device failures.

        Almost every command these transports issue is a query or an
        idempotent set (``PWON``, ``PWSTANDBY``, ``SI<TOKEN>``, ``set_volume``,
        ``set_mute``), so replaying one cannot compound. Toggling is resolved to
        an absolute state a layer up for exactly this reason.

        ``player/volume_up`` and ``player/volume_down`` are the exception: they
        are relative, so a command that reached the unit and then failed to
        answer is applied twice when replayed. The harm is bounded by one extra
        step of at most 10 on a 0-100 scale, which is cheaper than the
        alternative -- a read-modify-write that costs an extra round trip on
        every press of a volume button and races anyone else changing the level
        between the read and the write.

        Args:
            attempt: The single-shot transaction to run.
            what: Label used in log lines.

        Returns:
            Whatever ``attempt`` returns.

        Raises:
            DeviceError: If every attempt failed.
        """
        last: DeviceError | None = None
        for n in range(self.retries + 1):
            try:
                return attempt()
            except DeviceError as exc:
                last = exc
                if n < self.retries:
                    _log("!!", f"{what} failed ({exc}); retry {n + 1}/{self.retries}")
                    time.sleep(self.retry_backoff * (n + 1))
        _log("!!", f"{what} gave up after {self.retries + 1} attempts")
        assert last is not None
        raise last


class TelnetTransport(_PacedTransport):
    """Denon AVR control protocol over telnet, TCP 23."""

    def __init__(self, host: str, port: int = AVR_PORT, **kwargs: Any) -> None:
        """Bind to the receiver's AVR control port.

        Args:
            host: Receiver address.
            port: TCP port of the AVR control protocol.
            **kwargs: Pacing and retry overrides for :class:`_PacedTransport`.
        """
        super().__init__(host, port, **kwargs)

    @staticmethod
    def _drain(sock: socket.socket) -> None:
        """Half-close and read off the remainder so the peer sees a clean FIN.

        Args:
            sock: The socket to shut down for writing and drain.
        """
        try:
            sock.shutdown(socket.SHUT_WR)
            sock.settimeout(0.3)
            while sock.recv(256):
                pass
        except OSError:
            pass

    def send(self, command: str, expect: str | None = None, listen: float = 2.5) -> list[str]:
        """Send one AVR command and collect the frames that come back.

        Every frame seen inside the listen window is returned and the caller
        filters, rather than the first one being taken as the answer. Third
        party notes describe an unsolicited ``PW`` report every 10 s or so,
        which would interleave with replies; measured 2026-09-12, this unit
        sends nothing at all on an idle socket over 75 s. The tolerance stays
        because it costs nothing and the alternative fails silently on a
        firmware that does chatter.

        Args:
            command: Bare command token such as ``"PW?"``; CR is appended here.
            expect: Regex that ends the read early once the buffer matches it.
            listen: Seconds to keep reading before giving up.

        Returns:
            The CR-separated frames received, in arrival order.

        Raises:
            DeviceError: If the receiver refused or dropped every attempt.
        """
        return self._with_retry(lambda: self._send_once(command, expect, listen), f"AVR {command}")

    def _send_once(self, command: str, expect: str | None, listen: float) -> list[str]:
        """Perform a single AVR exchange.

        Args:
            command: Bare command token; CR is appended here.
            expect: Regex that ends the read early once the buffer matches it.
            listen: Seconds to keep reading before giving up.

        Returns:
            The CR-separated frames received, in arrival order.

        Raises:
            DeviceError: If the receiver refused or dropped the connection.
        """
        pattern = re.compile(expect) if expect else None
        buf = ""
        with self._paced():
            _log("->", f"AVR {command}")
            try:
                with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                    sock.settimeout(0.4)
                    sock.sendall(f"{command}\r".encode("ascii"))
                    deadline = time.monotonic() + listen
                    while time.monotonic() < deadline:
                        try:
                            chunk = sock.recv(1024)
                        except TimeoutError:
                            continue
                        if not chunk:
                            break
                        buf += chunk.decode("ascii", "ignore")
                        if pattern and pattern.search(buf):
                            break
                    self._drain(sock)
            except OSError as exc:
                raise DeviceError(f"AVR {command}: {exc}") from exc
        frames = [frame for frame in buf.split("\r") if frame]
        _log("<-", f"AVR {frames}")
        return frames


class HeosTransport(_PacedTransport):
    """HEOS CLI, TCP 1255."""

    def __init__(self, host: str, port: int = HEOS_PORT, pid: str = "", **kwargs: Any) -> None:
        """Bind to the receiver's HEOS CLI port.

        Args:
            host: Receiver address.
            port: TCP port of the HEOS CLI.
            pid: HEOS player id addressing this unit.
            **kwargs: Pacing and retry overrides for :class:`_PacedTransport`.
        """
        super().__init__(host, port, **kwargs)
        self.pid = str(pid)

    def query(self, command: str) -> dict[str, Any]:
        """Send one HEOS CLI command and return its response object.

        Async change events and replies to unrelated commands are skipped, so
        the object returned always corresponds to ``command``.

        Args:
            command: Full ``heos://...`` command string.

        Returns:
            The decoded JSON response.

        Raises:
            DeviceError: If every attempt failed.
        """
        want = command.split("heos://", 1)[-1].split("?", 1)[0]
        return self._with_retry(lambda: self._query_once(command, want), f"HEOS {want}")

    def _query_once(self, command: str, want: str) -> dict[str, Any]:
        """Perform a single HEOS exchange.

        Args:
            command: Full ``heos://...`` command string.
            want: The bare command name expected in the reply.

        Returns:
            The decoded JSON response.

        Raises:
            DeviceError: On connection failure, timeout, or a ``fail`` result.
        """
        with self._paced():
            _log("->", f"HEOS {command}")
            try:
                with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                    sock.settimeout(self.timeout)
                    sock.sendall(f"{command}\r\n".encode("ascii"))
                    buf = b""
                    while True:
                        try:
                            chunk = sock.recv(4096)
                        except TimeoutError:
                            raise DeviceError(f"HEOS {want}: no response") from None
                        if not chunk:
                            raise DeviceError(f"HEOS {want}: connection closed")
                        buf += chunk
                        while b"\r\n" in buf:
                            line, buf = buf.split(b"\r\n", 1)
                            if not line.strip():
                                continue
                            try:
                                obj = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            heos = obj.get("heos", {})
                            if heos.get("command") != want:
                                continue
                            _log("<-", f"HEOS {line.decode('utf-8', 'replace')}")
                            if heos.get("result") != "success":
                                raise DeviceError(f"HEOS {want}: {heos.get('message')}")
                            if UNDER_PROCESS in heos.get("message", ""):
                                # A slow command -- browsing a source, so far --
                                # is acknowledged immediately with an empty
                                # payload, and the real answer follows as a
                                # second message on this same socket. Returning
                                # the acknowledgement would hand the caller an
                                # empty result that looks like an empty source.
                                continue
                            return obj
            except OSError as exc:
                raise DeviceError(f"HEOS {want}: {exc}") from exc


def transports_from_config(
    path: Path | str = CONFIG_PATH, **kwargs: Any
) -> tuple[TelnetTransport, HeosTransport]:
    """Build both transports from ``config/device.yaml``.

    Args:
        path: Location of the configuration file.
        **kwargs: Pacing and retry overrides applied to both transports.

    Returns:
        The telnet and HEOS transports for the configured receiver.
    """
    cfg = load_config(path)
    device = cfg.get("device", {})
    ports = cfg.get("ports", {})
    host = device["host"]
    telnet = TelnetTransport(host, port=int(ports.get("avr", AVR_PORT)), **kwargs)
    heos = HeosTransport(
        host,
        port=int(ports.get("heos", HEOS_PORT)),
        pid=device.get("heos_pid", ""),
        **kwargs,
    )
    return telnet, heos


def heos_message(obj: dict[str, Any]) -> dict[str, str]:
    """Split a HEOS response's ``message`` field into its key/value pairs.

    Args:
        obj: A decoded HEOS response object.

    Returns:
        The ``&``-delimited message parameters as a flat mapping.
    """
    return {k: v[0] for k, v in parse_qs(obj.get("heos", {}).get("message", "")).items()}
