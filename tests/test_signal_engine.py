"""Tests for spread math and baseline signals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polymarket_paper_bot.config import load_config
from polymarket_paper_bot.models import BotState, Market, OrderBook, OrderBookLevel, Position, Token
from polymarket_paper_bot.strategy.signal_engine import (
    cents_to_price,
    evaluate_entry,
    evaluate_exit,
    mark_price,
    spread_cents_from_book,
)
from polymarket_paper_bot.models import SignalAction


def _book() -> OrderBook:
    return OrderBook(
        token_id="yes1",
        bids=[OrderBookLevel(0.40, 10.0)],
        asks=[OrderBookLevel(0.46, 10.0)],
        best_bid=0.40,
        best_ask=0.46,
        spread=0.06,
        spread_cents=6.0,
        mid=0.43,
        min_order_size=5.0,
        tick_size=0.01,
        raw={},
    )


def test_spread_cents_and_mark_price() -> None:
    b = _book()
    assert abs((spread_cents_from_book(b) or 0.0) - 6.0) < 1e-9
    assert abs((mark_price(b) or 0.0) - 0.43) < 1e-9


def test_cents_to_price() -> None:
    assert abs(cents_to_price(2.0) - 0.02) < 1e-9


def test_evaluate_exit_take_profit() -> None:
    cfg = load_config({"TAKE_PROFIT_CENTS": "2", "STOP_LOSS_CENTS": "3", "MAX_HOLD_MINUTES": "120"})
    pos = Position(
        position_id="p1",
        market_id="m1",
        token_id="yes1",
        side="YES",
        entry_price=0.40,
        size=10.0,
        notional=4.0,
        opened_at=datetime.now(timezone.utc),
        entry_reason="test",
    )
    book = _book()
    book.best_bid = 0.43
    book.best_ask = 0.44
    book.mid = 0.435
    sig = evaluate_exit(pos, book, cfg, datetime.now(timezone.utc))
    assert sig.action == SignalAction.EXIT
    assert sig.reason == "take_profit"


def test_evaluate_entry_blocked_when_position_open() -> None:
    cfg = load_config(
        {
            "MIN_SPREAD_CENTS": "1",
            "MIN_PRICE": "0.01",
            "MAX_PRICE": "0.99",
            "MAX_POSITION_NOTIONAL": "10",
        }
    )
    m = Market(
        market_id="m1",
        question="q",
        slug="s",
        active=True,
        closed=False,
        volume=50_000.0,
        volume_24hr=50_000.0,
        liquidity=1.0,
        enable_order_book=True,
        accepting_orders=True,
        min_order_size=5.0,
        tokens=[Token(token_id="yes1", outcome_label="Yes", market_id="m1")],
        outcome_prices=[0.43],
        raw={},
    )
    pos = Position(
        position_id="p1",
        market_id="m1",
        token_id="yes1",
        side="YES",
        entry_price=0.40,
        size=1.0,
        notional=0.4,
        opened_at=datetime.now(timezone.utc),
        entry_reason="test",
    )
    state = BotState(
        cash_usd=9.0,
        realized_pnl_usd=0.0,
        unrealized_pnl_usd=0.0,
        open_position=pos,
        pending_order=None,
        trades_count=0,
        wins=0,
        losses=0,
        total_hold_seconds=0.0,
        day_key="2025-01-01",
        day_realized_pnl_usd=0.0,
        last_updated=datetime.now(timezone.utc),
    )
    sig = evaluate_entry(m, _book(), cfg, state)
    assert sig.action == SignalAction.HOLD
    assert sig.reason == "already_open"


def test_evaluate_exit_max_hold() -> None:
    cfg = load_config({"TAKE_PROFIT_CENTS": "50", "STOP_LOSS_CENTS": "50", "MAX_HOLD_MINUTES": "60"})
    opened = datetime.now(timezone.utc) - timedelta(minutes=61)
    pos = Position(
        position_id="p1",
        market_id="m1",
        token_id="yes1",
        side="YES",
        entry_price=0.40,
        size=10.0,
        notional=4.0,
        opened_at=opened,
        entry_reason="test",
    )
    book = _book()
    sig = evaluate_exit(pos, book, cfg, datetime.now(timezone.utc))
    assert sig.action == SignalAction.EXIT
    assert sig.reason == "max_hold"
