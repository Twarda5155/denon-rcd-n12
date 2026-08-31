"""Standalone probe: report whether the Denon RCD-N12 is powered ON or in STANDBY.

What it does
------------
Opens a raw TCP connection to the receiver's AVR control port (telnet, port 23),
asks for the power state, prints either ``PWON`` or ``PWSTANDBY``, then closes the
connection cleanly. No project imports; run it directly with ``python``.

How it works
------------
1. Connect to <receiver-ip>:23 with a 2 s connect timeout.
2. Send the power-status query ``PW?\\r`` (Denon commands are CR-terminated ASCII).
3. The port is a stream that emits one or more status frames, so keep calling
   ``recv()`` (2 s per-read timeout) until the buffer contains ``PWON`` or
   ``PWSTANDBY``, then print that match.
4. Graceful close: ``shutdown(SHUT_WR)`` sends a FIN ("done sending"), then drain
   and discard any trailing bytes until the receiver closes its side or 0.3 s
   passes. This avoids an abortive RST that some firmware reacts badly to.
5. The ``with`` block closes the (now drained) socket on exit.

Note
----
The receiver IP is hardcoded here for the initial bring-up test only; it should
later be read from ``config/device.yaml`` like the rest of the project.
"""

import socket, re

with socket.create_connection(("192.168.3.40", 23), timeout=2) as s:
    s.sendall(b"PW?\r")
    buf = b""
    s.settimeout(2)
    while not re.search(rb"PW(ON|STANDBY)", buf):
        buf += s.recv(256)
    print(re.search(rb"PW(ON|STANDBY)", buf).group().decode())

    s.shutdown(socket.SHUT_WR) # tell the receiver "I'm done sending"
    s.settimeout(0.3)
    try:
        while s.recv(256):     # read whatever it still sends, discard it
            pass               # until recv() returns b'' (peer closed) or times out
    except OSError:
        pass
# socket is closed here automatically by the `with` statement