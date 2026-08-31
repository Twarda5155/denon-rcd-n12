# tools/probe_device.py
"""Probe the receiver's AVR protocol. Requires the device powered on and reachable."""
from __future__ import annotations

import socket
import time
from pathlib import Path

import yaml

CONFIG = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "config" / "device.yaml").read_text(
        encoding="utf-8-sig"
    )
)
HOST = CONFIG["device"]["host"]
PORT = CONFIG["ports"]["avr"]


def avr(cmds: list[str], listen: float = 3.0, gap: float = 0.6) -> str:
    """Send AVR commands with pacing, then collect replies and heartbeat."""
    with socket.create_connection((HOST, PORT), timeout=3) as s:
        s.settimeout(0.5)
        for c in cmds:
            s.sendall((c + "\r").encode("ascii"))
            time.sleep(gap)          # >=300ms: rapid commands soft-lock Denon units
        chunks: list[str] = []
        deadline = time.time() + listen
        while time.time() < deadline:
            try:
                data = s.recv(4096)
                if not data:
                    break
                chunks.append(data.decode("ascii", errors="replace"))
            except TimeoutError:
                continue
    return "".join(chunks).replace("\r", "\n").strip()


if __name__ == "__main__":
    print("--- queries ---")
    print(avr(["PW?", "MV?", "MU?", "SI?", "SLP?"], listen=4))
    print("--- passive heartbeat (12s) ---")
    print(avr([], listen=12))