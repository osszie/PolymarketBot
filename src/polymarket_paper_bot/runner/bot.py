"""Orchestrates scans, paper trading loops, and snapshot replay."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from random import Random

from polymarket_paper_bot.broker.paper_broker import PaperBroker
from polymarket_paper_bot.clients.clob_client import ClobClient
from polymarket_paper_bot.clients.gamma_client import GammaClient
from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.models import BotState, Market, OrderBook, SignalAction
from polymarket_paper_bot.risk.risk_manager import RiskManager
from polymarket_paper_bot.runner.snapshot import load_snapshot_file
from polymarket_paper_bot.storage.csv_logger import CsvTradeLogger
from polymarket_paper_bot.storage.state_store import StateStore, roll_trading_day_if_needed
from polymarket_paper_bot.strategy.filters import market_passes_filters
from polymarket_paper_bot.strategy.market_selector import rank_and_select
from polymarket_paper_bot.strategy.signal_engine import evaluate_entry, evaluate_exit, pick_yes_token
from polymarket_paper_bot.utils import deterministic_rng

logger = logging.getLogger(__name__)


def effective_min_order_size(market: Market, book: OrderBook) -> float | None:
    """Combine venue minimums from Gamma metadata and CLOB book fields when present."""
    vals: list[float] = []
    if market.min_order_size is not None:
        vals.append(float(market.min_order_size))
    if book.min_order_size is not None:
        vals.append(float(book.min_order_size))
    return max(vals) if vals else None


class TradingBot:
    """High-level runner for paper trading and public-data scans."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.gamma = GammaClient(config)
        self.clob = ClobClient(config)
        self.risk = RiskManager(config)
        self.store = StateStore(config)
        self.csv = CsvTradeLogger(config)
        self.rng: Random = deterministic_rng(config.random_seed)
        self.broker = PaperBroker(config, self.rng, self.store, self.csv, self.risk)

    def close(self) -> None:
        """Close HTTP clients."""
        self.gamma.close()
        self.clob.close()

    def run_scan(self, *, top_n: int) -> None:
        """Fetch markets + books once and print ranked candidates."""
        markets = self.gamma.get_active_markets(self.config.max_markets_to_scan)
        pairs: list[tuple[Market, OrderBook]] = []
        for m in markets:
            yes = pick_yes_token(m)
            if yes is None:
                continue
            book = self.clob.get_order_book(yes.token_id)
            if book is None:
                continue
            pairs.append((m, book))

        ranked = rank_and_select(pairs, self.config, top_n=max(1, int(top_n)))
        if not ranked:
            logger.warning("scan produced no scored candidates (filters/order books may be empty)")
            return

        for idx, sc in enumerate(ranked, start=1):
            ok, reason = market_passes_filters(sc.market, sc.book, self.config)
            logger.info(
                "candidate #%s | score=%.4f | ok=%s | reason=%s | market=%s | slug=%s | vol24=%s | spread_c=%.4f",
                idx,
                sc.score,
                ok,
                reason,
                sc.market.market_id,
                sc.market.slug,
                sc.market.volume_24hr if sc.market.volume_24hr is not None else sc.market.volume,
                float(sc.book.spread_cents or 0.0),
            )

    def run_paper_loop(self, *, iterations: int) -> None:
        """Run ``iterations`` timed ticks against live public endpoints (paper only)."""
        for i in range(max(1, int(iterations))):
            now = datetime.now(timezone.utc)
            logger.info("paper tick | i=%s/%s", i + 1, iterations)
            self._paper_tick_live(now)
            if i < iterations - 1:
                time.sleep(float(self.config.loop_seconds))

        state = self.broker.load_state(self.config)
        metrics = self.broker.snapshot_metrics(state)
        logger.info("run summary | %s", metrics)

    def _paper_tick_live(self, now: datetime) -> None:
        state = self.broker.load_state(self.config)
        roll_trading_day_if_needed(state, now)

        if state.open_position and state.open_position.token_id:
            book = self.clob.get_order_book(state.open_position.token_id)
            if book is None:
                logger.warning("could not load book for open position; skipping tick")
                self.broker.save_state(state, now)
                return
            self.broker.update_unrealized(state, book)
            sig = evaluate_exit(state.open_position, book, self.config, now)
            if sig.action == SignalAction.EXIT:
                self.broker.execute_exit(sig, book, state, now)
            self.broker.save_state(state, now)
            return

        if state.pending_order:
            token_id = str(state.pending_order.get("token_id") or "")
            book = self.clob.get_order_book(token_id) if token_id else None
            if book is None:
                logger.warning("could not load book for pending order; will retry next tick")
                self.broker.save_state(state, now)
                return
            min_sz = effective_min_order_size(
                _market_stub_from_pending(state),
                book,
            )
            self.broker.try_fill_pending(book, state, now, min_sz)
            self.broker.save_state(state, now)
            return

        markets = self.gamma.get_active_markets(self.config.max_markets_to_scan)
        pairs: list[tuple[Market, OrderBook]] = []
        for m in markets:
            yes = pick_yes_token(m)
            if yes is None:
                continue
            book = self.clob.get_order_book(yes.token_id)
            if book is None:
                continue
            pairs.append((m, book))

        ranked = rank_and_select(pairs, self.config, top_n=3)
        if not ranked:
            logger.info("no tradeable candidates this tick")
            self.broker.save_state(state, now)
            return

        best = ranked[0]
        min_sz = effective_min_order_size(best.market, best.book)
        sig = evaluate_entry(best.market, best.book, self.config, state)
        if sig.action == SignalAction.ENTER_YES:
            placed = self.broker.request_entry(sig, state, now, min_sz)
            if placed:
                logger.info("submitted paper maker entry | market=%s | token=%s", sig.market_id, sig.token_id)
        self.broker.save_state(state, now)

    def run_replay(self, *, snapshot_path: Path, iterations: int) -> None:
        """Replay stored snapshots through the paper broker without HTTP I/O."""
        steps = load_snapshot_file(snapshot_path)
        if not steps:
            logger.warning("replay snapshot contained no steps")
            return

        state = self.broker.load_state(self.config)
        n = min(len(steps), max(1, int(iterations)))

        for i in range(n):
            market, book = steps[i]
            now = datetime.now(timezone.utc)
            logger.info("replay step | %s/%s | market=%s", i + 1, n, market.market_id)
            self._paper_tick_replay(state, now, market, book)

        metrics = self.broker.snapshot_metrics(state)
        logger.info("replay summary | %s", metrics)

    def _paper_tick_replay(
        self,
        state: BotState,
        now: datetime,
        market: Market,
        book: OrderBook,
    ) -> None:
        roll_trading_day_if_needed(state, now)

        if state.open_position:
            sig = evaluate_exit(state.open_position, book, self.config, now)
            self.broker.update_unrealized(state, book)
            if sig.action == SignalAction.EXIT:
                self.broker.execute_exit(sig, book, state, now)
            self.broker.save_state(state, now)
            return

        if state.pending_order:
            min_sz = effective_min_order_size(market, book)
            self.broker.try_fill_pending(book, state, now, min_sz)
            self.broker.save_state(state, now)
            return

        min_sz = effective_min_order_size(market, book)
        sig = evaluate_entry(market, book, self.config, state)
        if sig.action == SignalAction.ENTER_YES:
            self.broker.request_entry(sig, state, now, min_sz)
        self.broker.save_state(state, now)


def _market_stub_from_pending(state: BotState) -> Market:
    """Minimal market object for min-size lookup when a pending order exists."""
    from polymarket_paper_bot.models import Token

    pending = state.pending_order or {}
    market_id = str(pending.get("market_id") or "unknown")
    token_id = str(pending.get("token_id") or "")
    mos = pending.get("min_order_size")
    mos_f = float(mos) if mos is not None else None
    return Market(
        market_id=market_id,
        question="",
        slug="",
        active=True,
        closed=False,
        volume=0.0,
        volume_24hr=None,
        liquidity=None,
        enable_order_book=True,
        accepting_orders=True,
        min_order_size=mos_f,
        tokens=[Token(token_id=token_id, outcome_label="YES", market_id=market_id)],
        outcome_prices=None,
        raw={},
    )
