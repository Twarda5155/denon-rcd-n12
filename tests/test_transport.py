"""Transport-layer tests: retry policy, device logging, fake/real interface sync.

Nothing here opens a socket. The retry policy is exercised through injected
callables, the logger through a redirected log path, and the HEOS read loop
through a scripted stand-in that replays bytes and connects to nothing.
"""

from __future__ import annotations

import inspect
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Self

from fakes import FakeHeosTransport, FakeTelnetTransport

from denon_rcd_n12 import transport as transport_module
from denon_rcd_n12.transport import (
    DeviceError,
    HeosTransport,
    SupportsHeos,
    SupportsTelnet,
    TelnetTransport,
    _parse_flat_yaml,
    transports_from_config,
)


class InterfaceSyncTests(unittest.TestCase):
    """The fake and the real transport must expose the same device interface."""

    def test_both_satisfy_the_protocol(self) -> None:
        self.assertIsInstance(TelnetTransport(host="10.0.0.1"), SupportsTelnet)
        self.assertIsInstance(FakeTelnetTransport(), SupportsTelnet)
        self.assertIsInstance(HeosTransport(host="10.0.0.1"), SupportsHeos)
        self.assertIsInstance(FakeHeosTransport(), SupportsHeos)

    @staticmethod
    def _shape(func: object) -> tuple[Any, ...]:
        """Reduce a signature to the parts an implementation must match.

        Parameter defaults are excluded: the protocol spells them ``...`` by
        convention while implementations carry real values. What must agree is
        the parameter names, kinds, annotations, and whether each is optional.

        Args:
            func: The function or method to describe.

        Returns:
            A comparable tuple describing the signature.
        """
        signature = inspect.signature(func)
        return (
            tuple(
                (p.name, p.kind, p.annotation, p.default is not inspect.Parameter.empty)
                for p in signature.parameters.values()
            ),
            signature.return_annotation,
        )

    def test_signatures_match_the_protocol(self) -> None:
        # A runtime_checkable Protocol only checks that names exist, so compare
        # the signature shapes -- that is what keeps the fake honest.
        pairs = (
            (SupportsTelnet, "send", (TelnetTransport, FakeTelnetTransport)),
            (SupportsHeos, "query", (HeosTransport, FakeHeosTransport)),
        )
        for protocol, name, impls in pairs:
            expected = self._shape(getattr(protocol, name))
            for impl in impls:
                with self.subTest(method=name, impl=impl.__name__):
                    self.assertEqual(self._shape(getattr(impl, name)), expected)


class TempLogMixin(unittest.TestCase):
    """Redirects the device log so no test ever writes to ``logs/device.log``."""

    def setUp(self) -> None:
        """Point :data:`transport.LOG_PATH` at a throwaway file."""
        super().setUp()
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = Path(tmp.name) / "device.log"
        original = transport_module.LOG_PATH
        transport_module.LOG_PATH = self.log
        self.addCleanup(self._restore, original)

    def _restore(self, original: Path) -> None:
        """Point the logger back at the real path and drop the temp handler.

        Args:
            original: The log path in force before the test.
        """
        transport_module.LOG_PATH = original
        for handler in list(transport_module._logger.handlers):
            transport_module._logger.removeHandler(handler)
            handler.close()
        transport_module._handler_path = None


