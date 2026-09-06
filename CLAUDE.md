# denon-rcd-n12

Local control of a Denon RCD-N12 network receiver on the home LAN, plus a
loopback-only one-page control app over its state.

## Environment
- Windows 10 Pro, Windows Terminal, PowerShell.
- Mamba env `denon` (Python 3.12). Activate before anything: `mamba activate denon`.
  Use mamba, not conda, for anything that touches environments.
  PowerShell needs the hook first, or `activate` silently no-ops:
  `(& mamba shell hook --shell powershell) | Out-String | Invoke-Expression`.
  If mamba ever dies with `critical libmamba failed to run python command`
  while reading `pip inspect --local`, the env's metadata is damaged: rebuild
  it rather than repairing it. Recreating this env on 2026-09-05 cleared it.
- MariaDB on localhost for persisted state/history. No driver is installed in
  the env yet and no code talks to it — deliberate, as of 2026-09-05.
- The receiver is on the local network. Its address is in `config/device.yaml`.

## Layout
- `src/denon_rcd_n12/` — library. `transport.py` (I/O), `client.py` (commands),
  `server.py` (loopback HTTP API), `static/index.html` (the page), `cli.py`.
- `tests/` — pytest. All tests use FakeTransport; none touch the network.
- `config/` — YAML, human-owned. Do not edit without asking.
- `docs/decisions/` — one dated markdown file per design decision.
- `docs/results/` — analysis writeups and publication material.
- `notebooks/` — prototyping only. Anything worth keeping moves to `src/`.

## Hard rules
- Never hardcode the receiver IP. Read it from `config/device.yaml`.
- All device I/O goes through `transport.py`. Nothing else opens a socket.
- Tests must pass with the receiver powered off.
- Run `pytest -q` before proposing a commit.
- Update `STATUS.md` and `OPEN-QUESTIONS.md` before proposing a commit.
  A question that gets answered leaves `OPEN-QUESTIONS.md`: measured facts
  go to `docs/reference/`, choices go to `docs/decisions/`.

## Commands
- Tests: `pytest -q`
- Control page: `$env:PYTHONPATH="src"; python -m denon_rcd_n12.cli serve`
  (there is no install step, so `src` must be on the path)
- Lint: `ruff check src tests`

## Conventions
- Python first; JavaScript only inside `static/index.html`, inlined and
  dependency-free — the page must fetch nothing from off the machine.
- Type hints on all public functions. Google-style docstrings.
- Commit messages: `area: imperative summary` (e.g. `transport: retry on timeout`).
