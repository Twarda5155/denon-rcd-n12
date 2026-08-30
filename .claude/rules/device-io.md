---
paths:
  - "src/denon_rcd_n12/transport.py"
  - "tests/**/*.py"
---

# Device I/O rules

- Every socket call needs an explicit timeout and a retry policy.
- Log every command sent and response received to `logs/device.log`.
- FakeTransport replays fixtures from `tests/fixtures/`; keep it in sync with
  TelnetTransport's interface via a shared Protocol.