class RetryTests(TempLogMixin):
    """`_with_retry` gives transient failures another go and then gives up."""

    def setUp(self) -> None:
        super().setUp()
        self.transport = TelnetTransport(host="10.0.0.1", retries=2, retry_backoff=0.0)

    def test_success_on_first_attempt_runs_once(self) -> None:
        calls: list[int] = []

        def attempt() -> str:
            calls.append(1)
            return "ok"

        self.assertEqual(self.transport._with_retry(attempt, "probe"), "ok")
        self.assertEqual(len(calls), 1)

    def test_transient_failure_is_retried_then_succeeds(self) -> None:
        calls: list[int] = []

        def attempt() -> str:
            calls.append(1)
            if len(calls) < 2:
                raise DeviceError("connection reset")
            return "ok"

        self.assertEqual(self.transport._with_retry(attempt, "probe"), "ok")
        self.assertEqual(len(calls), 2)

    def test_persistent_failure_exhausts_attempts_and_raises(self) -> None:
        calls: list[int] = []

        def attempt() -> str:
            calls.append(1)
            raise DeviceError("unreachable")

        with self.assertRaises(DeviceError):
            self.transport._with_retry(attempt, "probe")
        self.assertEqual(len(calls), 3)  # first attempt plus two retries

    def test_retries_can_be_disabled(self) -> None:
        transport = TelnetTransport(host="10.0.0.1", retries=0)
        calls: list[int] = []

        def attempt() -> str:
            calls.append(1)
            raise DeviceError("unreachable")

        with self.assertRaises(DeviceError):
            transport._with_retry(attempt, "probe")
        self.assertEqual(len(calls), 1)


class LoggingTests(TempLogMixin):
    """Commands, responses and give-ups all land in the device log."""

    def test_log_file_is_created_on_first_write(self) -> None:
        self.assertFalse(self.log.exists())
        transport_module._log("->", "AVR PW?")
        self.assertTrue(self.log.exists())

    def test_command_and_response_are_recorded(self) -> None:
        transport_module._log("->", "AVR PW?")
        transport_module._log("<-", "AVR ['PWON']")
        contents = self.log.read_text(encoding="utf-8")
        self.assertIn("-> AVR PW?", contents)
        self.assertIn("<- AVR ['PWON']", contents)

    def test_retry_and_give_up_are_recorded(self) -> None:
        transport = TelnetTransport(host="10.0.0.1", retries=1, retry_backoff=0.0)

        def attempt() -> str:
            raise DeviceError("unreachable")

        with self.assertRaises(DeviceError):
            transport._with_retry(attempt, "AVR PW?")
        contents = self.log.read_text(encoding="utf-8")
        self.assertIn("retry 1/1", contents)
        self.assertIn("gave up after 2 attempts", contents)


class PacingTests(TempLogMixin):
    """Pacing is device-wide, not per protocol."""

    def test_the_two_transports_share_one_lock_and_clock(self) -> None:
        # The receiver is one device: a HEOS command must not slip in
        # immediately after an AVR one just because they use different ports.
        telnet = TelnetTransport(host="10.0.0.1")
        heos = HeosTransport(host="10.0.0.1")
        self.assertIs(
            type(telnet)._lock,
            type(heos)._lock,
        )

    def test_second_transaction_waits_out_the_gap(self) -> None:
        telnet = TelnetTransport(host="10.0.0.1", min_gap=0.25)
        heos = HeosTransport(host="10.0.0.1", min_gap=0.25)
        with telnet._paced():
            pass
        start = time.monotonic()
        with heos._paced():
            pass
        self.assertGreaterEqual(time.monotonic() - start, 0.2)


class ScriptedSocket:
    """A socket that replays prepared bytes. Connects to nothing.

    Enough of the interface for :meth:`HeosTransport._query_once`: the context
    manager, a discarded ``sendall``, and ``recv`` handing back one prepared
    chunk at a time before behaving like a peer that has gone quiet.
    """

    def __init__(self, chunks: list[bytes]) -> None:
        """Prepare the chunks ``recv`` will return, in order.

        Args:
            chunks: Byte strings to hand out, one per ``recv`` call.
        """
        self.chunks = list(chunks)
        self.sent: list[bytes] = []

    def __enter__(self) -> Self:
        """Enter the context, as a real socket does."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Leave the context; there is nothing to close."""

    def settimeout(self, timeout: float) -> None:
        """Accept and ignore a timeout.

        Args:
            timeout: Ignored.
        """

    def sendall(self, data: bytes) -> None:
        """Record what was written.

        Args:
            data: The bytes the transport sent.
        """
        self.sent.append(data)

    def recv(self, size: int) -> bytes:
        """Return the next prepared chunk.

        Args:
            size: Ignored.

        Returns:
            The next chunk, or raises once the script is exhausted.

        Raises:
            TimeoutError: When nothing is left, which is how a real socket
                reports a peer that has stopped talking.
        """
        if not self.chunks:
            raise TimeoutError
        return self.chunks.pop(0)


