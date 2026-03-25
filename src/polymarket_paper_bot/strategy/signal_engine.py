"""
Baseline YES-only paper strategy.

This module is intentionally simple: it exists to exercise plumbing (data ingest,
risk checks, simulated execution) — **not** to imply any edge or profitability.

Known limitations (non-exhaustive):
- Ignores fees, adverse selection, partial fills, latency, and cross-market correlation.
- Uses mid / top-of-book proxies that can diverge from realized trade prices.
- A constant fill probability is a crude stand-in for queue dynamics.
"""

from __future__ import annotations

from datetime import datetime

from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.models import (
    BotState,
    Market,
    OrderBook,
    Position,
    SignalAction,
    StrategySignal,
)


def cents_to_price(cents: float) -> float:
    """Convert a 'cents' setting into absolute price units (0..1 scale on Polymarket)."""
    return float(cents) / 100.0


def pick_yes_token(market: Market):
    """Pick the YES outcome token when possible; otherwise fall back to the first token."""
    for t in market.tokens:
        if t.outcome_label.strip().lower() in {"yes", "y"}:
            return t
    return market.tokens[0] if market.tokens else None


def spread_cents_from_book(book: OrderBook) -> float | None:
    """Return spread in 'cents' (price * 100) using normalized top-of-book."""
    if book.spread_cents is not None:
        return float(book.spread_cents)
    if book.spread is None:
        return None
    return float(book.spread) * 100.0


def mark_price(book: OrderBook) -> float | None:
    """Best-effort mid/mark for PnL and exit checks."""
    if book.mid is not None:
        return float(book.mid)
    if book.best_bid is not None and book.best_ask is not None:
        return float((book.best_bid + book.best_ask) / 2.0)
    return None


def evaluate_exit(
    position: Position,
    book: OrderBook,
    config: AppConfig,
    now: datetime,
) -> StrategySignal:
    """Generate an exit signal for an open YES position using TP/SL/time rules."""
    mark = mark_price(book)
    if mark is None:
        return StrategySignal(action=SignalAction.HOLD, reason="no_mark_price_for_exit")

    tp = float(position.entry_price) + cents_to_price(config.take_profit_cents)
    sl = float(position.entry_price) - cents_to_price(config.stop_loss_cents)

    if mark >= tp:
        return StrategySignal(
            action=SignalAction.EXIT,
            reason="take_profit",
            limit_price=float(book.best_bid or mark),
            size=float(position.size),
            token_id=position.token_id,
            market_id=position.market_id,
        )

    if mark <= sl:
        return StrategySignal(
            action=SignalAction.EXIT,
            reason="stop_loss",
            limit_price=float(book.best_bid or mark),
            size=float(position.size),
            token_id=position.token_id,
            market_id=position.market_id,
        )

    hold_min = (now - position.opened_at).total_seconds() / 60.0
    if hold_min >= float(config.max_hold_minutes):
        return StrategySignal(
            action=SignalAction.EXIT,
            reason="max_hold",
            limit_price=float(book.best_bid or mark),
            size=float(position.size),
            token_id=position.token_id,
            market_id=position.market_id,
        )

    return StrategySignal(action=SignalAction.HOLD, reason="hold_position")


def evaluate_entry(
    market: Market,
    book: OrderBook,
    config: AppConfig,
    state: BotState,
) -> StrategySignal:
    """
    Generate an entry signal (YES) when flat.

    Entry is modeled as a maker bid at the current best bid — fills are simulated
    separately with ``PAPER_FILL_PROBABILITY`` inside the paper broker.
    """
    if state.open_position is not None:
        return StrategySignal(action=SignalAction.HOLD, reason="already_open")

    yes = pick_yes_token(market)
    if yes is None:
        return StrategySignal(action=SignalAction.HOLD, reason="no_yes_token")

    if book.token_id != yes.token_id:
        return StrategySignal(action=SignalAction.HOLD, reason="book_not_yes_token")

    sc = spread_cents_from_book(book)
    if sc is None or sc + 1e-9 < float(config.min_spread_cents):
        return StrategySignal(action=SignalAction.HOLD, reason="spread_too_tight")

    mid = mark_price(book)
    if mid is None:
        return StrategySignal(action=SignalAction.HOLD, reason="no_mid")

    if mid < config.min_price or mid > config.max_price:
        return StrategySignal(action=SignalAction.HOLD, reason="mid_out_of_band")

    if book.best_bid is None:
        return StrategySignal(action=SignalAction.HOLD, reason="no_best_bid")

    # Maker-style anchor: join the best bid (paper fills are probabilistic).
    limit_price = float(book.best_bid)
    notional = float(min(config.max_position_notional, state.cash_usd))
    if notional <= 0:
        return StrategySignal(action=SignalAction.HOLD, reason="no_cash")

    if limit_price <= 0:
        return StrategySignal(action=SignalAction.HOLD, reason="bad_limit_price")

    size = notional / limit_price
    return StrategySignal(
        action=SignalAction.ENTER_YES,
        reason="entry_signal",
        limit_price=limit_price,
        size=size,
        token_id=yes.token_id,
        market_id=market.market_id,
    )
