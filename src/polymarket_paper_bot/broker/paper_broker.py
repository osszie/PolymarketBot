"""Paper execution engine: probabilistic maker fills, positions, PnL."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from random import Random
from typing import Any

from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.models import BotState, OrderBook, Position, StrategySignal, Trade
from polymarket_paper_bot.models import SignalAction
from polymarket_paper_bot.risk.risk_manager import RiskManager
from polymarket_paper_bot.storage.csv_logger import CsvTradeLogger
from polymarket_paper_bot.storage.state_store import StateStore, roll_trading_day_if_needed
from polymarket_paper_bot.strategy.signal_engine import mark_price
from polymarket_paper_bot.utils import new_id

logger = logging.getLogger(__name__)


def _exit_price(book: OrderBook) -> float | None:
    # Conservative liquidation proxy for paper mode: lift the bid when possible.
    if book.best_bid is not None:
        return float(book.best_bid)
    return mark_price(book)


def _min_contract_size_ok(size: float, min_order_size: float | None) -> bool:
    if min_order_size is None:
        return True
    return size + 1e-9 >= float(min_order_size)


class PaperBroker:
    """Simulated broker with one open position at a time."""

    def __init__(
        self,
        config: AppConfig,
        rng: Random,
        store: StateStore,
        csv_logger: CsvTradeLogger,
        risk: RiskManager,
    ) -> None:
        self._config = config
        self._rng = rng
        self._store = store
        self._csv = csv_logger
        self._risk = risk

    def load_state(self, config: AppConfig) -> BotState:
        """Load persisted state or initialize defaults."""
        return self._store.load_or_create(config)

    def save_state(self, state: BotState, now: datetime) -> None:
        """Persist state after bookkeeping updates."""
        roll_trading_day_if_needed(state, now)
        state.last_updated = now.astimezone(timezone.utc)
        self._store.save(state)

    def update_unrealized(self, state: BotState, book: OrderBook | None) -> None:
        """Mark open YES positions to mid/best bid/ask mid."""
        pos = state.open_position
        if pos is None or book is None:
            state.unrealized_pnl_usd = 0.0
            return
        if book.token_id != pos.token_id:
            state.unrealized_pnl_usd = 0.0
            return
        mark = mark_price(book)
        if mark is None:
            state.unrealized_pnl_usd = 0.0
            return
        state.unrealized_pnl_usd = float((mark - pos.entry_price) * pos.size)

    def try_fill_pending(
        self,
        book: OrderBook,
        state: BotState,
        now: datetime,
        min_order_size: float | None,
    ) -> list[Trade]:
        """Attempt a probabilistic fill for a resting maker order."""
        pending = state.pending_order
        if pending is None:
            return []

        if book.token_id != str(pending.get("token_id")):
            return []

        allowed = self._risk.allow_pending_order(state)
        if not allowed.allowed:
            state.pending_order = None
            return []

        if self._rng.random() > float(self._config.paper_fill_probability):
            return []

        limit_price = float(pending["limit_price"])
        size = float(pending["size"])
        notional = float(pending["notional"])
        market_id = str(pending["market_id"])
        token_id = str(pending["token_id"])

        stored_min = pending.get("min_order_size")
        if stored_min is not None and str(stored_min).strip() != "":
            try:
                min_order_size = float(stored_min)
            except (TypeError, ValueError):
                pass

        if not _min_contract_size_ok(size, min_order_size):
            logger.info("pending order canceled: below min contract size | size=%s min=%s", size, min_order_size)
            state.pending_order = None
            return []

        if notional > state.cash_usd + 1e-9:
            state.pending_order = None
            return []

        state.cash_usd -= notional

        pos = Position(
            position_id=new_id("pos"),
            market_id=market_id,
            token_id=token_id,
            side="YES",
            entry_price=limit_price,
            size=size,
            notional=notional,
            opened_at=now.astimezone(timezone.utc),
            entry_reason="simulated_maker_fill",
        )
        state.open_position = pos
        state.pending_order = None

        trade = Trade(
            trade_id=new_id("trd"),
            market_id=market_id,
            token_id=token_id,
            side="YES",
            action="buy",
            price=limit_price,
            size=size,
            notional=notional,
            fee=0.0,
            realized_pnl=None,
            timestamp=now.astimezone(timezone.utc),
            reason="paper_buy_fill",
        )
        self._csv.append(trade)
        state.trades_count += 1
        return [trade]

    def request_entry(
        self,
        signal: StrategySignal,
        state: BotState,
        now: datetime,
        min_order_size: float | None,
    ) -> bool:
        """Create a pending maker order from an entry signal (no immediate fill)."""
        if signal.action != SignalAction.ENTER_YES:
            return False
        if signal.limit_price is None or signal.size is None or signal.token_id is None or signal.market_id is None:
            return False

        notional = float(signal.limit_price) * float(signal.size)
        decision = self._risk.allow_entry(state, notional, min_order_size)
        if not decision.allowed:
            logger.info("entry refused | reason=%s", decision.reason)
            return False

        if not _min_contract_size_ok(float(signal.size), min_order_size):
            logger.info("entry refused | below min contract size")
            return False

        state.pending_order = {
            "market_id": str(signal.market_id),
            "token_id": str(signal.token_id),
            "limit_price": float(signal.limit_price),
            "size": float(signal.size),
            "notional": float(notional),
            "placed_at": now.astimezone(timezone.utc).isoformat(),
            "min_order_size": min_order_size,
        }
        return True

    def execute_exit(
        self,
        signal: StrategySignal,
        book: OrderBook,
        state: BotState,
        now: datetime,
    ) -> Trade | None:
        """Close a YES position using a conservative exit price proxy."""
        if signal.action != SignalAction.EXIT:
            return None
        pos = state.open_position
        if pos is None:
            return None
        if signal.token_id and signal.token_id != pos.token_id:
            return None

        px = _exit_price(book)
        if px is None:
            return None

        size = float(pos.size)
        proceeds = float(px * size)
        realized = float((px - pos.entry_price) * size)

        state.cash_usd += proceeds
        state.realized_pnl_usd += realized
        state.day_realized_pnl_usd += realized

        hold_s = max(0.0, (now.astimezone(timezone.utc) - pos.opened_at).total_seconds())
        state.total_hold_seconds += hold_s

        if realized > 1e-9:
            state.wins += 1
        elif realized < -1e-9:
            state.losses += 1

        trade = Trade(
            trade_id=new_id("trd"),
            market_id=pos.market_id,
            token_id=pos.token_id,
            side="YES",
            action="sell",
            price=float(px),
            size=size,
            notional=float(proceeds),
            fee=0.0,
            realized_pnl=float(realized),
            timestamp=now.astimezone(timezone.utc),
            reason=str(signal.reason),
        )
        self._csv.append(trade)
        state.trades_count += 1
        state.open_position = None
        state.pending_order = None
        state.unrealized_pnl_usd = 0.0
        return trade

    def snapshot_metrics(self, state: BotState) -> dict[str, Any]:
        """Compute lightweight performance metrics for console summaries."""
        closed = int(state.wins + state.losses)
        win_rate = float(state.wins) / float(closed) if closed > 0 else 0.0
        avg_hold = float(state.total_hold_seconds / closed) if closed > 0 else 0.0
        return {
            "cash_usd": float(state.cash_usd),
            "realized_pnl_usd": float(state.realized_pnl_usd),
            "unrealized_pnl_usd": float(state.unrealized_pnl_usd),
            "trades_count": int(state.trades_count),
            "wins": int(state.wins),
            "losses": int(state.losses),
            "win_rate": win_rate,
            "avg_hold_seconds": avg_hold,
        }
