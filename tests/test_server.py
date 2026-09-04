"""HTTP surface tests: a real server on loopback, a fake receiver behind it."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any, ClassVar

from fakes import FakeHeosTransport, FakeTelnetTransport

from denon_rcd_n12 import client as client_module
from denon_rcd_n12.client import DenonClient
from denon_rcd_n12.server import _handler_class


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
            power=str(kwargs.pop("power", "on")), fail=fail
        )
        self.heos = FakeHeosTransport(
            volume=int(kwargs.pop("volume", 20)),
            mute=bool(kwargs.pop("mute", False)),
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


if __name__ == "__main__":
    unittest.main()
