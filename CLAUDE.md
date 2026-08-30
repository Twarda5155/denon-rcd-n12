# denon-rcd-n12

Local control of a Denon RCD-N12 network receiver on the home LAN, plus a
Streamlit dashboard over its state.

## Environment
- Windows 10 Pro, Windows Terminal, PowerShell.
- Conda env `denon` (Python 3.12). Activate before anything: `conda activate denon`.
- MariaDB on localhost for persisted state/history.
- The receiver is on the local network. Its address is in `config/device.yaml`.

## Layout
- `src/denon_rcd_n12/` — library. `transport.py` (I/O), `client.py` (commands), `cli.py`.
- `tests/` — pytest. All tests use FakeTransport; none touch the network.
- `streamlit/app.py` — dashboard.
- `config/` — YAML, human-owned. Do not edit without asking.
- `docs/decisions/` — one dated markdown file per design decision.
- `docs/results/` — analysis writeups and publication material.
- `notebooks/` — prototyping only. Anything worth keeping moves to `src/`.

## Hard rules
- Never hardcode the receiver IP. Read it from `config/device.yaml`.
- All device I/O goes through `transport.py`. Nothing else opens a socket.
- Tests must pass with the receiver powered off.
- Run `pytest -q` before proposing a commit.

## Commands
- Tests: `pytest -q`
- Dashboard: `streamlit run streamlit/app.py`
- Lint: `ruff check src tests`

## Conventions
- Python first; JavaScript only inside Streamlit components when unavoidable.
- Type hints on all public functions. Google-style docstrings.
- Commit messages: `area: imperative summary` (e.g. `transport: retry on timeout`).
