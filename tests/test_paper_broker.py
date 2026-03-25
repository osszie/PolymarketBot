"""Tests for simulated fills, PnL, and broker accounting."""

from __future__ import annotations

from datetime import datetime, timezone
from random import Random

from polymarket_paper_bot.broker.paper_broker import PaperBroker
from polymarket_paper_bot.config import load_config
from polymarket_paper_bot.models import BotState, OrderBook, OrderBookLevel, StrategySignal
from polymarket_paper_bot.models import SignalAction
from polymarket_paper_bot.risk.risk_manager import RiskManager
from polymarket_paper_bot.storage.csv_logger import CsvTradeLogger
from polymarket_paper_bot.storage.state_store import StateStore


def _cfg(tmp_path: object) -> object:
    import pathlib

    p = pathlib.Path(tmp_path)
    return load_config(
        {
            "DATA_DIR": str(p / "data"),
            "LOGS_DIR": str(p / "logs"),
            "PAPER_FILL_PROBABILITY": "1.0",
            "MAX_POSITION_NOTIONAL": "10",
            "MIN_PRACTICAL_ORDER_NOTIONAL": "0.01",
        }
    )


def _flat_state() -> BotState:
    return BotState(
        cash_usd=10.0,
        realized_pnl_usd=0.0,
        unrealized_pnl_usd=0.0,
        open_position=None,
        pending_order=None,
        trades_count=0,
        wins=0,
        losses=0,
        total_hold_seconds=0.0,
        day_key="2025-01-01",
        day_realized_pnl_usd=0.0,
        last_updated=datetime.now(timezone.utc),
    )


def test_pending_fill_and_exit_pnl(tmp_path: object) -> None:
    cfg = _cfg(tmp_path)
    cfg.ensure_runtime_dirs()
    rng = Random(0)
    store = StateStore(cfg)
    csv_logger = CsvTradeLogger(cfg)
    risk = RiskManager(cfg)
    broker = PaperBroker(cfg, rng, store, csv_logger, risk)

    state = _flat_state()
    now = datetime.now(timezone.utc)

    sig = StrategySignal(
        action=SignalAction.ENTER_YES,
        reason="entry_signal",
        limit_price=0.50,
        size=10.0,
        token_id="yes1",
        market_id="m1",
    )
    assert broker.request_entry(sig, state, now, min_order_size=1.0) is True

    book = OrderBook(
        token_id="yes1",
        bids=[OrderBookLevel(0.50, 100.0)],
        asks=[OrderBookLevel(0.55, 100.0)],
        best_bid=0.50,
        best_ask=0.55,
        spread=0.05,
        spread_cents=5.0,
        mid=0.525,
        min_order_size=1.0,
        tick_size=0.01,
        raw={},
    )
    trades = broker.try_fill_pending(book, state, now, min_order_size=1.0)
    assert len(trades) == 1
    assert state.open_position is not None
    assert abs(state.cash_usd - 5.0) < 1e-6  # 10 - 5 notional

    broker.update_unrealized(state, book)
    assert state.unrealized_pnl_usd != 0.0

    pos = state.open_position
    assert pos is not None
    # Force exit at bid (not a take-profit path in this fixture).
    exit_sig = StrategySignal(
        action=SignalAction.EXIT,
        reason="test_exit",
        limit_price=float(book.best_bid or 0.0),
        size=float(pos.size),
        token_id=pos.token_id,
        market_id=pos.market_id,
    )
    tr = broker.execute_exit(exit_sig, book, state, now)
    assert tr is not None
    assert tr.realized_pnl is not None
    assert state.open_position is None


def test_metrics_win_rate(tmp_path: object) -> None:
    cfg = _cfg(tmp_path)
    state = _flat_state()
    state.wins = 0
    state.losses = 0
    state.losses = 1
    state.wins = 1
    state.total_hold_seconds = 100.0
    broker = PaperBroker(cfg, Random(0), StateStore(cfg), CsvTradeLogger(cfg), RiskManager(cfg))
    m = broker.snapshot_metrics(state)
    assert m["win_rate"] == 0.5
    assert m["avg_hold_seconds"] == 50.0
