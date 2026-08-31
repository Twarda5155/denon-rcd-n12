"""Standalone probe: read the Denon RCD-N12 power state, turn it ON, confirm.

What it does
------------
Defines one helper, ``send_denon(cmd)``, that fires a single Denon control
command over the AVR telnet port (23) and returns every status frame the
receiver sends back as a list of strings. The script then: prints the current
power state, sends ``PWON``, waits for the unit to boot, and prints the state
again. No project imports; run it directly with ``python``.

How it works
------------
1. ``send_denon`` connects to <ip>:23 (3 s connect timeout) and sends
   ``<cmd>\\r`` (Denon commands are CR-terminated ASCII).
2. It sleeps ``wait`` seconds to let the reply arrive, then switches to a short
   0.3 s read timeout and loops ``recv()`` until the socket goes quiet
   (``socket.timeout``) or the peer closes.
3. The raw bytes are decoded and split on ``\\r``; empty fragments are dropped,
   so the return value is a clean list like ``['PWON']`` or ``['PWSTANDBY']``.
4. The ``with`` block closes the socket after each command.
5. Top level: query ``PW?`` -> ``PWON`` -> sleep 4 s (power-up) -> query ``PW?``
   again to confirm the transition.

Note
----
The receiver IP is a hardcoded default for the initial bring-up test only; it
should later come from ``config/device.yaml`` like the rest of the project.
"""

import socket, time

def send_denon(cmd, ip='192.168.3.40', port=23, wait=0.7):
    with socket.create_connection((ip, port), timeout=3) as s:
        s.sendall(f'{cmd}\r'.encode('ascii'))
        time.sleep(wait)
        s.settimeout(0.3)
        buf = b''
        try:
            while True:
                chunk = s.recv(1024)
                if not chunk:
                    break
                buf += chunk
        except socket.timeout:
            pass
    return [t for t in buf.decode('ascii', 'ignore').split('\r') if t]

print(send_denon('PW?'))
send_denon('PWON')
time.sleep(4)
print(send_denon('PW?'))