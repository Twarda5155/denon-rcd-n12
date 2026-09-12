"""Command-line entry point.

``serve`` starts the local one-page control app; ``status``, ``power``,
``volume``, ``mute``, ``source``, ``playback`` and ``sleep`` are the same
queries and writes without a browser, useful for checking the device path when
the page misbehaves.
"""

from __future__ import annotations

import argparse

from .client import (
    SELECTABLE_SOURCES,
    SETTABLE_PLAY_STATES,
    SLEEP_MAX,
    SLEEP_MIN,
    SOURCE_NET,
    SOURCE_SERVER,
    VOLUME_MAX,
    VOLUME_MIN,
    DenonClient,
)
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

    volume = sub.add_parser("volume", help="read or set playback volume")
    volume.add_argument(
        "level", nargs="?", type=int, help=f"HEOS level {VOLUME_MIN}-{VOLUME_MAX}"
    )

    mute = sub.add_parser("mute", help="read or set mute")
    mute.add_argument("state", nargs="?", choices=["on", "off", "toggle"])

    source = sub.add_parser("source", help="read or set the input source")
    source.add_argument(
        "name",
        nargs="?",
        choices=sorted(SELECTABLE_SOURCES),
        help=(
            f"input to select; reading can also report {SOURCE_NET!r} and "
            f"{SOURCE_SERVER!r}, the network input carrying a streaming service "
            "or a server on the LAN. Neither can be selected: this unit ignores "
            "SINET as a write"
        ),
    )

    playback = sub.add_parser(
        "playback", help="read the transport state, or drive it"
    )
    playback.add_argument("state", nargs="?", choices=sorted(SETTABLE_PLAY_STATES))

    sleep = sub.add_parser("sleep", help="read or set the sleep timer")
    sleep.add_argument(
        "minutes",
        nargs="?",
        type=int,
        help=f"{SLEEP_MIN}-{SLEEP_MAX} to arm it, 0 to cancel",
    )

    sub.add_parser("status", help="read everything in one go")

    args = parser.parse_args(argv)

    if args.command == "serve":
        return serve(host=args.host, port=args.port)

    try:
        client = DenonClient.from_config()
        if args.command == "power":
            if args.state == "toggle":
                print(client.toggle_power())
            elif args.state:
                print(client.set_power(args.state))
            else:
                print(client.get_power())
        elif args.command == "volume":
            if args.level is None:
                state = client.get_volume()
            else:
                state = client.set_volume(args.level)
            print(f"{state['volume']}/100{'  muted' if state['mute'] else ''}")
        elif args.command == "mute":
            if args.state is None:
                state = client.get_volume()
            elif args.state == "toggle":
                state = client.toggle_mute()
            else:
                state = client.set_mute(args.state == "on")
            print("muted" if state["mute"] else "not muted")
        elif args.command == "source":
            if args.name is None:
                print(client.get_source())
            else:
                print(client.set_source(args.name))
        elif args.command == "sleep":
            minutes = (
                client.get_sleep() if args.minutes is None else client.set_sleep(args.minutes)
            )
            print(f"{minutes} min" if minutes else "off")
        elif args.command == "status":
            state = client.get_status()
            for key in sorted(state):
                print(f"{key:<12} {state[key]}")
        else:
            playing = (
                client.get_playback() if args.state is None else client.set_play_state(args.state)
            )
            # Title and artist only: the remaining fields repeat them often
            # enough that a one-line summary is clearer without them.
            detail = " - ".join(p for p in (playing["title"], playing["artist"]) if p)
            print(f"{playing['state']}  {detail or 'no metadata'}")
    except (DeviceError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
