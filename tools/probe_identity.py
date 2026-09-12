# tools/probe_identity.py
"""Ask a receiver who it is, and print a `config/device.yaml` ready to paste.

`device.example.yaml` says the values come "from player/get_players", which is
true of some of them and misleading about the rest. This asks the device and
fills in what it actually answers, so nobody has to work out the mapping twice.

Takes the address as an argument because the configuration file is what it is
meant to produce -- there is a chicken and egg here, and the egg is the IP.
Find it in the router's DHCP table or at the unit under Settings > Network.

    python tools/probe_identity.py 192.168.3.40

Reads only. Opens its own HEOS connection through `transport.py`, so the pacing
and retry policy apply as they do everywhere else.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from denon_rcd_n12.transport import AVR_PORT, HEOS_PORT, DeviceError, HeosTransport

#: Keys `transport.py` actually reads. Everything else in the file documents
#: the unit for humans and can be wrong without breaking anything -- except
#: `heos_pid`, whose absence sends every HEOS command with an empty pid.
REQUIRED = ("host", "heos_pid")


def pick(players: list[dict], host: str) -> dict | None:
    """Choose the player that answers at the address we connected to.

    `player/get_players` lists every HEOS player on the network, not just the
    one whose CLI answered, so in a house with more than one the reply needs
    disambiguating.

    Args:
        players: The payload of ``player/get_players``.
        host: The address the connection was made to.

    Returns:
        The matching player, the only player if there is just one, or ``None``
        when the choice is ambiguous.
    """
    if len(players) == 1:
        return players[0]
    for player in players:
        if str(player.get("ip", "")) == host:
            return player
    return None


def emit(player: dict, host: str, heos_port: int, avr_port: int) -> None:
    """Print the configuration block for one player.

    Args:
        player: A single entry from ``player/get_players``.
        host: The address to record.
        heos_port: HEOS CLI port.
        avr_port: AVR control port.
    """
    reported = player.get("model", "")
    print("device:")
    print(f"  host: {host}")
    print(f"  heos_pid: {player.get('pid', '')}")
    print(f"  serial: {player.get('serial', '')}")
    print(f"  model: {reported}")
    print(f"  heos_firmware: {player.get('version', '')}")
    print("ports:")
    print(f"  heos: {heos_port}")
    print(f"  avr: {avr_port}")
    print()
    print("# Only host and heos_pid are read by the code. serial, model and")
    print("# heos_firmware document the unit and can be edited freely.")
    if reported and "RCD" not in reported.upper():
        print(f"# The unit calls itself {reported!r}, which is the family name.")
        print("# Substitute the marketing name (RCD-N12) if you prefer it here.")


def main(argv: list[str] | None = None) -> int:
    """Query one receiver and print its configuration block.

    Args:
        argv: Argument vector; ``sys.argv[1:]`` when omitted.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(
        prog="probe_identity",
        description="Print a config/device.yaml for the receiver at HOST",
    )
    parser.add_argument("host", help="receiver IP, from the router or the unit's menu")
    parser.add_argument("--heos-port", type=int, default=HEOS_PORT)
    parser.add_argument("--avr-port", type=int, default=AVR_PORT)
    args = parser.parse_args(argv)

    try:
        reply = HeosTransport(args.host, port=args.heos_port).query(
            "heos://player/get_players"
        )
    except (DeviceError, OSError) as exc:
        print(f"cannot reach a HEOS player at {args.host}:{args.heos_port}: {exc}")
        print("check the address, and that the unit is on the network at all")
        return 1

    players = reply.get("payload") or []
    if not players:
        print("the unit answered but listed no players, which should not happen")
        return 1

    chosen = pick(players, args.host)
    if chosen is None:
        print(f"{len(players)} players answered and none reports {args.host} as its ip.")
        print("Pick one and take its pid and serial by hand:\n")
        for player in players:
            print(f"  {player.get('ip', '?'):<16} pid={player.get('pid')} "
                  f"{player.get('name', '')} ({player.get('model', '')})")
        return 1

    emit(chosen, args.host, args.heos_port, args.avr_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
