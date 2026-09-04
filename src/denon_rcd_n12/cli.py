"""Command-line entry point.

``serve`` starts the local one-page control app; ``power`` and ``volume`` are
the same queries without a browser, useful for checking the device path when
the page misbehaves.
"""

from __future__ import annotations

import argparse

from .client import DenonClient
from .server import HOST, PORT, serve
from .transport import DeviceError


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch.

    Args:
        argv: Argument vector; ``sys.argv[1:]`` when omitted.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(prog="denon", description="Control a Denon RCD-N12")
    sub = parser.add_subparsers(dest="command", required=True)

    web = sub.add_parser("serve", help="run the local control page")
    web.add_argument("--host", default=HOST, help="bind address (default: loopback)")
    web.add_argument("--port", type=int, default=PORT)

    power = sub.add_parser("power", help="read or set power state")
    power.add_argument("state", nargs="?", choices=["on", "standby", "toggle"])

    sub.add_parser("volume", help="read playback volume and mute")

    args = parser.parse_args(argv)

    if args.command == "serve":
        serve(host=args.host, port=args.port)
        return 0

    try:
        client = DenonClient.from_config()
        if args.command == "power":
            if args.state == "toggle":
                print(client.toggle_power())
            elif args.state:
                print(client.set_power(args.state))
            else:
                print(client.get_power())
        else:
            state = client.get_volume()
            print(f"{state['volume']}/100{'  muted' if state['mute'] else ''}")
    except (DeviceError, OSError) as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
