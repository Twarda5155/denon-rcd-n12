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


def _level(raw: str) -> int:
    """Parse a ``level`` form value into an integer.

    Args:
        raw: The raw form value.

    Returns:
        The level as an integer.

    Raises:
        ValueError: If ``raw`` is missing or not a whole number, which the
            handler reports as a 400 rather than a device failure.
    """
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"level must be a whole number, got {raw!r}") from None


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

        def _unframed(self, why: str) -> None:
            """Refuse a body whose length cannot be determined.

            Such a body cannot be drained, so the connection cannot be reused
            without the leftover bytes being read as the next request line.
            Closing it is the only safe answer.

            Args:
                why: Explanation returned to the caller.
            """
            self.close_connection = True
            self._json({"ok": False, "error": why}, status=411)

        def _form(self) -> dict[str, list[str]] | None:
            """Read and decode the request body, always draining it.

            The body must be consumed even when the route ignores it: on a
            keep-alive connection anything left behind is parsed as the next
            request line, and the client then gets an HTML error page where it
            asked for JSON.

            Returns:
                The form parameters as :func:`parse_qs` returns them, or
                ``None`` if the body could not be framed, in which case the
                response has already been sent.
            """
            if self.headers.get("Transfer-Encoding"):
                self._unframed("chunked request bodies are not supported")
                return None
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._unframed("malformed Content-Length")
                return None
            if length < 0:
                self._unframed("malformed Content-Length")
                return None
            return parse_qs(self.rfile.read(length).decode("utf-8"))

        def do_POST(self) -> None:
            """Route POST requests: a power change or a volume change."""
            path = urlparse(self.path).path
            form = self._form()  # drained first, whatever the path turns out to be
            if form is None:
                return
            if path == "/api/power":
                self._power(form)
            elif path == "/api/volume":
                self._volume(form)
            else:
                self._json({"ok": False, "error": "not found"}, status=404)

        def _power(self, form: dict[str, list[str]]) -> None:
            """Apply a power write.

            Args:
                form: Decoded form parameters; ``state`` defaults to ``toggle``.
            """
            state = (form.get("state") or ["toggle"])[0]
            if state == "toggle":
                self._run(lambda: {"power": client.toggle_power()})
            else:
                self._run(lambda: {"power": client.set_power(state)})

        def _volume(self, form: dict[str, list[str]]) -> None:
            """Apply a volume write.

            The body must carry ``level``; there is no default, because
            guessing a volume for a caller that omitted it is not safe.

            Args:
                form: Decoded form parameters carrying ``level``.
            """
            raw = (form.get("level") or [""])[0]
            self._run(lambda: client.set_volume(_level(raw)))

    return Handler


class _ControlServer(ThreadingHTTPServer):
    """Threading server that refuses to share its port.

    :class:`~http.server.HTTPServer` sets ``allow_reuse_address``, which on
    Windows lets a *second* process bind a port that is already listening
    rather than failing. Connections are then split between the two servers
    unpredictably -- a stale process keeps answering while the operator
    believes they restarted it -- and both would hold the receiver's single
    control connection at once. Refusing the second bind is what keeps one
    process in charge of the device.
    """

    allow_reuse_address = False


def serve(host: str = HOST, port: int = PORT, client: DenonClient | None = None) -> int:
    """Run the control server until interrupted.

    Args:
        host: Address to bind. Loopback by default, deliberately.
        port: TCP port to bind.
        client: Device client to use; built from ``config/device.yaml`` if omitted.

    Returns:
        Process exit status: ``0`` after a clean stop, ``1`` if the port was
        already in use.
    """
    client = client or DenonClient.from_config()
    try:
        httpd = _ControlServer((host, port), _handler_class(client))
    except OSError as exc:
        print(f"cannot bind {host}:{port}: {exc}")
        print("another control server is already running there; stop it first")
        return 1
    print(f"denon-rcd-n12 control -> http://{host}:{port}")
    print(f"receiver {client.host}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    serve()
