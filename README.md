# polymarket-paper-bot

A small, **paper-trading-only-by-default** Python bot that ingests **public** Polymarket market and CLOB data, filters candidate markets, applies a **baseline** YES-side strategy, and simulates execution with CSV/JSON logging.

This project is designed as a **research and simulation** sandbox: production-style structure, minimal dependencies, and no hardcoded secrets.

## Safety and compliance

- **Default behavior** is **public data + paper trading** only (no wallet, no authenticated trading in-tree).
- **You are responsible** for complying with [Polymarket](https://polymarket.com/) terms of service and applicable laws in your jurisdiction.
- **Do not** use this repo to bypass geography, compliance, platform restrictions, or account controls.
- If you ever add a **live-trading adapter**, keep it **disabled by default**, **lawful**, and **separate** from the public-data pipeline; **never** commit API keys or private keys.
- This software **does not** claim profitability or suitability for trading.

## Features

- **Gamma API** market discovery (`/markets`) with defensive normalization.
- **CLOB public reads**: order books (`/book`), midpoint (`/midpoint`), spread (`/spread`).
- **Retries** with exponential backoff for transient HTTP failures.
- **Configurable filters** (volume, spread, price band, order book flags).
- **Paper broker** with probabilistic maker fills, positions, PnL, and **one open position** at a time.
- **Risk** checks (notional caps, cash, optional daily loss cap, kill switch).
- **CSV** trade log + **JSON** state snapshots under `DATA_DIR`.
- **CLI modes**: `paper` loop, `scan`, `snapshot` capture, `replay` from JSON snapshots.
- **Local web dashboard** (`--mode web`) to view `trades.csv` and `bot_state.json` in the browser (read-only).

## Requirements

- Python **3.11+** (tested on 3.11+; 3.13 works locally)
- Network access for live `scan` / `paper` / `snapshot` modes (not required for `--mode web`)

## Quickstart

```bash
cd polymarket-paper-bot
make install
cp .env.example .env
make test
make run
```

Or without `make`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -e .
cp .env.example .env
python -m polymarket_paper_bot --mode paper --iterations 5
```

## CLI

```text
python -m polymarket_paper_bot --mode paper --iterations 20
python -m polymarket_paper_bot --mode scan --iterations 10
python -m polymarket_paper_bot --mode snapshot --snapshot-file ./data/snapshot.json
python -m polymarket_paper_bot --mode replay --snapshot-file ./data/snapshot.json --iterations 50
python -m polymarket_paper_bot --mode web --host 127.0.0.1 --port 5050
make web
```

### Web dashboard (local)

Starts a small **Flask** UI (default `http://127.0.0.1:5050`) that reads:

- `DATA_DIR/trades.csv` — all simulated fills (newest first)
- `DATA_DIR/bot_state.json` — cash, PnL, open position (if any)

JSON endpoints: `/api/trades`, `/api/state`. The page auto-refreshes every 30 seconds.

Bind address is **`127.0.0.1` by default** (local only). Only use `--host 0.0.0.0` on a trusted network if you need access from another machine.

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `STARTING_BANKROLL` | `10.0` | Initial simulated cash |
| `MAX_POSITION_NOTIONAL` | `2.5` | Cap per position |
| `MIN_MARKET_VOLUME` | `10000` | Minimum volume (24h if present, else total) |
| `MIN_SPREAD_CENTS` | `3` | Minimum top-of-book spread (price × 100) |
| `TAKE_PROFIT_CENTS` / `STOP_LOSS_CENTS` | `2` / `3` | Exit thresholds for YES mark |
| `MAX_HOLD_MINUTES` | `120` | Time stop |
| `LOOP_SECONDS` | `10` | Delay between paper ticks |
| `MAX_MARKETS_TO_SCAN` | `50` | Gamma fetch limit |
| `MIN_PRICE` / `MAX_PRICE` | `0.10` / `0.90` | Allowed mid range |
| `PAPER_FILL_PROBABILITY` | `0.25` | Per-tick maker fill probability |
| `DAILY_MAX_LOSS_USD` | empty | Optional daily realized loss cap |
| `KILL_SWITCH` | `false` | Hard stop for new entries |
| `ENABLE_LIVE_ADAPTER` | `false` | Must be false for this repo build |
| `DATA_DIR` / `LOGS_DIR` | `./data` / `./logs` | Output paths |

## Project layout

```text
polymarket-paper-bot/
  src/polymarket_paper_bot/
    config.py          # env configuration
    models.py          # dataclasses
    clients/           # Gamma + CLOB readers
    strategy/          # filters, scoring, baseline signals
    broker/            # paper broker + live adapter boundary (stub)
    risk/              # risk checks
    storage/           # CSV + JSON state
    runner/            # orchestration + snapshot helpers
    web/               # Flask dashboard (trades + state)
    main.py            # CLI
  tests/
```

## How paper mode works

1. Load **JSON state** (`DATA_DIR/bot_state.json`) or start fresh at `STARTING_BANKROLL`.
2. Pull active markets from **Gamma**, fetch **YES** token books from the **CLOB**.
3. Rank candidates by a simple **liquidity + spread** score.
4. If flat, place a **simulated maker** bid at the **best bid**; each tick it may fill with probability `PAPER_FILL_PROBABILITY`.
5. When filled, manage the position with **take-profit**, **stop-loss**, and **max-hold** rules against a mid / top-of-book mark.
6. Append trades to **CSV** and persist state to **JSON**.

## Limitations

- **Not** a prediction engine; the strategy is a **baseline** for plumbing tests.
- Public endpoints and schemas can change; clients normalize **defensively**.
- Slippage, fees, latency, and partial fills are **not** modeled realistically.
- **Replay** snapshots are best-effort for debugging; steps may not match token continuity across markets.

## Future work (ideas)

- Richer execution model (partial fills, queue position proxy, fee schedule).
- Multi-position portfolio mode with caps.
- Stronger observability (structured JSON logs, optional OpenTelemetry).
- Property-based tests for accounting invariants.

## License

MIT — see [`LICENSE`](LICENSE).
