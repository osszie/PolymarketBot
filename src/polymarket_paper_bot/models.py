"""Domain models for markets, order books, positions, and bot state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utcnow() -> datetime:
    """Timezone-aware UTC ``now`` (used for tests and deterministic timestamps)."""
    return datetime.now(timezone.utc)


class SignalAction(str, Enum):
    """Coarse strategy action."""

    HOLD = "hold"
    ENTER_YES = "enter_yes"
    EXIT = "exit"


@dataclass(slots=True)
class Token:
    """Outcome token on the CLOB (e.g., YES / NO)."""

    token_id: str
    outcome_label: str
    market_id: str


@dataclass(slots=True)
class Market:
    """Normalized Gamma market record (fields may be partially missing upstream)."""

    market_id: str
    question: str
    slug: str
    active: bool
    closed: bool
    volume: float
    volume_24hr: float | None
    liquidity: float | None
    enable_order_book: bool | None
    accepting_orders: bool | None
    min_order_size: float | None
    tokens: list[Token]
    outcome_prices: list[float] | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrderBookLevel:
    """Single price level on the CLOB."""

    price: float
    size: float


@dataclass(slots=True)
class OrderBook:
    """Normalized L2 book for one token."""

    token_id: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    spread_cents: float | None
    mid: float | None
    min_order_size: float | None
    tick_size: float | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StrategySignal:
    """Strategy output for one evaluation step."""

    action: SignalAction
    reason: str
    limit_price: float | None = None
    size: float | None = None
    token_id: str | None = None
    market_id: str | None = None


@dataclass(slots=True)
class Position:
    """Open simulated position (YES-only baseline)."""

    position_id: str
    market_id: str
    token_id: str
    side: str  # "YES"
    entry_price: float
    size: float
    notional: float
    opened_at: datetime
    entry_reason: str


@dataclass(slots=True)
class Trade:
    """Executed (simulated) trade record."""

    trade_id: str
    market_id: str
    token_id: str
    side: str
    action: str  # "buy", "sell"
    price: float
    size: float
    notional: float
    fee: float
    realized_pnl: float | None
    timestamp: datetime
    reason: str


@dataclass(slots=True)
class BotState:
    """Persisted bot state (paper)."""

    cash_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    open_position: Position | None
    pending_order: dict[str, Any] | None
    trades_count: int
    wins: int
    losses: int
    total_hold_seconds: float
    day_key: str
    day_realized_pnl_usd: float
    last_updated: datetime
