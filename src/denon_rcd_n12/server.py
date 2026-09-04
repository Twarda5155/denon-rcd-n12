"""Localhost control server: one page, a small JSON API, no outbound traffic.

Implements the power and volume slice of the API in
``docs/decisions/2026-08-30-local-control-server.md`` on the stdlib
``http.server``, so it runs on a bare interpreter with nothing installed.

The socket is bound to the loopback address and every asset the page needs is
inlined, so nothing is fetched from or sent to anything but the receiver on the
local network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .client import DenonClient
from .transport import DeviceError

HOST = "127.0.0.1"
PORT = 8712
INDEX = Path(__file__).resolve().parent / "static" / "index.html"


def _handler_class(client: DenonClient) -> type[BaseHTTPRequestHandler]:
    """Build a request handler bound to one client.

    Args:
        client: The device client the API routes delegate to.

    Returns:
        A handler class ready to hand to :class:`ThreadingHTTPServer`.
    """

    class Handler(BaseHTTPRequestHandler):
        """Serves the single page and the power/volume API."""

        protocol_version = "HTTP/1.1"
        server_version = "denon-rcd-n12"

        def log_message(self, fmt: str, *args: Any) -> None:
            """Log one line per request without the default timestamp noise.

            Args:
                fmt: printf-style format string.
                *args: Values for ``fmt``.
            """
            print(f"  {self.address_string()} {fmt % args}")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            """Write a complete response.

            Args:
                status: HTTP status code.
                body: Response body.
                content_type: Value for the ``Content-Type`` header.
            """
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: dict[str, Any], status: int = 200) -> None:
            """Write a JSON response.

            Args:
                payload: Object to serialise.
                status: HTTP status code.
            """
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

        def _run(self, action: Callable[[], dict[str, Any]]) -> None:
            """Run a device action, converting failures into a JSON error.

            Args:
                action: Callable returning the success payload.
            """
            try:
                self._json({"ok": True, **action()})
            except DeviceError as exc:
                self._json({"ok": False, "error": str(exc)}, status=502)
            except (ValueError, KeyError) as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)

        def do_GET(self) -> None:
            """Route GET requests: the page, or a read-only device query."""
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/power":
                self._run(lambda: {"power": client.get_power()})
            elif path == "/api/volume":
                self._run(client.get_volume)
            else:
                self._json({"ok": False, "error": "not found"}, status=404)

        def do_POST(self) -> None:
            """Route POST requests: the only write is a power change."""
            path = urlparse(self.path).path
            if path != "/api/power":
                self._json({"ok": False, "error": "not found"}, status=404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            state = (form.get("state") or ["toggle"])[0]
            if state == "toggle":
                self._run(lambda: {"power": client.toggle_power()})
            else:
                self._run(lambda: {"power": client.set_power(state)})

    return Handler


def serve(host: str = HOST, port: int = PORT, client: DenonClient | None = None) -> None:
    """Run the control server until interrupted.

    Args:
        host: Address to bind. Loopback by default, deliberately.
        port: TCP port to bind.
        client: Device client to use; built from ``config/device.yaml`` if omitted.
    """
    client = client or DenonClient.from_config()
    httpd = ThreadingHTTPServer((host, port), _handler_class(client))
    print(f"denon-rcd-n12 control -> http://{host}:{port}")
    print(f"receiver {client.host}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
