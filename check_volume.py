#!/usr/bin/env python3
"""Read playback volume (and mute) from a Denon RCD-N12 over HEOS CLI.

HEOS CLI: TCP 1255, CRLF-terminated commands, single-line JSON responses.
`level` is an absolute 0-100 scale, NOT dB, and NOT the same scale as the
AVR-protocol `MV` value on port 23.

Usage:
    python heos_volume.py
    python heos_volume.py --host 192.168.3.40 --pid 370278583
"""

from __future__ import annotations

import argparse
import json
import re
import socket
from urllib.parse import parse_qs

HOST = "192.168.3.40"
PID = "370278583"
PORT = 1255
TIMEOUT = 1.0


class HeosError(RuntimeError):
    pass


def heos_query(command: str, host: str = HOST, port: int = PORT,
               timeout: float = TIMEOUT) -> dict:
    """Send one HEOS command, return the matching response object.

    Opens and closes a socket per call. Fine for one-shot queries; if you start
    polling, hold a single socket behind a lock and register for change events
    instead -- repeated connect/close exhausts the connection ceiling.
    """
    want = command.split("heos://", 1)[-1].split("?", 1)[0]

    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(f"{command}\r\n".encode("ascii"))

        buf = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                raise HeosError(f"no response to {want} within {timeout}s") from None
            if not chunk:
                raise HeosError("connection closed by device")
            buf += chunk

            while b"\r\n" in buf:
                line, buf = buf.split(b"\r\n", 1)
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue  # tolerate anything unparseable on the wire
                heos = obj.get("heos", {})
                # Ignore async change events and unrelated replies.
                if heos.get("command") != want:
                    continue
                if heos.get("result") != "success":
                    raise HeosError(f"{want} failed: {heos.get('message')}")
                return obj


def _msg(obj: dict) -> dict[str, str]:
    """Parse the &-delimited `message` field into a dict."""
    return {k: v[0] for k, v in parse_qs(obj["heos"].get("message", "")).items()}


def get_volume(host: str = HOST, pid: str = PID) -> int:
    obj = heos_query(f"heos://player/get_volume?pid={pid}", host=host)
    level = _msg(obj).get("level")
    if level is None:
        raise HeosError(f"no level in response: {obj['heos'].get('message')!r}")
    return int(level)


def get_mute(host: str = HOST, pid: str = PID) -> bool:
    obj = heos_query(f"heos://player/get_mute?pid={pid}", host=host)
    return _msg(obj).get("state") == "on"


def main() -> int:
    ap = argparse.ArgumentParser(description="Read RCD-N12 playback volume")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--pid", default=PID)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    try:
        volume = get_volume(args.host, args.pid)
        muted = get_mute(args.host, args.pid)
    except (OSError, HeosError) as exc:
        print(f"error: {exc}")
        return 1

    if args.json:
        print(json.dumps({"volume": volume, "mute": muted}))
    else:
        print(f"volume: {volume}/100{'  (MUTED)' if muted else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())