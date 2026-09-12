# tools/probe_ports.py
"""Scan the receiver's control ports and record the power state they were seen in.

Open question 1 asks which ports answer powered on *and* in standby, so the
answer is two runs of this, one per state. The power state is read first and
printed with the results, because a scan without it records nothing useful.

Like `probe_device.py` this is a diagnostic that opens its own sockets rather
than going through `transport.py`: it is asking whether a port answers at all,
which is the one question the transport cannot pose.
"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from denon_rcd_n12.client import DenonClient
from denon_rcd_n12.transport import DeviceError, load_config

#: The ports open question 1 names, plus 443 for the TLS redirect some
#: 2023-era Denons are reported to use.
PORTS = (23, 80, 443, 1255, 8080, 10443)

#: Long enough to tell "refused" from "filtered" on this unit. A refusal comes
#: back over wifi in 2.2-2.5 s, so a 2 s timeout reported the closed ports as
#: filtered -- the opposite conclusion from the same wire.
TIMEOUT_S = 6.0


def probe(host: str, port: int) -> tuple[str, float]:
    """Try one TCP connection.

    Args:
        host: Receiver address.
        port: TCP port to try.

    Returns:
        A verdict (``open``, ``refused``, ``timeout`` or an error name) and how
        long the attempt took, in seconds.
    """
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT_S):
            return "open", time.monotonic() - started
    except TimeoutError:
        return "timeout", time.monotonic() - started
    except ConnectionRefusedError:
        return "refused", time.monotonic() - started
    except OSError as exc:
        return type(exc).__name__, time.monotonic() - started


def main() -> int:
    """Read the power state, then scan every port once.

    Returns:
        Process exit status.
    """
    cfg = load_config()
    host = cfg["device"]["host"]

    try:
        power = DenonClient.from_config().get_power()
    except (DeviceError, OSError) as exc:
        power = f"unknown ({exc})"

    print(f"host {host}   power {power}   {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    for port in PORTS:
        verdict, took = probe(host, port)
        print(f"  {port:>6}  {verdict:<12} {took:5.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
