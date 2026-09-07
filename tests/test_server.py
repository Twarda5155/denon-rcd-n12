"""HTTP surface tests: a real server on loopback, a fake receiver behind it."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any, ClassVar

from fakes import FakeHeosTransport, FakeTelnetTransport

from denon_rcd_n12 import client as client_module
from denon_rcd_n12.client import DenonClient
from denon_rcd_n12.server import _ControlServer, _handler_class, serve


class ServerTestCase(unittest.TestCase):
    """Boots the control server on an ephemeral loopback port per test."""

    transport_kwargs: ClassVar[dict[str, Any]] = {}

    def setUp(self) -> None:
        """Start the server and collapse the power settle delays."""
        for name in ("WAKE_SETTLE_S", "SLEEP_SETTLE_S"):
            original = getattr(client_module, name)
            setattr(client_module, name, 0.0)
            self.addCleanup(setattr, client_module, name, original)

        kwargs = dict(self.transport_kwargs)
        fail = bool(kwargs.pop("fail", False))
        self.telnet = FakeTelnetTransport(
            power=str(kwargs.pop("power", "on")),
            source=str(kwargs.pop("source", "SINET")),
            fail=fail,
        )
        self.heos = FakeHeosTransport(
            volume=int(kwargs.pop("volume", 20)),
            mute=bool(kwargs.pop("mute", False)),
            now_playing_sid=kwargs.pop("now_playing_sid", 1024),
            play_state=str(kwargs.pop("play_state", "play")),
            fail=fail,
        )
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), _handler_class(DenonClient(self.telnet, self.heos))
        )
        self.httpd.RequestHandlerClass.log_message = lambda *a, **k: None  # type: ignore[method-assign]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def get(self, path: str) -> tuple[int, Any]:
        """Issue a GET.

        Args:
            path: Path to request, relative to the server root.

        Returns:
            The status code and the decoded body.
        """
        return self._request(urllib.request.Request(self.base + path))

    def post(self, path: str, body: str) -> tuple[int, Any]:
        """Issue a form-encoded POST.

        Args:
            path: Path to request, relative to the server root.
            body: URL-encoded request body.

        Returns:
            The status code and the decoded body.
        """
        request = urllib.request.Request(
            self.base + path,
            data=body.encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return self._request(request)

    @staticmethod
    def _request(request: urllib.request.Request) -> tuple[int, Any]:
        """Perform a request, treating HTTP errors as ordinary responses.

        Args:
            request: The prepared request.

        Returns:
            The status code and the body, decoded as JSON when possible.
        """
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            with exc:
                status, raw = exc.code, exc.read()
        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, raw.decode("utf-8")


class PageTests(ServerTestCase):
    """The single page itself."""

    def test_index_is_served(self) -> None:
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("denon rcd-n12", body)

    def test_page_references_no_external_origin(self) -> None:
        # Local-only by construction: nothing is fetched from off the machine.
        _, body = self.get("/")
        for marker in ("http://", "https://", "//cdn"):
            self.assertNotIn(marker, body.replace('<html lang="en">', ""))

    def test_unknown_path_is_404(self) -> None:
        status, body = self.get("/nope")
        self.assertEqual(status, 404)
        self.assertFalse(body["ok"])


class PowerRouteTests(ServerTestCase):
    """``/api/power``."""

    transport_kwargs: ClassVar[dict[str, Any]] = {"power": "standby"}

    def test_get_power(self) -> None:
        status, body = self.get("/api/power")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True, "power": "standby"})

    def test_toggle_power(self) -> None:
        status, body = self.post("/api/power", "state=toggle")
        self.assertEqual(status, 200)
        self.assertEqual(body["power"], "on")
        self.assertIn("PWON", self.telnet.commands)

    def test_explicit_state(self) -> None:
        _, body = self.post("/api/power", "state=on")
        self.assertEqual(body["power"], "on")

    def test_bad_state_is_400(self) -> None:
        status, body = self.post("/api/power", "state=explode")
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])

    def test_post_to_unknown_path_is_404(self) -> None:
        status, _ = self.post("/api/nope", "")
        self.assertEqual(status, 404)


class VolumeRouteTests(ServerTestCase):
    """``/api/volume``."""

    transport_kwargs: ClassVar[dict[str, Any]] = {"volume": 42, "mute": True}

    def test_get_volume(self) -> None:
        status, body = self.get("/api/volume")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True, "volume": 42, "mute": True})

    def test_set_volume(self) -> None:
        status, body = self.post("/api/volume", "level=63")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True, "volume": 63, "mute": True})
        self.assertEqual(self.heos.volume, 63)

    def test_out_of_range_level_is_400(self) -> None:
        status, body = self.post("/api/volume", "level=101")
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])
        self.assertEqual(self.heos.volume, 42)

    def test_non_numeric_level_is_400(self) -> None:
        status, body = self.post("/api/volume", "level=loud")
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])

    def test_missing_level_is_400(self) -> None:
        # No default: a body without a level is a caller bug, not a request
        # to pick a volume on their behalf.
        status, body = self.post("/api/volume", "")
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])
        self.assertEqual(self.heos.volume, 42)


class SourceRouteTests(ServerTestCase):
    """``/api/source``, read-only while ``SI`` writes are unverified (Q9)."""

    transport_kwargs: ClassVar[dict[str, Any]] = {"source": "SICD"}

    def test_get_source(self) -> None:
        status, body = self.get("/api/source")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True, "source": "cd"})

    def test_post_is_404_and_writes_nothing(self) -> None:
        # The route is deliberately absent rather than wired to set_source:
        # no SI write has ever reached this unit.
        status, _ = self.post("/api/source", "name=phono")
        self.assertEqual(status, 404)
        self.assertEqual(self.telnet.source, "SICD")


class NetworkSourceRouteTests(ServerTestCase):
    """``/api/source`` on the one input that needs both protocols to name it."""

    transport_kwargs: ClassVar[dict[str, Any]] = {
        "source": "SINET",
        "now_playing_sid": 1024,
    }

    def test_local_media_reads_as_server(self) -> None:
        _, body = self.get("/api/source")
        self.assertEqual(body["source"], "server")


class PlaybackRouteTests(ServerTestCase):
    """``/api/playback``."""

    transport_kwargs: ClassVar[dict[str, Any]] = {
        "now_playing_sid": 3,
        "play_state": "pause",
    }

    def test_get_playback(self) -> None:
        status, body = self.get("/api/playback")
        self.assertEqual(status, 200)
        self.assertEqual(
            body,
            {
                "ok": True,
                "state": "pause",
                "title": "Deutschland national",
                "artist": "Klassik Radio",
                "album": None,
                "station": "Klassik Radio",
                "media_type": "station",
            },
        )

    def test_post_is_404(self) -> None:
        status, _ = self.post("/api/playback", "state=play")
        self.assertEqual(status, 404)


class KeepAliveFramingTests(ServerTestCase):
    """A request body left unread is read as the next request line.

    The page reuses one connection, so a desync here reaches the user as an
    HTML error page parsed as JSON -- reported one request later than the
    request that actually caused it.
    """

    transport_kwargs: ClassVar[dict[str, Any]] = {"volume": 20}

    @staticmethod
    def request_bytes(start_line: str, *headers: str, body: str = "") -> bytes:
        """Build one raw HTTP/1.1 request.

        Args:
            start_line: The request line, without the protocol version.
            *headers: Header lines to send after ``Host``.
            body: Body to append after the header terminator.

        Returns:
            The encoded request.
        """
        head = "\r\n".join([f"{start_line} HTTP/1.1", "Host: x", *headers])
        return (head + "\r\n\r\n" + body).encode("ascii")

    def exchange(self, payload: bytes) -> list[bytes]:
        """Send raw bytes on one connection and split out the responses.

        Args:
            payload: Raw request bytes, possibly several requests back to back.

        Returns:
            One entry per response received, each starting at its status line.
        """
        sock = socket.create_connection(
            ("127.0.0.1", self.httpd.server_address[1]), timeout=5
        )
        sock.settimeout(2.0)
        data = b""
        try:
            sock.sendall(payload)
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        except TimeoutError:
            pass
        finally:
            sock.close()
        return [b"HTTP/1." + part for part in data.split(b"HTTP/1.")[1:]]

    @staticmethod
    def body_of(response: bytes) -> bytes:
        """Return the body of one raw response.

        Args:
            response: A raw response including its headers.

        Returns:
            The bytes after the header terminator.
        """
        _, _, body = response.partition(b"\r\n\r\n")
        return body

    def test_post_to_unknown_path_does_not_desync_the_connection(self) -> None:
        # The 404 route ignores the body, but it must still be drained.
        responses = self.exchange(
            self.request_bytes(
                "POST /api/nope",
                "Content-Type: application/x-www-form-urlencoded",
                "Content-Length: 8",
                body="level=55",
            )
            + self.request_bytes("GET /api/volume")
        )
        self.assertEqual(len(responses), 2, f"expected two replies, got {responses!r}")
        self.assertIn(b"404", responses[0].partition(b"\r\n")[0])
        self.assertIn(b"200", responses[1].partition(b"\r\n")[0])
        self.assertEqual(json.loads(self.body_of(responses[1]))["volume"], 20)

    def test_chunked_body_is_refused_without_desync(self) -> None:
        # A chunked body cannot be framed from Content-Length, so it cannot be
        # drained; the reply must still be JSON, and the connection is closed.
        responses = self.exchange(
            self.request_bytes(
                "POST /api/volume",
                "Content-Type: application/x-www-form-urlencoded",
                "Transfer-Encoding: chunked",
                body="8\r\nlevel=55\r\n0\r\n\r\n",
            )
        )
        self.assertTrue(responses, "no reply at all")
        self.assertIn(b"411", responses[0].partition(b"\r\n")[0])
        self.assertFalse(json.loads(self.body_of(responses[0]))["ok"])

    def test_no_reply_is_ever_html(self) -> None:
        # The reported symptom: JSON.parse choking on "<!DOCTYPE HTML>".
        payloads = (
            self.request_bytes(
                "POST /api/nope", "Content-Length: 8", body="level=55"
            )
            + self.request_bytes("GET /api/volume"),
            self.request_bytes("POST /api/volume", "Content-Length: bogus"),
            self.request_bytes(
                "POST /api/volume", "Transfer-Encoding: chunked", body="0\r\n\r\n"
            ),
        )
        for payload in payloads:
            with self.subTest(payload=payload[:20]):
                for response in self.exchange(payload):
                    self.assertNotIn(b"<!DOCTYPE", response)

    def test_reported_sequence_over_one_connection(self) -> None:
        # check volume, set volume, check volume -- as reported.
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.httpd.server_address[1], timeout=5
        )
        self.addCleanup(conn.close)
        levels = []
        for method, body in (("GET", None), ("POST", "level=55"), ("GET", None)):
            headers = (
                {"Content-Type": "application/x-www-form-urlencoded"} if body else {}
            )
            conn.request(method, "/api/volume", body=body, headers=headers)
            response = conn.getresponse()
            payload = response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "application/json")
            levels.append(json.loads(payload)["volume"])
        self.assertEqual(levels, [20, 55, 55])


class ExclusiveBindTests(unittest.TestCase):
    """One port, one server.

    Windows lets a second process bind an address that is already listening
    when ``allow_reuse_address`` is set, so a stale server keeps answering
    some requests after an apparently successful restart.
    """

    @staticmethod
    def build_server(port: int) -> _ControlServer:
        """Start a control server over fakes.

        Args:
            port: TCP port to bind; ``0`` picks a free one.

        Returns:
            The bound server.
        """
        client = DenonClient(FakeTelnetTransport(), FakeHeosTransport())
        return _ControlServer(("127.0.0.1", port), _handler_class(client))

    def test_second_server_cannot_take_the_same_port(self) -> None:
        first = self.build_server(0)
        self.addCleanup(first.server_close)
        with self.assertRaises(OSError):
            self.build_server(first.server_address[1]).server_close()

    def test_port_is_free_again_after_close(self) -> None:
        first = self.build_server(0)
        port = first.server_address[1]
        first.server_close()
        second = self.build_server(port)  # must not raise
        second.server_close()

    def test_serve_reports_a_taken_port_instead_of_sharing_it(self) -> None:
        first = self.build_server(0)
        self.addCleanup(first.server_close)
        client = DenonClient(FakeTelnetTransport(), FakeHeosTransport())
        status = serve(host="127.0.0.1", port=first.server_address[1], client=client)
        self.assertEqual(status, 1)


class UnreachableDeviceTests(ServerTestCase):
    """A receiver that does not answer must surface as an error, not a hang."""

    transport_kwargs: ClassVar[dict[str, Any]] = {"fail": True}

    def test_power_reports_502(self) -> None:
        status, body = self.get("/api/power")
        self.assertEqual(status, 502)
        self.assertFalse(body["ok"])
        self.assertIn("unreachable", body["error"])

    def test_volume_reports_502(self) -> None:
        status, body = self.get("/api/volume")
        self.assertEqual(status, 502)
        self.assertFalse(body["ok"])

    def test_set_volume_reports_502(self) -> None:
        status, body = self.post("/api/volume", "level=30")
        self.assertEqual(status, 502)
        self.assertFalse(body["ok"])
        self.assertIn("unreachable", body["error"])

    def test_source_reports_502(self) -> None:
        status, body = self.get("/api/source")
        self.assertEqual(status, 502)
        self.assertFalse(body["ok"])

    def test_playback_reports_502(self) -> None:
        status, body = self.get("/api/playback")
        self.assertEqual(status, 502)
        self.assertFalse(body["ok"])


if __name__ == "__main__":
    unittest.main()