class DeferredReplyTests(TempLogMixin):
    """HEOS answers a slow command twice; only the second one is the answer."""

    def setUp(self) -> None:
        """Bind a transport and prepare to intercept its socket."""
        super().setUp()
        self.transport = HeosTransport(host="10.0.0.1", pid="1", min_gap=0.0, retries=0)

    def _run(self, chunks: list[bytes]) -> dict[str, Any]:
        """Run one query against a scripted socket.

        Args:
            chunks: The bytes the fake peer will return.

        Returns:
            The response object the transport settled on.
        """
        scripted = ScriptedSocket(chunks)
        original = transport_module.socket.create_connection
        transport_module.socket.create_connection = (  # type: ignore[assignment]
            lambda *a, **k: scripted
        )
        self.addCleanup(
            setattr, transport_module.socket, "create_connection", original
        )
        return self.transport.query("heos://browse/browse?sid=1028")

    def test_acknowledgement_is_not_mistaken_for_the_answer(self) -> None:
        # Measured 2026-09-11: browsing a source is acknowledged with an empty
        # payload and 'command under process', and the listing follows. Taking
        # the first message would report an empty favourites list.
        ack = (
            b'{"heos":{"command":"browse/browse","result":"success",'
            b'"message":"command under process&sid=1028"},"payload":[]}\r\n'
        )
        answer = (
            b'{"heos":{"command":"browse/browse","result":"success",'
            b'"message":"sid=1028&returned=1&count=1"},'
            b'"payload":[{"name":"1.FM Gaia","mid":"s214674"}]}\r\n'
        )
        reply = self._run([ack, answer])
        self.assertEqual(reply["payload"], [{"name": "1.FM Gaia", "mid": "s214674"}])

    def test_a_single_reply_is_still_returned_at_once(self) -> None:
        answer = (
            b'{"heos":{"command":"player/get_volume","result":"success",'
            b'"message":"pid=1&level=7"}}\r\n'
        )
        scripted = ScriptedSocket([answer])
        original = transport_module.socket.create_connection
        transport_module.socket.create_connection = (  # type: ignore[assignment]
            lambda *a, **k: scripted
        )
        self.addCleanup(
            setattr, transport_module.socket, "create_connection", original
        )
        reply = self.transport.query("heos://player/get_volume?pid=1")
        self.assertEqual(reply["heos"]["message"], "pid=1&level=7")

    def test_an_acknowledgement_with_no_answer_behind_it_fails(self) -> None:
        # Better a timeout than an empty listing presented as the truth.
        ack = (
            b'{"heos":{"command":"browse/browse","result":"success",'
            b'"message":"command under process&sid=1028"},"payload":[]}\r\n'
        )
        with self.assertRaises(DeviceError):
            self._run([ack])


class ConfigTests(unittest.TestCase):
    """Config loading never hardcodes an address."""

    def test_from_config_reads_host_and_ports(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "device.yaml"
            path.write_text(
                "device:\n  host: 10.1.2.3\n  heos_pid: 42\nports:\n  heos: 1255\n  avr: 23\n",
                encoding="utf-8",
            )
            telnet, heos = transports_from_config(path)
        self.assertEqual(telnet.host, "10.1.2.3")
        self.assertEqual(telnet.port, 23)
        self.assertEqual(heos.host, "10.1.2.3")
        self.assertEqual(heos.port, 1255)
        self.assertEqual(heos.pid, "42")

    def test_flat_yaml_ignores_comments(self) -> None:
        cfg = _parse_flat_yaml("device:\n  host: 10.0.0.1  # the receiver\n")
        self.assertEqual(cfg["device"]["host"], "10.0.0.1")


if __name__ == "__main__":
    unittest.main()
